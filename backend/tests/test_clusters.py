"""Tests for cluster API thumbnail URL fields."""

import hashlib
from datetime import datetime, timezone

from find_api.models.cluster import Cluster
from find_api.models.media import Media


def _seed_media(db, *, filename: str) -> Media:
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
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
    return media


def _seed_cluster(db, *, member_ids: list[int]) -> Cluster:
    cluster = Cluster(
        cluster_type="general",
        member_ids=member_ids,
        member_count=len(member_ids),
        label="Test cluster",
        description="Cluster used in tests",
        created_at=datetime.now(timezone.utc),
    )
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster


def test_clusters_include_thumbnail_urls(client, db):
    first = _seed_media(db, filename="one.jpg")
    second = _seed_media(db, filename="two.jpg")
    _seed_cluster(db, member_ids=[first.id, second.id])

    body = client.get("/api/clusters").json()

    assert body["total"] == 1
    sample = body["clusters"][0]["samples"][0]
    assert sample["thumbnail_url"] == f"/api/image/{sample['id']}/thumbnail"


def test_cluster_detail_includes_thumbnail_urls(client, db):
    first = _seed_media(db, filename="detail-one.jpg")
    second = _seed_media(db, filename="detail-two.jpg")
    cluster = _seed_cluster(db, member_ids=[first.id, second.id])

    body = client.get(f"/api/cluster/{cluster.id}").json()

    assert body["id"] == cluster.id
    member = body["members"][0]
    assert member["thumbnail_url"] == f"/api/image/{member['id']}/thumbnail"


def test_update_cluster_label(client, db):
    media = _seed_media(db, filename="rename.jpg")
    cluster = _seed_cluster(db, member_ids=[media.id])

    response = client.patch(
        f"/api/cluster/{cluster.id}",
        json={"label": "Vacation photos"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == cluster.id
    assert body["label"] == "Vacation photos"

    db.refresh(cluster)
    assert cluster.label == "Vacation photos"


def test_update_cluster_label_trims_empty_to_null(client, db):
    media = _seed_media(db, filename="clear-label.jpg")
    cluster = _seed_cluster(db, member_ids=[media.id])

    response = client.patch(f"/api/cluster/{cluster.id}", json={"label": "   "})

    assert response.status_code == 200
    assert response.json()["label"] is None

    db.refresh(cluster)
    assert cluster.label is None
