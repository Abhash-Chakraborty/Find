"""Near-duplicate detection via pgvector cosine similarity."""
from __future__ import annotations

import pytest
from find_api.models import Media
from find_api.services.duplicate_service import find_near_duplicate, flag_as_duplicate
from sqlalchemy.orm import Session


def test_find_near_duplicate_no_match(db: Session):
    """Test find_near_duplicate returns None when no similar image exists."""
    # Create media without duplicate
    media = Media(
        file_hash="test_hash_1",
        minio_key="test_key_1",
        filename="test_1.jpg",
        status="indexed",
        vector=[0.0] * 1536,
    )
    db.add(media)
    db.commit()

    # Search for duplicates with different embedding
    result = find_near_duplicate(
        db=db,
        media_id=media.id,
        embedding=[1.0] * 1536,
    )

    assert result is None


def test_find_near_duplicate_similar_match(db: Session):
    """Test find_near_duplicate finds similar images above threshold."""
    # Create original media
    original = Media(
        file_hash="test_hash_original",
        minio_key="test_key_original",
        filename="original.jpg",
        status="indexed",
        vector=[0.99] * 1536,  # Nearly identical vector
    )
    db.add(original)
    db.commit()

    # Create nearly identical media
    similar = Media(
        file_hash="test_hash_similar",
        minio_key="test_key_similar",
        filename="similar.jpg",
        status="indexed",
        vector=[0.99] * 1536,  # Nearly identical vector
    )
    db.add(similar)
    db.commit()

    # Search should find the similar image
    result = find_near_duplicate(
        db=db,
        media_id=original.id,
        embedding=[0.99] * 1536,
    )

    assert result == similar.id


def test_flag_as_duplicate(db: Session):
    """Test flag_as_duplicate marks media as duplicate."""
    # Create original and duplicate media
    original = Media(
        file_hash="test_hash_original",
        minio_key="test_key_original",
        filename="original.jpg",
        status="indexed",
    )
    db.add(original)
    db.commit()

    duplicate = Media(
        file_hash="test_hash_duplicate",
        minio_key="test_key_duplicate",
        filename="duplicate.jpg",
        status="indexed",
    )
    db.add(duplicate)
    db.commit()

    # Flag as duplicate
    flag_as_duplicate(db=db, media_id=duplicate.id, duplicate_of=original.id)

    # Verify the flag was set
    db.refresh(duplicate)
    assert duplicate.duplicate_of == original.id


def test_flag_as_duplicate_invalid_media(db: Session):
    """Test flag_as_duplicate handles non-existent media gracefully."""
    # Try to flag a non-existent media
    with pytest.raises(Exception):
        flag_as_duplicate(db=db, media_id=99999, duplicate_of=99998)