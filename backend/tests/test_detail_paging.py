"""Paging for the person, cluster and album detail endpoints."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from find_api.core.paging import DETAIL_PAGE_MAX
from find_api.models.cluster import Cluster
from find_api.models.face import Face
from find_api.models.media import Media
from find_api.models.person import Person

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _seed_media(db, filename: str, *, minutes: int = 0) -> Media:
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=800,
        height=600,
        vault_state="visible",
        created_at=BASE_TIME + timedelta(minutes=minutes),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _add_face(db, media: Media, person: Person) -> Face:
    face = Face(
        media_id=media.id,
        bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
        confidence=0.9,
        person_id=person.id,
    )
    db.add(face)
    db.commit()
    return face


class TestPersonImages:
    def test_pages_by_photo_newest_first(self, client, db):
        person = Person(name="Ana")
        db.add(person)
        db.commit()
        photos = [_seed_media(db, f"ana-{i}.jpg", minutes=i) for i in range(5)]
        for photo in photos:
            _add_face(db, photo, person)
        # Two faces of the same person in one photo still make one item.
        _add_face(db, photos[4], person)

        first = client.get(
            f"/api/people/{person.id}/images", params={"limit": 2}
        ).json()
        rest = client.get(
            f"/api/people/{person.id}/images", params={"skip": 2, "limit": 10}
        ).json()

        assert first["total"] == 5
        assert [img["media_id"] for img in first["images"]] == [
            photos[4].id,
            photos[3].id,
        ]
        assert len(first["images"][0]["faces"]) == 2
        assert [img["media_id"] for img in rest["images"]] == [
            photos[2].id,
            photos[1].id,
            photos[0].id,
        ]

    def test_hidden_photos_are_not_counted(self, client, db):
        person = Person(name="Ben")
        db.add(person)
        db.commit()
        shown = _seed_media(db, "ben-shown.jpg")
        hidden = _seed_media(db, "ben-hidden.jpg", minutes=1)
        hidden.is_archived = True
        db.commit()
        _add_face(db, shown, person)
        _add_face(db, hidden, person)

        body = client.get(f"/api/people/{person.id}/images").json()

        assert body["total"] == 1
        assert [img["media_id"] for img in body["images"]] == [shown.id]


def _seed_cluster(db, member_ids: list[int]) -> Cluster:
    cluster = Cluster(
        cluster_type="general",
        member_ids=member_ids,
        member_count=len(member_ids),
        label="Trips",
        created_at=BASE_TIME,
    )
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster


class TestClusterDetail:
    def test_pages_members_newest_first(self, client, db):
        photos = [_seed_media(db, f"trip-{i}.jpg", minutes=i) for i in range(5)]
        cluster = _seed_cluster(db, [p.id for p in photos])

        body = client.get(
            f"/api/cluster/{cluster.id}", params={"skip": 1, "limit": 2}
        ).json()

        assert body["member_count"] == 5
        assert body["total"] == 5
        assert [m["id"] for m in body["members"]] == [photos[3].id, photos[2].id]

    def test_filename_filter_searches_every_member(self, client, db):
        photos = [_seed_media(db, f"beach-{i}.jpg", minutes=i) for i in range(3)]
        photos.append(_seed_media(db, "city_night.jpg", minutes=9))
        photos.append(_seed_media(db, "city-night.jpg", minutes=8))
        cluster = _seed_cluster(db, [p.id for p in photos])

        beach = client.get(
            f"/api/cluster/{cluster.id}", params={"q": "BEACH", "limit": 1}
        ).json()
        underscore = client.get(
            f"/api/cluster/{cluster.id}", params={"q": "city_"}
        ).json()

        assert beach["member_count"] == 5
        assert beach["total"] == 3
        assert [m["filename"] for m in beach["members"]] == ["beach-2.jpg"]
        # "_" matches itself, not any character.
        assert [m["filename"] for m in underscore["members"]] == ["city_night.jpg"]

    def test_rejects_oversized_pages(self, client, db):
        cluster = _seed_cluster(db, [_seed_media(db, "one.jpg").id])

        response = client.get(
            f"/api/cluster/{cluster.id}", params={"limit": DETAIL_PAGE_MAX + 1}
        )

        assert response.status_code == 422


class TestAlbumAssets:
    def test_pages_in_album_order(self, client, db):
        album = client.post("/api/albums", json={"name": "Paged"}).json()
        photos = [_seed_media(db, f"album-{i}.jpg", minutes=i) for i in range(4)]
        client.put(
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [p.id for p in photos]},
        )

        first = client.get(
            f"/api/albums/{album['id']}/assets", params={"limit": 3}
        ).json()
        rest = client.get(
            f"/api/albums/{album['id']}/assets", params={"skip": 3}
        ).json()

        assert first["total"] == 4
        assert [item["id"] for item in first["items"]] == [p.id for p in photos[:3]]
        assert [item["id"] for item in rest["items"]] == [photos[3].id]


@pytest.mark.parametrize(
    "path", ["/api/people/1/images", "/api/cluster/1", "/api/albums/1/assets"]
)
def test_negative_skip_is_rejected(client, path):
    assert client.get(path, params={"skip": -1}).status_code == 422
