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
