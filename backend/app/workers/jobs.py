"""
Background worker jobs for image processing
"""
from rq import get_current_job
from PIL import Image
import hashlib
import io
import logging
from datetime import datetime
import numpy as np

from app.core.database import SessionLocal
from app.core.storage import get_file
from app.models.media import Media
from app.ml.clip_embedder import get_clip_embedder
from app.ml.object_detector import get_object_detector
from app.ml.captioner import get_image_captioner
from app.ml.ocr import get_ocr_extractor
from app.utils.exif import extract_exif_data

logger = logging.getLogger(__name__)


def analyze_image(media_id: int):
    """
    Main worker job to analyze an uploaded image
    
    Args:
        media_id: Database ID of media record
    """
    job = get_current_job()
    db = SessionLocal()
    
    try:
        # Get media record
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            logger.error(f"Media {media_id} not found")
            return
        
        logger.info(f"Processing media {media_id}: {media.filename}")
        
        # Update status
        media.status = "processing"
        db.commit()
        
        # Download image from MinIO
        image_data = get_file(media.minio_key)
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        # Store dimensions
        media.width, media.height = image.size
        
        # Extract EXIF data
        try:
            exif_data = extract_exif_data(image)
            media.exif_json = exif_data
        except Exception as e:
            logger.warning(f"Failed to extract EXIF: {e}")
            media.exif_json = {}
        
        # Initialize metadata dict
        metadata = {}
        
        # 1. Object Detection
        try:
            logger.info("Running object detection...")
            detector = get_object_detector()
            objects = detector.detect(image)
            metadata["objects"] = objects
            logger.info(f"Detected {len(objects)} objects")
        except Exception as e:
            logger.error(f"Object detection failed: {e}")
            metadata["objects"] = []
        
        # 2. Image Captioning
        try:
            logger.info("Generating caption...")
            captioner = get_image_captioner()
            caption = captioner.generate_caption(image)
            metadata["caption"] = caption
            logger.info(f"Caption: {caption}")
        except Exception as e:
            logger.error(f"Captioning failed: {e}")
            metadata["caption"] = ""
        
        # 3. OCR Text Extraction
        try:
            logger.info("Extracting text...")
            ocr = get_ocr_extractor()
            ocr_text = ocr.extract_text(image)
            text_blocks = ocr.extract_text_with_boxes(image)
            metadata["ocr_text"] = ocr_text
            metadata["text_blocks"] = text_blocks
            logger.info(f"Extracted {len(ocr_text)} characters")
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            metadata["ocr_text"] = ""
            metadata["text_blocks"] = []
        
        # 4. CLIP Embedding
        try:
            logger.info("Generating CLIP embedding...")
            embedder = get_clip_embedder()
            # Generate Image Embedding
            image_embedding = embedder.embed_image(image)
            
            # Generate Caption Embedding
            caption_embedding = embedder.embed_text(metadata.get("caption", ""))
            
            # Generate Objects Embedding
            objects = metadata.get("objects", [])
            object_names = [obj["class"] for obj in objects]
            if object_names:
                objects_text = "detected objects: " + ", ".join(sorted(list(set(object_names))))
            else:
                objects_text = ""
            objects_embedding = embedder.embed_text(objects_text)
            
            # Create Hybrid Vector (Average)
            hybrid_vector = (image_embedding + caption_embedding + objects_embedding) / 3.0
            
            # Normalize
            hybrid_vector = hybrid_vector / np.linalg.norm(hybrid_vector)
            
            # Store embedding as list for pgvector
            media.vector = hybrid_vector.tolist()
            logger.info("Hybrid embedding (Image + Caption + Objects) generated")
        except Exception as e:
            logger.error(f"CLIP embedding failed: {e}")
            raise  # This is critical, fail the job
        
        # Store metadata
        media.metadata_json = metadata
        media.status = "indexed"
        media.processed_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Successfully processed media {media_id}")
        
        return {
            "media_id": media_id,
            "status": "success",
            "metadata": metadata
        }
    
    except Exception as e:
        logger.error(f"Failed to process media {media_id}: {e}")
        
        # Update status to failed
        if media:
            media.status = "failed"
            media.error_message = str(e)
            db.commit()
        
        raise
    
    finally:
        db.close()


def cluster_images():
    """
    Background job to cluster all indexed images
    """
    from app.ml.clusterer import get_image_clusterer
    from app.models.cluster import Cluster
    
    db = SessionLocal()
    
    try:
        logger.info("Starting clustering job...")
        
        # Get all indexed media with embeddings
        media_list = db.query(Media).filter(
            Media.status == "indexed",
            Media.vector.isnot(None)
        ).all()
        
        if len(media_list) < 5:
            logger.warning("Not enough images for clustering")
            return
        
        # Extract embeddings and IDs
        embeddings = np.array([m.vector for m in media_list])
        media_ids = [m.id for m in media_list]
        
        logger.info(f"Clustering {len(media_list)} images...")
        
        # Run clustering
        clusterer = get_image_clusterer()
        labels, info = clusterer.cluster(embeddings)
        
        # Compute centroids
        centroids = clusterer.compute_centroids(embeddings, labels)
        
        # Update media with cluster assignments
        for i, media in enumerate(media_list):
            cluster_id = int(labels[i])
            if cluster_id != -1:
                media.cluster_id = cluster_id
        
        # Create or update cluster records
        for cluster_id, centroid in centroids.items():
            # Get member IDs
            member_ids = [
                media_ids[i] for i, label in enumerate(labels)
                if label == cluster_id
            ]
            
            # Check if cluster exists
            cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
            
            if cluster:
                cluster.member_ids = member_ids
                cluster.member_count = len(member_ids)
                cluster.centroid_vector = centroid.tolist()
            else:
                cluster = Cluster(
                    id=cluster_id,
                    cluster_type="general",
                    member_ids=member_ids,
                    member_count=len(member_ids),
                    centroid_vector=centroid.tolist()
                )
                db.add(cluster)
        
        db.commit()
        
        logger.info(f"Clustering complete: {info}")
        return info
    
    except Exception as e:
        logger.error(f"Clustering failed: {e}")
        raise
    
    finally:
        db.close()
