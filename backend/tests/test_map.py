"""Privacy and scoping tests for the opt-in local map."""

from datetime import datetime, timezone
from typing import Optional

from find_api.models.app_setting import AppSetting
from find_api.models.media import Media
from find_api.models.user import User
from find_api.routers import map as map_router


def _media(
    media_id: int,
    *,
    latitude: Optional[float] = 22.5726,
    longitude: Optional[float] = 88.3639,
    liked: bool = False,
    hidden: bool = False,
    archived: bool = False,
    deleted: bool = False,
    vault_state: str = "visible",
    uploader_user_id: Optional[int] = None,
) -> Media:
    return Media(
        id=media_id,
        file_hash=f"{media_id:064x}",
        minio_key=f"images/{media_id}.jpg",
        filename=f"photo-{media_id}.jpg",
        status="indexed",
        created_at=datetime(2026, 7, media_id, tzinfo=timezone.utc),
        width=1600,
        height=900,
        latitude=latitude,
        longitude=longitude,
        liked=liked,
        is_hidden=hidden,
        is_archived=archived,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
        vault_state=vault_state,
        uploader_user_id=uploader_user_id,
    )


def _enable_map(db) -> None:
    db.add(AppSetting(key="map_enabled", value="true"))
    db.commit()


def test_map_is_disabled_by_default(client, db):
    db.add(AppSetting(key="map_enabled", value="false"))
    db.add(_media(1))
    db.commit()

    response = client.get("/api/map/markers")

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "markers": [], "total": 0}


def test_map_returns_only_visible_non_deleted_assets(client, db):
    _enable_map(db)
    db.add_all(
        [
            _media(1),
            _media(2, hidden=True),
            _media(3, archived=True),
            _media(4, deleted=True),
            _media(5, latitude=None, longitude=None),
            _media(6, vault_state="encrypted"),
        ]
    )
    db.commit()

    response = client.get("/api/map/markers")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert [marker["id"] for marker in body["markers"]] == [1]
    assert body["markers"][0]["thumbnail_url"] == "/api/image/1/thumbnail"
    assert body["markers"][0]["ratio"] == 1.7778
    assert body["markers"][0]["liked"] is False


def test_map_filters_favorites_bbox_and_optional_archive(client, db):
    _enable_map(db)
    db.add_all(
        [
            _media(1, latitude=22.57, longitude=88.36, liked=True),
            _media(2, latitude=51.50, longitude=-0.12, liked=True),
            _media(
                3,
                latitude=22.58,
                longitude=88.40,
                liked=True,
                archived=True,
            ),
            _media(4, latitude=22.59, longitude=88.41, liked=False),
        ]
    )
    db.commit()

    response = client.get(
        "/api/map/markers",
        params={
            "liked": "true",
            "include_archived": "true",
            "west": 88,
            "east": 89,
            "south": 22,
            "north": 23,
        },
    )

    assert response.status_code == 200
    assert {marker["id"] for marker in response.json()["markers"]} == {1, 3}


def test_map_bbox_wraps_across_the_antimeridian(client, db):
    _enable_map(db)
    db.add_all(
        [
            _media(1, latitude=10, longitude=179.5),
            _media(2, latitude=10, longitude=-179.5),
            _media(3, latitude=10, longitude=0),
        ]
    )
    db.commit()

    response = client.get(
        "/api/map/markers",
        params={"west": 170, "east": -170, "south": 0, "north": 20},
    )

    assert response.status_code == 200
    assert {marker["id"] for marker in response.json()["markers"]} == {1, 2}


def test_marker_query_is_scoped_to_the_signed_in_member(db):
    alice = User(id=10, username="alice", role="member", password_hash="hash")
    db.add_all(
        [
            _media(1, uploader_user_id=10),
            _media(2, uploader_user_id=11),
        ]
    )
    db.commit()

    rows = map_router._marker_query(
        db,
        alice,
        include_archived=False,
        liked=None,
        west=None,
        south=None,
        east=None,
        north=None,
    ).all()

    assert [media.id for media in rows] == [1]
