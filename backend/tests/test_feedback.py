"""
Tests for feedback system (person corrections and general ratings)
"""

import pytest
from sqlalchemy.orm import Session

from find_api.models.person import Person
from find_api.models.face import Face
from find_api.models.media import Media


@pytest.fixture
def test_media(db: Session):
    """Create test media for feedback tests"""
    media = Media(
        filename="test.jpg",
        file_hash="testhash123",
        minio_key="images/test.jpg",
        file_size=1024,
        content_type="image/jpeg",
        width=800,
        height=600,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


@pytest.fixture
def test_person_with_faces(db: Session, test_media: Media):
    """Create a test person group with multiple faces"""
    person = Person(name="Test Person")
    db.add(person)
    db.flush()

    # Create 5 faces belonging to this person
    faces = []
    for i in range(5):
        face = Face(
            media_id=test_media.id,
            person_id=person.id,
            bounding_box={"x1": i * 10, "y1": 10, "x2": i * 10 + 50, "y2": 60},
            confidence=0.95,
            embedding=None,
        )
        db.add(face)
        faces.append(face)

    db.commit()
    db.refresh(person)

    return person, faces


class TestPersonClusterFeedback:
    """Test person cluster split/merge/correction feedback"""

    def test_split_person_cluster(self, client, db: Session, test_person_with_faces):
        """Test splitting a person cluster by moving selected faces to new person"""
        person, faces = test_person_with_faces
        face_ids_to_split = [faces[0].id, faces[1].id]

        response = client.post(
            f"/api/people/{person.id}/feedback/split",
            json={
                "feedback_type": "split",
                "face_ids": face_ids_to_split,
                "user_reason": "These are different people",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "split"
        assert feedback["status"] == "applied"
        assert len(feedback["face_ids"]) == 2

        # Verify faces were moved to new person
        db.expire_all()
        db_faces = db.query(Face).filter(Face.id.in_(face_ids_to_split)).all()
        assert all(f.person_id != person.id for f in db_faces)

    def test_split_with_empty_face_ids(
        self, client, db: Session, test_person_with_faces
    ):
        """Test that split fails with empty face_ids"""
        person, _ = test_person_with_faces

        response = client.post(
            f"/api/people/{person.id}/feedback/split",
            json={
                "feedback_type": "split",
                "face_ids": [],
            },
        )

        assert response.status_code == 400

    def test_merge_two_persons(self, client, db: Session, test_media: Media):
        """Test merging two person groups"""
        person1 = Person(name="Person 1")
        person2 = Person(name="Person 2")
        db.add(person1)
        db.add(person2)
        db.flush()

        # Add faces to person1
        face1 = Face(
            media_id=test_media.id,
            person_id=person1.id,
            bounding_box={"x1": 0, "y1": 0, "x2": 50, "y2": 50},
            confidence=0.95,
        )
        db.add(face1)
        db.commit()
        db.refresh(person1)

        # Merge person1 into person2
        response = client.post(
            f"/api/people/{person1.id}/feedback/merge/{person2.id}",
            json={
                "feedback_type": "merge",
                "face_ids": [face1.id],
                "user_reason": "These are the same person",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "merge"
        assert feedback["target_person_id"] == person2.id

        # Verify face was moved
        db.refresh(face1)
        assert face1.person_id == person2.id

    def test_merge_person_with_itself_fails(
        self, client, db: Session, test_person_with_faces
    ):
        """Test that merging a person with itself fails"""
        person, _ = test_person_with_faces

        response = client.post(
            f"/api/people/{person.id}/feedback/merge/{person.id}",
            json={
                "feedback_type": "merge",
                "face_ids": [],
            },
        )

        assert response.status_code == 400

    def test_wrong_person_feedback(self, client, db: Session, test_person_with_faces):
        """Test marking face as wrong person"""
        person, faces = test_person_with_faces
        face_id = faces[0].id

        response = client.post(
            f"/api/people/{person.id}/feedback/wrong-person",
            json={
                "feedback_type": "wrong_person",
                "face_ids": [face_id],
                "user_reason": "This is someone else",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "wrong_person"

        # Verify face moved to new person
        db.expire_all()
        db_face = db.query(Face).filter(Face.id == face_id).first()
        assert db_face.person_id != person.id

    def test_correct_feedback(self, client, db: Session, test_person_with_faces):
        """Test marking person cluster as correctly grouped"""
        person, faces = test_person_with_faces

        response = client.post(
            f"/api/people/{person.id}/feedback/correct",
            json={
                "feedback_type": "correct",
                "face_ids": [f.id for f in faces],
                "user_reason": "This clustering is correct",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "correct"
        assert feedback["status"] == "applied"


class TestGeneralFeedback:
    """Test general feedback (ratings) for search, captions, objects"""

    def test_search_rating(self, client, db: Session, test_media: Media):
        """Test rating a search result"""
        response = client.post(
            "/api/feedback/search-rating",
            json={
                "feedback_type": "search_rating",
                "media_id": test_media.id,
                "rating": 5,
                "rating_reason": "Perfect match!",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "search_rating"
        assert feedback["rating"] == 5

    def test_caption_rating(self, client, db: Session, test_media: Media):
        """Test rating a caption"""
        response = client.post(
            "/api/feedback/caption-rating",
            json={
                "feedback_type": "caption_rating",
                "media_id": test_media.id,
                "rating": 3,
                "rating_reason": "Caption is somewhat accurate",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "caption_rating"
        assert feedback["rating"] == 3

    def test_caption_correction(self, client, db: Session, test_media: Media):
        """Test storing a corrected caption for future training data."""
        test_media.metadata_json = {"caption": "a wrong caption"}
        db.commit()

        response = client.post(
            "/api/feedback/caption-correction",
            json={
                "feedback_type": "caption_correction",
                "media_id": test_media.id,
                "corrected_caption": "a person standing near a building",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "caption_correction"
        assert feedback["rating"] is None
        assert feedback["extra_metadata"]["original_caption"] == "a wrong caption"
        assert (
            feedback["extra_metadata"]["corrected_caption"]
            == "a person standing near a building"
        )

    def test_object_rating(self, client, db: Session, test_media: Media):
        """Test rating object detection"""
        response = client.post(
            "/api/feedback/object-rating",
            json={
                "feedback_type": "object_rating",
                "media_id": test_media.id,
                "rating": 4,
                "rating_reason": "Detected most objects correctly",
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "object_rating"
        assert feedback["rating"] == 4

    def test_object_correction(self, client, db: Session, test_media: Media):
        """Test storing corrected object labels for future training data."""
        test_media.metadata_json = {
            "objects": [
                {"class": "person", "confidence": 0.95},
                {"class": "chair", "confidence": 0.55},
            ]
        }
        db.commit()

        response = client.post(
            "/api/feedback/object-correction",
            json={
                "feedback_type": "object_correction",
                "media_id": test_media.id,
                "corrected_objects": ["person", "backpack"],
            },
        )

        assert response.status_code == 200
        feedback = response.json()
        assert feedback["feedback_type"] == "object_correction"
        assert feedback["rating"] is None
        assert feedback["extra_metadata"]["original_objects"] == ["person", "chair"]
        assert feedback["extra_metadata"]["corrected_objects"] == [
            "person",
            "backpack",
        ]

    def test_rating_validation(self, client, db: Session, test_media: Media):
        """Test that ratings are validated (1-5 range)"""
        response = client.post(
            "/api/feedback/search-rating",
            json={
                "feedback_type": "search_rating",
                "media_id": test_media.id,
                "rating": 10,  # Invalid
            },
        )

        assert response.status_code == 400

    def test_zero_rating_is_invalid(self, client, db: Session, test_media: Media):
        """Test that zero is rejected instead of treated as missing/truthy."""
        response = client.post(
            "/api/feedback/search-rating",
            json={
                "feedback_type": "search_rating",
                "media_id": test_media.id,
                "rating": 0,
            },
        )

        assert response.status_code == 400

    def test_missing_rating_is_invalid(self, client, db: Session, test_media: Media):
        """Test that rating endpoints require an explicit 1-5 score."""
        response = client.post(
            "/api/feedback/search-rating",
            json={
                "feedback_type": "search_rating",
                "media_id": test_media.id,
            },
        )

        assert response.status_code == 400


class TestFeedbackStats:
    """Test feedback analytics endpoints"""

    def test_get_feedback_stats(
        self, client, db: Session, test_media: Media, test_person_with_faces
    ):
        """Test retrieving feedback statistics"""
        person, faces = test_person_with_faces

        # Add some feedback
        client.post(
            "/api/feedback/search-rating",
            json={
                "feedback_type": "search_rating",
                "media_id": test_media.id,
                "rating": 4,
            },
        )
        client.post(
            "/api/feedback/caption-rating",
            json={
                "feedback_type": "caption_rating",
                "media_id": test_media.id,
                "rating": 3,
            },
        )
        client.post(
            f"/api/people/{person.id}/feedback/correct",
            json={
                "feedback_type": "correct",
                "face_ids": [faces[0].id],
            },
        )

        response = client.get("/api/feedback/stats")

        assert response.status_code == 200
        stats = response.json()
        assert stats["person_feedback"]["total"] >= 1
        assert stats["general_feedback"]["total"] >= 2

    def test_list_person_feedback(self, client, db: Session, test_person_with_faces):
        """Test listing person feedback by person"""
        person, faces = test_person_with_faces

        # Add feedback
        client.post(
            f"/api/people/{person.id}/feedback/correct",
            json={
                "feedback_type": "correct",
                "face_ids": [faces[0].id],
            },
        )

        response = client.get(f"/api/people/feedback?person_id={person.id}")

        assert response.status_code == 200
        feedback_list = response.json()
        assert len(feedback_list) >= 1
        assert feedback_list[0]["source_person_id"] == person.id
