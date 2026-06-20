from typing import Any, List, Optional
from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from find_api.core.database import get_db
from find_api.models.feedback import PersonFeedback, GeneralFeedback
from find_api.models.person import Person
from find_api.models.face import Face
from find_api.models.media import Media

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["feedback"])


# ─── Helpers ───────────────────────────────────────────────────────────────


def _validate_rating(rating: Optional[int]) -> None:
    if rating is None:
        raise HTTPException(status_code=400, detail="rating is required")
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")


# ─── Pydantic Schemas ─────────────────────────────────────────────────────


class PersonFeedbackRequest(BaseModel):
    """Request body for person cluster feedback"""

    feedback_type: str  # "split", "merge", "wrong_person", "correct"
    face_ids: List[int]
    target_person_id: Optional[int] = None
    user_reason: Optional[str] = None


class PersonFeedbackResponse(BaseModel):
    """Response from person feedback endpoint"""

    id: int
    feedback_type: str
    source_person_id: int
    target_person_id: Optional[int]
    face_ids: List[int]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneralFeedbackRequest(BaseModel):
    """Request body for general feedback and correction data."""

    feedback_type: str
    media_id: Optional[int] = None
    person_id: Optional[int] = None
    rating: Optional[int] = None  # 1-5
    rating_reason: Optional[str] = None
    corrected_caption: Optional[str] = None
    corrected_objects: Optional[List[str]] = None


class GeneralFeedbackResponse(BaseModel):
    """Response from general feedback endpoint"""

    id: int
    feedback_type: str
    media_id: Optional[int]
    person_id: Optional[int]
    rating: Optional[int]
    rating_reason: Optional[str]
    extra_metadata: Optional[dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Person Cluster Feedback Endpoints ────────────────────────────────────


@router.post(
    "/people/{person_id}/feedback/split", response_model=PersonFeedbackResponse
)
def submit_split_feedback(
    person_id: int,
    body: PersonFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Mark faces to be split into a separate person group.

    If `face_ids` contains face IDs to move to new person:
    - Create a new Person (unnamed)
    - Move those faces from source_person_id to new person
    - Log feedback record
    """
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if not body.face_ids:
        raise HTTPException(status_code=400, detail="face_ids cannot be empty")

    # Verify all faces belong to this person
    faces = (
        db.query(Face)
        .filter(Face.person_id == person_id, Face.id.in_(body.face_ids))
        .all()
    )

    if len(faces) != len(body.face_ids):
        raise HTTPException(
            status_code=400, detail="One or more face_ids do not belong to this person"
        )

    total_faces = db.query(Face).filter(Face.person_id == person_id).count()
    if len(faces) >= total_faces:
        raise HTTPException(
            status_code=400,
            detail="Cannot split every face from a person group",
        )

    try:
        # Create new person (unnamed)
        new_person = Person(name=None)
        db.add(new_person)
        db.flush()  # Get the new person ID without committing

        # Move faces to new person
        for face_id in body.face_ids:
            face = db.query(Face).filter(Face.id == face_id).first()
            if face:
                face.person_id = new_person.id

        # Record feedback
        feedback = PersonFeedback(
            feedback_type="split",
            source_person_id=person_id,
            target_person_id=new_person.id,
            face_ids=body.face_ids,
            user_reason=body.user_reason,
            status="applied",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Split person {person_id}: moved {len(body.face_ids)} faces to new person {new_person.id}"
        )

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to split person cluster")
        raise HTTPException(status_code=500, detail="Split failed")


@router.post(
    "/people/{person_id}/feedback/merge/{target_person_id}",
    response_model=PersonFeedbackResponse,
)
def submit_merge_feedback(
    person_id: int,
    target_person_id: int,
    body: PersonFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Merge two person groups into one.
    All faces from source_person_id are moved to target_person_id.
    Source person is NOT deleted (in case user wants to undo).
    """
    source_person = db.query(Person).filter(Person.id == person_id).first()
    if not source_person:
        raise HTTPException(status_code=404, detail="Source person not found")

    target_person = db.query(Person).filter(Person.id == target_person_id).first()
    if not target_person:
        raise HTTPException(status_code=404, detail="Target person not found")

    if person_id == target_person_id:
        raise HTTPException(status_code=400, detail="Cannot merge person with itself")

    try:
        # Get all faces in source person
        faces = db.query(Face).filter(Face.person_id == person_id).all()
        face_ids = [f.id for f in faces]

        # Move all faces to target person
        for face in faces:
            face.person_id = target_person_id

        # Record feedback
        feedback = PersonFeedback(
            feedback_type="merge",
            source_person_id=person_id,
            target_person_id=target_person_id,
            face_ids=face_ids,
            user_reason=body.user_reason,
            status="applied",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Merged person {person_id} into {target_person_id}: "
            f"moved {len(face_ids)} faces"
        )

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to merge persons")
        raise HTTPException(status_code=500, detail="Merge failed")


@router.post(
    "/people/{person_id}/feedback/wrong-person", response_model=PersonFeedbackResponse
)
def submit_wrong_person_feedback(
    person_id: int,
    body: PersonFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Mark specific face(s) as belonging to a different person.
    Creates a new unnamed person and moves the face(s) there.
    """
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if not body.face_ids:
        raise HTTPException(status_code=400, detail="face_ids cannot be empty")

    # Verify faces belong to this person
    faces = (
        db.query(Face)
        .filter(Face.person_id == person_id, Face.id.in_(body.face_ids))
        .all()
    )

    if len(faces) != len(body.face_ids):
        raise HTTPException(
            status_code=400, detail="One or more faces don't belong to this person"
        )

    total_faces = db.query(Face).filter(Face.person_id == person_id).count()
    if len(faces) >= total_faces:
        raise HTTPException(
            status_code=400,
            detail="Cannot move every face out of a person group",
        )

    try:
        # Create new unnamed person
        new_person = Person(name=None)
        db.add(new_person)
        db.flush()

        # Move faces to new person
        for face in faces:
            face.person_id = new_person.id

        # Record feedback
        feedback = PersonFeedback(
            feedback_type="wrong_person",
            source_person_id=person_id,
            target_person_id=new_person.id,
            face_ids=body.face_ids,
            user_reason=body.user_reason,
            status="applied",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Marked {len(body.face_ids)} faces as wrong person for {person_id}"
        )

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to mark wrong person")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.post(
    "/people/{person_id}/feedback/correct", response_model=PersonFeedbackResponse
)
def submit_correct_feedback(
    person_id: int,
    body: PersonFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Mark person cluster as correctly grouped (positive feedback).
    No changes are made; just records that user approves this grouping.
    """
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    try:
        # Get all faces in this person if not specified
        face_ids = body.face_ids if body.face_ids else []
        if not face_ids:
            faces = db.query(Face.id).filter(Face.person_id == person_id).all()
            face_ids = [f.id for f in faces]

        feedback = PersonFeedback(
            feedback_type="correct",
            source_person_id=person_id,
            face_ids=face_ids,
            user_reason=body.user_reason,
            status="applied",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(f"Marked person {person_id} as correctly grouped")

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to submit correct feedback")
        raise HTTPException(status_code=500, detail="Operation failed")


# ─── General Feedback Endpoints ────────────────────────────────────────────


@router.post("/feedback/search-rating", response_model=GeneralFeedbackResponse)
def rate_search_result(
    body: GeneralFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Rate the relevance of a search result (1-5 stars).
    """
    if body.media_id is None:
        raise HTTPException(
            status_code=400, detail="media_id is required for search rating"
        )

    media = db.query(Media).filter(Media.id == body.media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    _validate_rating(body.rating)

    try:
        feedback = GeneralFeedback(
            feedback_type="search_rating",
            media_id=body.media_id,
            rating=body.rating,
            rating_reason=body.rating_reason,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Search rating recorded for media {body.media_id}: {body.rating} stars"
        )

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to record search rating")
        raise HTTPException(status_code=500, detail="Failed to save rating")


@router.post("/feedback/caption-rating", response_model=GeneralFeedbackResponse)
def rate_caption(
    body: GeneralFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Rate the accuracy of an image caption (1-5 stars).
    """
    if body.media_id is None:
        raise HTTPException(
            status_code=400, detail="media_id is required for caption rating"
        )

    media = db.query(Media).filter(Media.id == body.media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    _validate_rating(body.rating)

    try:
        feedback = GeneralFeedback(
            feedback_type="caption_rating",
            media_id=body.media_id,
            rating=body.rating,
            rating_reason=body.rating_reason,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Caption rating recorded for media {body.media_id}: {body.rating} stars"
        )

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to record caption rating")
        raise HTTPException(status_code=500, detail="Failed to save rating")


@router.post("/feedback/object-rating", response_model=GeneralFeedbackResponse)
def rate_object_detection(
    body: GeneralFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Rate the accuracy of object detection (1-5 stars).
    """
    if body.media_id is None:
        raise HTTPException(
            status_code=400, detail="media_id is required for object rating"
        )

    media = db.query(Media).filter(Media.id == body.media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    _validate_rating(body.rating)

    try:
        feedback = GeneralFeedback(
            feedback_type="object_rating",
            media_id=body.media_id,
            rating=body.rating,
            rating_reason=body.rating_reason,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Object rating recorded for media {body.media_id}: {body.rating} stars"
        )

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to record object rating")
        raise HTTPException(status_code=500, detail="Failed to save rating")


@router.post("/feedback/caption-correction", response_model=GeneralFeedbackResponse)
def submit_caption_correction(
    body: GeneralFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Store user-edited caption text for future local personalization/training.
    """
    if body.media_id is None:
        raise HTTPException(
            status_code=400, detail="media_id is required for caption correction"
        )

    corrected_caption = (body.corrected_caption or "").strip()
    if not corrected_caption:
        raise HTTPException(status_code=400, detail="corrected_caption is required")

    media = db.query(Media).filter(Media.id == body.media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    metadata = media.metadata_json or {}

    try:
        feedback = GeneralFeedback(
            feedback_type="caption_correction",
            media_id=body.media_id,
            rating_reason=body.rating_reason,
            extra_metadata={
                "original_caption": metadata.get("caption") or "",
                "corrected_caption": corrected_caption,
            },
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info("Caption correction recorded for media %s", body.media_id)

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to record caption correction")
        raise HTTPException(status_code=500, detail="Failed to save correction")


@router.post("/feedback/object-correction", response_model=GeneralFeedbackResponse)
def submit_object_correction(
    body: GeneralFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Store user-corrected object labels for future local personalization/training.
    """
    if body.media_id is None:
        raise HTTPException(
            status_code=400, detail="media_id is required for object correction"
        )

    corrected_objects = [
        label.strip()
        for label in (body.corrected_objects or [])
        if label and label.strip()
    ]
    if not corrected_objects:
        raise HTTPException(status_code=400, detail="corrected_objects is required")

    media = db.query(Media).filter(Media.id == body.media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    metadata = media.metadata_json or {}
    original_objects = [
        obj.get("class")
        for obj in metadata.get("objects", [])
        if isinstance(obj, dict) and obj.get("class")
    ]

    try:
        feedback = GeneralFeedback(
            feedback_type="object_correction",
            media_id=body.media_id,
            rating_reason=body.rating_reason,
            extra_metadata={
                "original_objects": original_objects,
                "corrected_objects": corrected_objects,
            },
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info("Object correction recorded for media %s", body.media_id)

        return feedback
    except Exception:
        db.rollback()
        logger.exception("Failed to record object correction")
        raise HTTPException(status_code=500, detail="Failed to save correction")


# ─── Analytics Endpoints ──────────────────────────────────────────────────


@router.get("/feedback/stats")
def get_feedback_stats(db: Session = Depends(get_db)):
    """
    Get aggregate feedback statistics for analytics.
    """
    try:
        from sqlalchemy import func

        person_feedback_count = db.query(func.count(PersonFeedback.id)).scalar() or 0
        person_feedback_applied = (
            db.query(func.count(PersonFeedback.id))
            .filter(PersonFeedback.status == "applied")
            .scalar()
            or 0
        )

        general_feedback_count = db.query(func.count(GeneralFeedback.id)).scalar() or 0

        avg_search_rating = (
            db.query(func.avg(GeneralFeedback.rating))
            .filter(GeneralFeedback.feedback_type == "search_rating")
            .scalar()
        )

        avg_caption_rating = (
            db.query(func.avg(GeneralFeedback.rating))
            .filter(GeneralFeedback.feedback_type == "caption_rating")
            .scalar()
        )

        avg_object_rating = (
            db.query(func.avg(GeneralFeedback.rating))
            .filter(GeneralFeedback.feedback_type == "object_rating")
            .scalar()
        )

        return {
            "person_feedback": {
                "total": person_feedback_count,
                "applied": person_feedback_applied,
            },
            "general_feedback": {
                "total": general_feedback_count,
                "search_avg_rating": round(avg_search_rating, 2)
                if avg_search_rating
                else None,
                "caption_avg_rating": round(avg_caption_rating, 2)
                if avg_caption_rating
                else None,
                "object_avg_rating": round(avg_object_rating, 2)
                if avg_object_rating
                else None,
            },
        }
    except Exception:
        logger.exception("Failed to get feedback stats")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


@router.get("/people/feedback", response_model=List[PersonFeedbackResponse])
def list_person_feedback(
    person_id: Optional[int] = None,
    feedback_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    List all person feedback entries, optionally filtered by person or type.
    """
    query = db.query(PersonFeedback)

    if person_id:
        query = query.filter(PersonFeedback.source_person_id == person_id)

    if feedback_type:
        query = query.filter(PersonFeedback.feedback_type == feedback_type)

    feedback_list = query.order_by(PersonFeedback.created_at.desc()).all()

    return feedback_list
