"""Tests for people API thumbnail URL fields."""

import hashlib
from datetime import datetime, timezone

from find_api.models.face import Face
from find_api.models.media import Media
from find_api.models.person import Person


def _seed_person_group(db, *, name: str = "Alice") -> tuple[Person, Media]:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)

    media = Media(
        file_hash=hashlib.sha256(name.encode()).hexdigest(),
        minio_key=f"images/test/{name.lower()}.jpg",
        filename=f"{name.lower()}.jpg",
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=800,
        height=600,
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    face = Face(
        media_id=media.id,
        bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
        confidence=0.95,
        person_id=person.id,
    )
    db.add(face)
    db.commit()

    return person, media


def test_people_list_includes_thumbnail_url(client, db):
    _person, media = _seed_person_group(db)

    body = client.get("/api/people").json()

    assert body[0]["thumbnail_url"] == f"/api/image/{media.id}/thumbnail"


def test_people_images_include_thumbnail_url_and_face_ids(client, db):
    person, media = _seed_person_group(db)

    body = client.get(f"/api/people/{person.id}/images").json()

    assert body["images"][0]["thumbnail_url"] == f"/api/image/{media.id}/thumbnail"
    assert body["images"][0]["faces"][0]["id"]
