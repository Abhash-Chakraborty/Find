# User Feedback Loops for Person Grouping & Model Personalization

## Overview

Issue #188 is a parent roadmap for adding:

1. **Feedback collection** — Users correct person clusters (splits, merges, duplicates)
2. **General feedback capture** — Rate search results, captions, objects, people grouping
3. **Research + prototyping** — Low-compute personalization before fine-tuning

**Key constraint**: Keep all feedback local. No cloud training or public datasets.

---

## Current State

### What exists

- ✅ **Person model** — Groups faces into person clusters
- ✅ **Face model** — Embeddings, bounding boxes, confidence scores, person_id FK
- ✅ **People page** — Browse and name person groups
- ✅ **Face clustering** — Automatic HDBSCAN-based grouping

### What's missing

- ❌ Feedback data model (corrections, corrections, ratings)
- ❌ Split person cluster UI + backend
- ❌ Merge person clusters UI + backend
- ❌ Mark faces as "wrong person" (duplicate detection)
- ❌ General feedback storage (search, caption, object, people ratings)
- ❌ Feedback analytics/dashboards
- ❌ Low-compute personalization research

---

## Sub-Issue Breakdown

### Issue #189: Collect User Feedback for Split or Duplicate Person Clusters

**Scope**: Enable users to correct person grouping directly from the People page

#### Backend Tasks

1. **Create feedback model** (`feedback.py` or in `person.py`)
   - `FeedbackType`: SPLIT, MERGE, WRONG_PERSON, CORRECT
   - `source_person_id`, `target_person_id` (if applicable)
   - `face_ids` (which faces triggered feedback)
   - `user_reason` (free text, optional)
   - `created_at`, `resolved_at`
   - Store in SQLite/PostgreSQL local feedback table

2. **New API endpoints** (in `routers/people.py`)
   - `POST /people/{person_id}/feedback/split` — Split person into multiple groups
   - `POST /people/{person_id}/{face_id}/feedback/wrong-person` — Mark face as misclassified
   - `POST /people/{person_id}/feedback/merge/{target_person_id}` — Merge two persons
   - `GET /people/feedback` — List all feedback (for debugging/analytics)

3. **Feedback processing** (in `workers/processors.py` or new file)
   - When split feedback received: Move selected face_ids to new person (or ungroup)
   - When merge feedback: Move all faces from source to target person
   - Log each action atomically

#### Frontend Tasks

1. **Split UI** (modify `people/page.tsx`)
   - In person detail modal, add "Split this group" button
   - Show checklist of face images
   - Select faces to move to new group
   - Submit creates feedback record + updates UI optimistically

2. **Merge UI**
   - Add "Merge with another person" button
   - Modal to select target person
   - Confirm + merge

3. **Wrong person marker**
   - In detail view, click face → "This is not [person name]"
   - Move to new person or ungroup
   - Stores feedback + updates immediately

#### Testing

- Unit tests for split/merge/ungroup logic
- API tests for feedback endpoints
- Integration tests for clustering + feedback workflow

---

### Issue #190: Add Manual Feedback Actions for Search, Captions, Objects, and People

**Scope**: General-purpose feedback capture across the app (not just people)

#### Data Model (extended feedback system)

```python
class Feedback(Base):
    id = Column(Integer, primary_key=True)
    feedback_type = Column(Enum(FeedbackType))  # SEARCH_RATING, CAPTION_RATING, OBJECT_RATING, PEOPLE_CORRECTION
    
    # Polyglot: varies by type
    media_id = Column(Integer, FK nullable)  # Search, caption, object
    person_id = Column(Integer, FK nullable)  # People correction
    
    rating = Column(Integer, nullable)  # 1-5 stars for search, captions, objects
    rating_reason = Column(String, nullable)  # "caption is inaccurate", "search result not relevant"
    
    # For people feedback specifically
    correction_type = Column(String, nullable)  # SPLIT, MERGE, WRONG_PERSON, CORRECT
    
    created_at = Column(DateTime, default=now)
```

#### Backend Tasks

1. **Feedback endpoints** (new router: `routers/feedback.py`)
   - `POST /feedback/search-rating` — Rate search result relevance (1-5 + reason)
   - `POST /feedback/caption-rating` — Rate caption accuracy
   - `POST /feedback/object-rating` — Rate object detection accuracy
   - `POST /feedback/people` — Rate person grouping (overlaps with #189)
   - `GET /feedback/stats` — Aggregate feedback stats (optional, for analytics)

2. **Feedback storage** (SQLite OK for local storage)
   - All feedback stored locally, never uploaded

#### Frontend Tasks

1. **Search page** (`app/search/page.tsx`)
   - Add star rating widget below each search result
   - Text input for reason (optional)

2. **Gallery page** (`app/gallery/page.tsx`)
   - Rate image caption accuracy below image details
   - Rate detected objects (if shown in UI)

3. **People page** (`app/people/page.tsx`)
   - Already covered by #189

#### Testing

- API tests for each feedback type
- Frontend component tests for rating widgets
- Verify feedback persists and retrieves correctly

---

### Issue #191: Research Low-Compute Personalization Before Fine-Tuning

**Scope**: Prototype + document feasibility of personalization without fine-tuning

#### Research & Documentation

1. **Document existing personalization approaches**
   - Threshold tuning (adjust HDBSCAN epsilon per user feedback)
   - Re-weighting embeddings (boost faces user marked as "correct")
   - Hard negatives (mark faces as "NOT person X")
   - Local ranking/sorting by feedback

2. **Prototype low-compute options** (in `docs/PERSONALIZATION_RESEARCH.md`)
   - **Approach A**: Threshold adaptation
     - If user splits clusters frequently → lower epsilon
     - If user marks many wrong → adjust confidence threshold
     - Cost: None (parameter tuning only)

   - **Approach B**: Embedding re-weighting
     - User feedback on faces → weight adjustment signal
     - Re-cluster with weighted distance function
     - Cost: Low (re-cluster only affected faces)

   - **Approach C**: Negative sampling
     - "This face is NOT person X" → add to negative set
     - Use negatives in similarity scoring
     - Cost: Low (inference only, no training)

   - **Approach D**: Fine-tuning (avoid for now)
     - Too expensive for local, GPU-dependent
     - Document why it's out of scope

3. **Proof-of-concept** (optional, depends on priority)
   - Implement Approach A or B in a branch
   - Show results with 10-20 feedback samples
   - Document performance + cost trade-offs

#### Deliverables

- `docs/PERSONALIZATION_RESEARCH.md` — Detailed research document
- Optional: Simple prototype in `backend/ml/personalization.py`
- Findings inform future work on #200+ issues

---

## Implementation Order (Recommended)

### Phase 1: Feedback Foundation (#189)

**Effort**: 3-5 days (2 dev + 1 QA)

1. Create `PersonFeedback` model (split, merge, wrong_person)
2. Implement backend API endpoints
3. Add split/merge logic to cluster processor
4. Simple tests
5. Frontend split UI + wrong_person marker

### Phase 2: Generalized Feedback (#190)

**Effort**: 2-3 days (1 dev + 1 QA)

1. Create generic `Feedback` model
2. Backend endpoints for search, caption, object ratings
3. Frontend rating widgets on search + gallery
4. Tests

### Phase 3: Research & Prototype (#191)

**Effort**: 3-5 days (1 researcher/dev)

1. Document research findings in MD
2. Prototype Approach A or B if feasible
3. Benchmark + document costs
4. Open discussion for future personalization work

---

## Database Schema (Phase 1)

```python
# backend/src/find_api/models/feedback.py

class PersonFeedback(Base):
    __tablename__ = "person_feedback"
    
    id = Column(Integer, primary_key=True)
    feedback_type = Column(String(50))  # SPLIT, MERGE, WRONG_PERSON, CORRECT
    source_person_id = Column(Integer, FK("persons.id"), nullable=False)
    target_person_id = Column(Integer, FK("persons.id"), nullable=True)  # For merge/move
    face_ids = Column(JSON, nullable=False)  # [1, 2, 3] — which faces affected
    user_reason = Column(String(500), nullable=True)  # Free text
    created_at = Column(DateTime, default=now)
    resolved_at = Column(DateTime, nullable=True)  # When feedback was applied
    status = Column(String(20), default="pending")  # pending, applied, rejected
```

---

## Files to Create/Modify

### Backend

- ✨ Create: `backend/src/find_api/models/feedback.py`
- ✨ Create: `backend/src/find_api/routers/feedback.py`
- 🔄 Modify: `backend/src/find_api/routers/people.py` (add split/merge endpoints)
- 🔄 Modify: `backend/src/find_api/workers/processors.py` (apply feedback logic)
- ✨ Create: `docs/PERSONALIZATION_RESEARCH.md`

### Frontend

- 🔄 Modify: `frontend/src/app/people/page.tsx` (split/merge/wrong-person UI)
- 🔄 Modify: `frontend/src/app/search/page.tsx` (rating widget)
- 🔄 Modify: `frontend/src/app/gallery/page.tsx` (caption/object rating)
- 🔄 Modify: `frontend/src/lib/api.ts` (new API client methods)

### Tests

- ✨ Create: `backend/tests/test_feedback.py`
- ✨ Create: `backend/tests/test_people_corrections.py`
- ✨ Create: `frontend/src/__tests__/feedback.test.tsx`

---

## Success Criteria

- ✅ Users can split misclassified person clusters
- ✅ Users can merge wrongly-separated persons
- ✅ Feedback is stored locally (SQLite/PostgreSQL)
- ✅ General feedback capture works for search/captions/objects
- ✅ Research doc on personalization published
- ✅ All feedback operations atomic + rollback-safe
- ✅ Tests cover core feedback logic + edge cases

---

## Open Questions

1. **UI/UX**: Should feedback be applied immediately or queued for review?
   - Suggestion: Apply immediately (optimistic), store in DB, allow undo

2. **Feedback limits**: Should we throttle feedback to prevent spam?
   - Suggestion: No throttle for local-first, but track volume in stats

3. **Merge strategy**: When merging persons, which name wins?
   - Suggestion: User-selected or keep both names (e.g., "Alice / Emma")

4. **Split strategy**: Move selected faces to new person or to "Unknown"?
   - Suggestion: Create new unnamed person, user names it after

5. **Personalization timeline**: When to start work on #191?
   - Suggestion: After #189 + #190 complete, or parallel if resources allow

---

## References

- Issue #188: Parent roadmap
- Issue #189: Collect feedback for person cluster corrections
- Issue #190: Manual feedback for search/captions/objects/people
- Issue #191: Research low-compute personalization
- [Personalization Research](./PERSONALIZATION_RESEARCH.md) (TBD)
