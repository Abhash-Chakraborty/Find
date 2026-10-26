"""Clusters endpoints for retrieving cluster information."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import (
    get_admin_user,
    get_required_user,
    scope_media_query,
)
from find_api.core.media_scope import browsable_media
from find_api.core.queue import enqueue_clustering_job
from find_api.models.cluster import Cluster
from find_api.models.media import Media
from find_api.models.user import User
from find_api.routers.gallery import build_original_url, build_thumbnail_url

router = APIRouter()

# Member ids per visibility query. Keeps each IN list well under SQLite's
# bound-parameter limit on large libraries.
MEMBER_LOOKUP_BATCH = 5000


class ClusterUpdateRequest(BaseModel):
    """Editable cluster metadata."""

    label: str | None = Field(default=None, max_length=255)


def _cluster_payload(cluster: Cluster, *, members: list | None = None):
    payload = {
        "id": cluster.id,
        "type": cluster.cluster_type,
        "label": cluster.label,
        "description": cluster.description,
        "member_count": cluster.member_count,
        "created_at": cluster.created_at.isoformat() if cluster.created_at else None,
    }
    if members is not None:
        payload["members"] = members
    return payload


@router.get("/clusters")
def get_clusters(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_required_user),
):
    """
    Get all clusters with member information

    Returns:
        List of clusters with metadata
    """
    clusters = db.query(Cluster).order_by(desc(Cluster.member_count), Cluster.id).all()

    # Look up every member's visibility at once instead of two queries per
    # cluster. Visible = browsable AND (in shared mode) owned by the caller.
    all_member_ids = sorted(
        {media_id for cluster in clusters for media_id in cluster.member_ids or []}
    )
    visible_filenames: dict[int, str] = {}
    for start in range(0, len(all_member_ids), MEMBER_LOOKUP_BATCH):
        batch = all_member_ids[start : start + MEMBER_LOOKUP_BATCH]
        rows = scope_media_query(
            db.query(Media.id, Media.filename).filter(
                Media.id.in_(batch), *browsable_media()
            ),
            user,
        ).all()
        visible_filenames.update({row.id: row.filename for row in rows})

    result = []
    for cluster in clusters:
        visible_ids = [
            media_id
            for media_id in cluster.member_ids or []
            if media_id in visible_filenames
        ]
        visible_member_count = len(visible_ids)
        if visible_member_count == 0:
            continue

        samples = [
            {
                "id": media_id,
                "filename": visible_filenames[media_id],
                "url": build_original_url(media_id),
                "thumbnail_url": build_thumbnail_url(media_id),
            }
            for media_id in visible_ids[:5]
        ]

        cluster_info = _cluster_payload(cluster)
        cluster_info["member_count"] = visible_member_count
        cluster_info["samples"] = samples

        result.append(cluster_info)

    return {
        "clusters": result,
        "total": len(result),
        "min_cluster_size": settings.MIN_CLUSTER_SIZE,
    }


@router.get("/cluster/{cluster_id}")
def get_cluster_detail(
    cluster_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_required_user),
):
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
    members = scope_media_query(
        db.query(Media).filter(Media.id.in_(member_ids), *browsable_media()),
        user,
    ).all()

    # A regular user who owns none of this cluster's media should not see it.
    if user is not None and user.role != "admin" and not members:
        raise HTTPException(404, "Cluster not found")

    member_list = []
    for media in members:
        url = build_original_url(media.id)
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

    if not member_list:
        raise HTTPException(404, "Cluster not found")

    payload = _cluster_payload(cluster, members=member_list)
    payload["member_count"] = len(member_list)
    return payload


@router.patch("/cluster/{cluster_id}")
def update_cluster(
    cluster_id: int,
    payload: ClusterUpdateRequest,
    db: Session = Depends(get_db),
    _admin: User | None = Depends(get_admin_user),
):
    """Update editable cluster metadata.

    Cluster labels are shared across every uploader's view, so editing is
    admin-only in shared mode (no-op restriction in local mode).
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

    if not cluster:
        raise HTTPException(404, "Cluster not found")

    label = payload.label.strip() if payload.label else None
    cluster.label = label or None
    db.commit()
    db.refresh(cluster)

    return _cluster_payload(cluster)


@router.post("/cluster/run")
def trigger_clustering(
    db: Session = Depends(get_db),
    _admin: User | None = Depends(get_admin_user),
):
    """
    Manually trigger clustering job

    Rebuilds clusters across every uploader's media, so this is admin-only
    in shared mode (no-op restriction in local mode).

    Returns:
        Job information
    """
    indexed_count = (
        db.query(Media)
        .filter(
            Media.status == "indexed",
            Media.vector.isnot(None),
            Media.is_hidden.is_(False),
        )
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
