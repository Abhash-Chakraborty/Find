"""Tests for people API thumbnail URL fields."""

import hashlib
from datetime import datetime, timezone

from find_api.models.face import Face
from find_api.models.media import Media
from find_api.models.person import Person


def _seed_person_group(
    db, *, name: str = "Alice", is_hidden: bool = False
) -> tuple[Person, Media]:
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
        is_hidden=is_hidden,
        vault_state="hidden_encrypted" if is_hidden else "visible",
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


def test_people_list_excludes_groups_with_only_hidden_media(client, db):
    hidden_person, _hidden_media = _seed_person_group(db, name="Hidden", is_hidden=True)
    visible_person, visible_media = _seed_person_group(db, name="Visible")

    body = client.get("/api/people").json()
    person_ids = [item["id"] for item in body]

    assert visible_person.id in person_ids
    assert hidden_person.id not in person_ids
    listed = next(item for item in body if item["id"] == visible_person.id)
    assert listed["thumbnail_url"] == f"/api/image/{visible_media.id}/thumbnail"


def test_people_images_omit_hidden_media_faces(client, db):
    person, _visible_media = _seed_person_group(db, name="Mixed")

    hidden_media = Media(
        file_hash=hashlib.sha256("mixed-hidden".encode()).hexdigest(),
        minio_key="images/test/mixed-hidden.jpg",
        filename="mixed-hidden.jpg",
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=800,
        height=600,
        is_hidden=True,
        vault_state="hidden_encrypted",
        created_at=datetime.now(timezone.utc),
    )
    db.add(hidden_media)
    db.commit()
    db.refresh(hidden_media)

    hidden_face = Face(
        media_id=hidden_media.id,
        bounding_box={"x1": 1, "y1": 1, "x2": 12, "y2": 12},
        confidence=0.9,
        person_id=person.id,
    )
    db.add(hidden_face)
    db.commit()

    body = client.get(f"/api/people/{person.id}/images").json()
    media_ids = [item["media_id"] for item in body["images"]]

    assert hidden_media.id not in media_ids
