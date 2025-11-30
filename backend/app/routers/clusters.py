"""
Clusters endpoint for retrieving cluster information
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.storage import get_file_url
from app.models.cluster import Cluster
from app.models.media import Media

router = APIRouter()


@router.get("/clusters")
async def get_clusters(db: Session = Depends(get_db)):
    """
    Get all clusters with member information

    Returns:
        List of clusters with metadata
    """
    clusters = db.query(Cluster).all()

    result = []
    for cluster in clusters:
        # Get sample images from cluster
        sample_media = (
            db.query(Media).filter(Media.id.in_(cluster.member_ids[:5])).all()
        )

        samples = []
        for media in sample_media:
            try:
                url = get_file_url(media.minio_key)
            except Exception:
                url = None

            samples.append({"id": media.id, "filename": media.filename, "url": url})

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

    return {"clusters": result, "total": len(result)}


@router.get("/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: int, db: Session = Depends(get_db)):
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
    members = db.query(Media).filter(Media.id.in_(cluster.member_ids)).all()

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
async def trigger_clustering(db: Session = Depends(get_db)):
    """
    Manually trigger clustering job

    Returns:
        Job information
    """
    from redis import Redis
    from rq import Queue
    from app.core.config import settings
    from app.workers.jobs import cluster_images

    redis_conn = Redis.from_url(settings.REDIS_URL)
    task_queue = Queue(connection=redis_conn)

    job = task_queue.enqueue(cluster_images, job_timeout=600)

    return {"message": "Clustering job started", "job_id": job.id}
