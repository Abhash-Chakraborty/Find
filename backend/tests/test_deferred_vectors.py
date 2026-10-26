"""Vector columns stay out of ordinary queries until something reads them."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import inspect

from find_api.models.cluster import Cluster
from find_api.models.face import Face
from find_api.models.media import Media


def test_vector_columns_are_deferred(db):
    media = Media(
        file_hash=hashlib.sha256(b"deferred").hexdigest(),
        minio_key="images/test/deferred.jpg",
        filename="deferred.jpg",
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        created_at=datetime.now(UTC),
    )
    db.add(media)
    db.commit()
    db.add(Face(media_id=media.id, bounding_box={}, confidence=0.9))
    db.add(Cluster(cluster_type="general", member_ids=[media.id], member_count=1))
    db.commit()
    db.expunge_all()

    for model, column in (
        (Media, "vector"),
        (Face, "embedding"),
        (Cluster, "centroid_vector"),
    ):
        row = db.query(model).first()
        assert column in inspect(row).unloaded, f"{model.__name__}.{column}"
