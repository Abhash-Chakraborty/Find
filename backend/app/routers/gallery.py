"""
Gallery endpoint for browsing images
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional

from app.core.database import get_db
from app.core.storage import get_file_url, delete_file
from app.models.media import Media
from app.models.cluster import Cluster

router = APIRouter()


@router.get("/gallery")
async def get_gallery(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    liked: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Get paginated list of images
    
    Args:
        skip: Number of records to skip
        limit: Max number of records to return
        status: Filter by status (pending, processing, indexed, failed)
        
    Returns:
        Paginated list of media records
    """
    # Build query
    query = db.query(Media)
    
    if status:
        query = query.filter(Media.status == status)
    if liked is not None:
        query = query.filter(Media.liked == liked)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    media_list = query.order_by(desc(Media.created_at)).offset(skip).limit(limit).all()
    
    # Build response
    items = []
    for media in media_list:
        item = {
            "id": media.id,
            "filename": media.filename,
            "status": media.status,
            "created_at": media.created_at.isoformat() if media.created_at else None,
            "processed_at": media.processed_at.isoformat() if media.processed_at else None,
            "width": media.width,
            "height": media.height,
            "file_size": media.file_size,
            "cluster_id": media.cluster_id,
            "minio_key": media.minio_key,
            "liked": media.liked,
        }
        
        # Add thumbnail URL
        try:
            item["url"] = get_file_url(media.minio_key)
        except:
            item["url"] = None
        
        # Add metadata if indexed
        if media.status == "indexed" and media.metadata_json:
            item["caption"] = media.metadata_json.get("caption", "")
            item["objects"] = media.metadata_json.get("objects", [])
            item["has_text"] = bool(media.metadata_json.get("ocr_text", ""))
        
        items.append(item)
    
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/image/{media_id}")
async def get_image_detail(media_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific image
    
    Args:
        media_id: Media record ID
        
    Returns:
        Complete media information including metadata
    """
    media = db.query(Media).filter(Media.id == media_id).first()
    
    if not media:
        from fastapi import HTTPException
        raise HTTPException(404, "Image not found")
    
    # Build response
    response = {
        "id": media.id,
        "filename": media.filename,
        "file_hash": media.file_hash,
        "status": media.status,
        "content_type": media.content_type,
        "file_size": media.file_size,
        "width": media.width,
        "height": media.height,
        "created_at": media.created_at.isoformat() if media.created_at else None,
        "processed_at": media.processed_at.isoformat() if media.processed_at else None,
        "cluster_id": media.cluster_id,
        "metadata": media.metadata_json,
        "exif": media.exif_json,
        "error": media.error_message,
        "liked": media.liked,
    }
    
    # Add presigned URL
    try:
        response["url"] = get_file_url(media.minio_key)
    except:
        response["url"] = None
    
    return response


@router.post("/image/{media_id}/like")
async def toggle_like(media_id: int, db: Session = Depends(get_db)):
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    media.liked = not media.liked
    db.commit()
    db.refresh(media)

    return {"id": media.id, "liked": media.liked}


@router.delete("/image/{media_id}")
async def delete_image(media_id: int, db: Session = Depends(get_db)):
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    try:
        delete_file(media.minio_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Failed to delete file from storage: {exc}") from exc

    db.delete(media)
    db.flush()

    clusters = db.query(Cluster).filter(Cluster.member_ids.contains([media_id])).all()
    for cluster in clusters:
        current_members = cluster.member_ids or []
        if media_id in current_members:
            cluster.member_ids = [member_id for member_id in current_members if member_id != media_id]
            cluster.member_count = len(cluster.member_ids)

    db.commit()

    return {"message": "Image deleted", "id": media_id}
