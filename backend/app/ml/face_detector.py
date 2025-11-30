"""
Face detection and recognition using InsightFace (AntelopeV2)
"""
import insightface
from insightface.app import FaceAnalysis
from PIL import Image
import numpy as np
from typing import List, Dict, Union
import logging
import cv2

from app.core.config import settings
from app.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class FaceDetector:
    """Detect and recognize faces using InsightFace"""
    
    def __init__(self):
        self.manager = get_model_manager()
        logger.info("FaceDetector initialized for model: antelopev2")
    
    def _load_model(self):
        """Loader function for ModelManager"""
        logger.info("Loading InsightFace model: antelopev2")
        
        # providers: ['CUDAExecutionProvider'] if GPU else ['CPUExecutionProvider']
        providers = ['CUDAExecutionProvider'] if settings.USE_GPU else ['CPUExecutionProvider']
        
        # Initialize FaceAnalysis with antelopev2
        app = FaceAnalysis(name='antelopev2', providers=providers)
        app.prepare(ctx_id=0 if settings.USE_GPU else -1, det_size=(640, 640))
        
        return app
    
    def detect_faces(self, image: Union[Image.Image, np.ndarray]) -> List[Dict]:
        """
        Detect faces in image
        """
        try:
            if isinstance(image, Image.Image):
                # Convert PIL to BGR numpy array (cv2 format)
                image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            app = self.manager.get_model("insightface", self._load_model)
            
            faces = app.get(image)
            
            results = []
            for face in faces:
                # Bounding box
                bbox = face.bbox.astype(int).flatten()
                
                # Landmarks (5 points)
                kps = face.kps.astype(int)
                
                # Embedding (512-dim for antelopev2)
                embedding = face.embedding
                if embedding is not None:
                    embedding = embedding.tolist()
                
                # Gender/Age (if available in model)
                gender = getattr(face, 'gender', None)
                age = getattr(face, 'age', None)
                
                results.append({
                    "bbox": {
                        "x1": int(bbox[0]),
                        "y1": int(bbox[1]),
                        "x2": int(bbox[2]),
                        "y2": int(bbox[3])
                    },
                    "confidence": float(face.det_score),
                    "landmarks": kps.tolist(),
                    "embedding": embedding,
                    "gender": int(gender) if gender is not None else None,
                    "age": int(age) if age is not None else None
                })
            
            logger.info(f"Detected {len(results)} faces")
            return results
        
        except Exception as e:
            logger.error(f"Failed to detect faces: {e}")
            raise


# Global instance
_face_detector = None


def get_face_detector() -> FaceDetector:
    """Get or create global face detector instance"""
    global _face_detector
    if _face_detector is None:
        _face_detector = FaceDetector()
    return _face_detector
