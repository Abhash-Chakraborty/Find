"""
People router - API endpoints for person groups and face clusters
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, ConfigDict
from typing import List, Optional

from find_api.core.database import get_db
from find_api.core.config import settings
from find_api.core.dependencies import get_admin_user, get_required_user
from find_api.core.queue import get_task_queue
from find_api.routers.gallery import build_thumbnail_url
from find_api.models.face import Face
from find_api.models.media import Media
from find_api.models.person import Person
from find_api.models.user import User
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Pydantic schemas (what the API returns) ──────────────────────────────────


class PersonResponse(BaseModel):
    """What we send back when listing people"""

    id: int
    name: Optional[str]
    face_count: int
    # Sample image IDs to show thumbnails in the UI
    sample_media_ids: List[int]
    thumbnail_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PersonUpdate(BaseModel):
    """What the user sends when naming a person"""

    name: str


class PersonImageFace(BaseModel):
    """Face data for one image in a person group."""

    id: int
    bounding_box: dict
    confidence: float


class PersonImageResponse(BaseModel):
    """Image shown inside a person group."""

    media_id: int
    filename: str
    thumbnail_url: Optional[str] = None
    faces: List[PersonImageFace]


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/people", response_model=List[PersonResponse])
def list_people(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """
    Get all person groups with face counts and sample images.
    This powers the People page in the UI.
    """
    # In shared mode a regular user only sees faces in media they uploaded.
    scope_user_id = user.id if (user is not None and user.role != "admin") else None

    persons = db.query(Person).order_by(Person.created_at.desc()).all()

    result = []
    for person in persons:
        # Count how many faces belong to this person
        count_query = (
            db.query(func.count(Face.id))
            .join(Media, Media.id == Face.media_id)
            .filter(Face.person_id == person.id, Media.is_hidden.is_(False))
        )
        if scope_user_id is not None:
            count_query = count_query.filter(Media.uploader_user_id == scope_user_id)
        face_count = count_query.scalar()

        # Get up to 4 sample media IDs for thumbnail preview
        sample_query = (
            db.query(Face.media_id)
            .join(Media, Media.id == Face.media_id)
            .filter(Face.person_id == person.id)
            .filter(Media.is_hidden.is_(False))
        )
        if scope_user_id is not None:
            sample_query = sample_query.filter(Media.uploader_user_id == scope_user_id)
        sample_faces = sample_query.distinct().limit(4).all()
        sample_media_ids = [f.media_id for f in sample_faces]
        # Skip groups with no visible faces. face_count/sample_media_ids are
        # already scoped to the caller in shared mode, so this also hides
        # person groups the user has none of their own media in.
        if face_count == 0 or not sample_media_ids:
            continue

        thumbnail_url = (
            build_thumbnail_url(sample_media_ids[0]) if sample_media_ids else None
        )

        result.append(
            PersonResponse(
                id=person.id,
                name=person.name,
                face_count=face_count,
                sample_media_ids=sample_media_ids,
                thumbnail_url=thumbnail_url,
            )
        )

    return result


@router.get("/people/{person_id}/images")
def get_person_images(
    person_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """
    Get all images that contain a specific person.
    Used when user clicks on a person group.
    """
    scope_user_id = user.id if (user is not None and user.role != "admin") else None

    # Check person exists
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # Get all unique media IDs where this person appears
    face_query = (
        db.query(
            Face.id,
            Face.media_id,
            Media.filename,
            Face.bounding_box,
            Face.confidence,
        )
        .join(Media, Media.id == Face.media_id)
        .filter(Face.person_id == person_id, Media.is_hidden.is_(False))
    )
    if scope_user_id is not None:
        face_query = face_query.filter(Media.uploader_user_id == scope_user_id)
    face_rows = face_query.order_by(Media.created_at.desc()).all()

    # A regular user who owns none of this person's media should not learn it exists.
    if scope_user_id is not None and not face_rows:
        raise HTTPException(status_code=404, detail="Person not found")

    # Group by media_id
    images = {}
    for row in face_rows:
        if row.media_id not in images:
            images[row.media_id] = {
                "media_id": row.media_id,
                "filename": row.filename,
                "thumbnail_url": build_thumbnail_url(row.media_id),
                "faces": [],
            }
        images[row.media_id]["faces"].append(
            {
                "id": row.id,
                "bounding_box": row.bounding_box,
                "confidence": row.confidence,
            }
        )

    return {
        "person_id": person_id,
        "person_name": person.name,
        "images": list(images.values()),
    }


@router.patch("/people/{person_id}")
def update_person_name(
    person_id: int,
    body: PersonUpdate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """
    Let the user name a person group e.g. 'Alice' or 'Dad'.
    This is the only manual step in the whole pipeline.
    """
    scope_user_id = user.id if (user is not None and user.role != "admin") else None

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # A regular user may only rename a person who appears in their own media.
    if scope_user_id is not None:
        owns_face = (
            db.query(Face.id)
            .join(Media, Media.id == Face.media_id)
            .filter(
                Face.person_id == person_id,
                Media.uploader_user_id == scope_user_id,
            )
            .first()
        )
        if owns_face is None:
            raise HTTPException(status_code=404, detail="Person not found")

    clean_name = body.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if len(clean_name) > 255:
        raise HTTPException(status_code=400, detail="Name is too long")
    person.name = clean_name
    db.commit()
    db.refresh(person)
    return {
        "id": person.id,
        "name": person.name,
        "message": f"Person named '{person.name}' successfully",
    }


@router.post("/people/cluster")
def trigger_face_clustering(
    _admin: Optional[User] = Depends(get_admin_user),
):
    """
    Manually trigger face clustering job.
    Groups all detected faces into person groups.

    This rebuilds person groups across every uploader's faces, so it is
    restricted to admins in shared mode (no-op restriction in local mode).
    """
    try:
        from find_api.workers.jobs import cluster_faces

        job = get_task_queue().enqueue(
            cluster_faces,
            job_timeout=settings.WORKER_TIMEOUT,
            result_ttl=300,
        )
        return {
            "job_id": job.id,
            "message": "Face clustering job queued",
            "status": "queued",
            "enqueued": True,
        }
    except Exception:
        logger.exception("Face clustering failed")
        raise HTTPException(
            status_code=500,
            detail="Face clustering failed",
        )
