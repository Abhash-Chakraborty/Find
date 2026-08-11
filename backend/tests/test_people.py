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


def test_people_list_counts_and_samples_are_not_mixed_between_people(client, db):
    person_a, media_1 = _seed_person_group(db, name="A")
    person_b, media_3 = _seed_person_group(db, name="B")

    # A second media for person A, plus a second face of A's in media_1 —
    # face_count should total all faces (3), sample_media_ids only the
    # 2 distinct media.
    media_2 = Media(
        file_hash=hashlib.sha256("a-second".encode()).hexdigest(),
        minio_key="images/test/a-second.jpg",
        filename="a-second.jpg",
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=800,
        height=600,
        is_hidden=False,
        vault_state="visible",
        created_at=datetime.now(timezone.utc),
    )
    db.add(media_2)
    db.commit()
    db.refresh(media_2)

    db.add_all(
        [
            Face(
                media_id=media_1.id,
                person_id=person_a.id,
                bounding_box={"x1": 20, "y1": 20, "x2": 30, "y2": 30},
                confidence=0.9,
            ),
            Face(
                media_id=media_2.id,
                person_id=person_a.id,
                bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                confidence=0.9,
            ),
        ]
    )
    db.commit()

    body = client.get("/api/people").json()
    by_id = {item["id"]: item for item in body}

    assert by_id[person_a.id]["face_count"] == 3
    assert set(by_id[person_a.id]["sample_media_ids"]) == {media_1.id, media_2.id}
    assert by_id[person_b.id]["face_count"] == 1
    assert by_id[person_b.id]["sample_media_ids"] == [media_3.id]


def test_people_list_query_count_does_not_grow_with_people(client, db):
    """The point of the batching: cost must not scale with N.

    Asserting the response shape alone would not have caught the original
    1 + 2N pattern, since it returned correct data — it was only slow. This
    fails if anyone reintroduces a per-person query.
    """
    from sqlalchemy import event

    engine = db.get_bind()

    def count_selects_for(batch: str, person_count: int) -> int:
        # Names are hashed into file_hash, which is unique, so each batch needs
        # its own prefix rather than restarting the counter.
        for index in range(person_count):
            _seed_person_group(db, name=f"{batch}{index}")

        statements: list[str] = []

        def record(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            assert client.get("/api/people").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", record)
        return len(statements)

    few = count_selects_for("Few", 3)
    many = count_selects_for("Many", 20)

    # Constant, not merely "fewer": 23 people must cost the same as 3.
    assert few == many, (
        f"query count grew with the number of people: {few} -> {many}; "
        "a per-person query has been reintroduced"
    )
