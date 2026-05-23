"""Clusters endpoints for retrieving cluster information."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.queue import enqueue_clustering_job
from find_api.core.storage import get_file_url
from find_api.routers.gallery import build_thumbnail_url
from find_api.models.cluster import Cluster
from find_api.models.media import Media

router = APIRouter()


@router.get("/clusters")
def get_clusters(db: Session = Depends(get_db)):
    """
    Get all clusters with member information

    Returns:
        List of clusters with metadata
    """
    clusters = db.query(Cluster).order_by(desc(Cluster.member_count), Cluster.id).all()

    result = []
    for cluster in clusters:
        # Get sample images from cluster
        sample_ids = (cluster.member_ids or [])[:5]
        sample_media = db.query(Media).filter(Media.id.in_(sample_ids)).all()

        samples = []
        for media in sample_media:
            try:
                url = get_file_url(media.minio_key)
            except Exception:
                url = None

            samples.append(
                {
                    "id": media.id,
                    "filename": media.filename,
                    "url": url,
                    "thumbnail_url": build_thumbnail_url(media.id),
                }
            )

        cluster_info = {
            "id": cluster.id,
            "type": cluster.cluster_type,
            "label": cluster.label,
            "description": cluster.description,
            "member_count": cluster.member_count,
            "created_at": cluster.created_at.isoformat()
            if cluster.created_at
            else None,
            "samples": samples,
        }

        result.append(cluster_info)

    return {
        "clusters": result,
        "total": len(result),
        "min_cluster_size": settings.MIN_CLUSTER_SIZE,
    }


@router.get("/cluster/{cluster_id}")
def get_cluster_detail(cluster_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific cluster

    Args:
        cluster_id: Cluster ID

    Returns:
        Cluster information with all members
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

    if not cluster:
        raise HTTPException(404, "Cluster not found")

    # Get all member media
    member_ids = cluster.member_ids or []
    members = db.query(Media).filter(Media.id.in_(member_ids)).all()

    member_list = []
    for media in members:
        try:
            url = get_file_url(media.minio_key)
        except Exception:
            url = None

        member_list.append(
            {
                "id": media.id,
                "filename": media.filename,
                "url": url,
                "thumbnail_url": build_thumbnail_url(media.id),
                "caption": media.metadata_json.get("caption", "")
                if media.metadata_json
                else "",
            }
        )

    return {
        "id": cluster.id,
        "type": cluster.cluster_type,
        "label": cluster.label,
        "description": cluster.description,
        "member_count": cluster.member_count,
        "created_at": cluster.created_at.isoformat() if cluster.created_at else None,
        "members": member_list,
    }


@router.post("/cluster/run")
def trigger_clustering(db: Session = Depends(get_db)):
    """
    Manually trigger clustering job

    Returns:
        Job information
    """
    indexed_count = (
        db.query(Media)
        .filter(Media.status == "indexed", Media.vector.isnot(None))
        .count()
    )
    if indexed_count < settings.MIN_CLUSTER_SIZE:
        message = (
            "Not enough indexed images for clustering "
            f"(found {indexed_count}, need at least {settings.MIN_CLUSTER_SIZE})."
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "current_count": indexed_count,
                "required_minimum": settings.MIN_CLUSTER_SIZE,
            },
        )
    return enqueue_clustering_job(reason="manual")
