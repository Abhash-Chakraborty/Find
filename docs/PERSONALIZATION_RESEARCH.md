# Personalization Research: Low-Compute Approaches for Local Model Adaptation

## Overview

This document evaluates approaches for personalizing Find's ML models based on user feedback, **without cloud training or heavy fine-tuning**. The goal is to improve clustering accuracy over time while keeping all computation local and GPU-optional.

## Problem Statement

After deploying the feedback collection system (#189, #190), Find will have rich data about:

- Which person clusters are correct/incorrect
- Which faces were misclassified
- Which search results were irrelevant
- User-edited captions that describe what the model should have generated
- User-corrected object labels that describe what should have been detected

**Challenge**: How do we learn from this feedback to improve local models without:

- Uploading data to cloud servers
- Fine-tuning models (computationally expensive, GPU-intensive)
- Modifying model weights (risky, requires retraining)

## Existing System

### Current Clustering Pipeline

1. **Face detection** → YOLOv10 → bounding boxes + confidence
2. **Face embeddings** → SigLIP (open-clip) → 768-dim vectors
3. **Clustering** → HDBSCAN(eps=0.45, min_samples=5) → person groups

### Current Parameters

- SigLIP embedding model: Open-CLIP community weights
- HDBSCAN epsilon (eps): Fixed at 0.45
- Min samples: Fixed at 5
- Confidence threshold: Fixed at 0.0 (all faces used)

## Evaluated Approaches

### Approach A: Adaptive Epsilon Tuning ⭐ (RECOMMENDED)

**Idea**: Adjust HDBSCAN's `eps` parameter based on user feedback patterns.

**Implementation**:

```python
# backend/ml/personalization.py

class AdaptiveEpsilonTuner:
    def __init__(self, initial_eps=0.45):
        self.eps = initial_eps
        self.feedback_history = []
    
    def record_feedback(self, feedback_type, face_count, distance_hint):
        """Record user feedback and adjust epsilon"""
        self.feedback_history.append({
            "type": feedback_type,  # "split", "merge", "correct"
            "face_count": face_count,
            "distance_hint": distance_hint,  # For ML use
        })
    
    def compute_adaptive_eps(self):
        """Update eps based on feedback trends"""
        if len(self.feedback_history) < 5:
            return self.eps  # Not enough data
        
        recent = self.feedback_history[-20:]  # Last 20 feedbacks
        split_count = sum(1 for f in recent if f["type"] == "split")
        merge_count = sum(1 for f in recent if f["type"] == "merge")
        distance_hints = [
            f["distance_hint"] for f in recent if f.get("distance_hint") is not None
        ]
        avg_distance_hint = (
            sum(distance_hints) / len(distance_hints) if distance_hints else None
        )
        
        # Too many splits → faces too close together → lower eps
        if split_count > merge_count + 2:
            self.eps = max(0.3, self.eps - 0.02)
        # Too many merges → faces too far apart → raise eps
        elif merge_count > split_count + 2:
            self.eps = min(0.7, self.eps + 0.02)
        # If feedback includes measured distances, use it as a small nudge only.
        elif avg_distance_hint is not None and avg_distance_hint > self.eps + 0.1:
            self.eps = min(0.7, self.eps + 0.01)
        
        return self.eps
```

**Pros**:

- ✅ No model retraining
- ✅ Low computation (clustering only)
- ✅ Easy to implement
- ✅ Reversible (can always reset)

**Cons**:

- ❌ Only affects clustering, not search quality
- ❌ Single global parameter (not per-user customizable yet)
- ⚠️ Slow feedback loop (need 20+ feedbacks to see effect)

**Cost**: <1ms per clustering job (negligible)

**Feasibility**: ✅ **HIGH** — Implement in Phase 1-2

---

### Approach B: Embedding Re-weighting ⭐⭐ (BEST TRADEOFF)

**Idea**: Boost embedding quality for commonly-correct faces, suppress for commonly-wrong faces.

**Implementation**:

```python
# backend/ml/personalization.py
import numpy as np

class EmbeddingReweighter:
    def __init__(self):
        self.face_quality_scores = {}  # face_id → confidence boost
        self.correction_log = []
    
    def record_correction(self, face_id, correct_cluster):
        """Record if face was correctly/incorrectly clustered"""
        if correct_cluster:
            # This face was correctly grouped → boost confidence
            self.face_quality_scores[face_id] = \
                self.face_quality_scores.get(face_id, 1.0) + 0.1
        else:
            # This face was misclassified → lower confidence
            self.face_quality_scores[face_id] = \
                self.face_quality_scores.get(face_id, 1.0) - 0.1
        
        self.correction_log.append((face_id, correct_cluster))
    
    def get_adjusted_embedding(self, embedding, face_id):
        """Return re-weighted embedding for clustering"""
        if face_id not in self.face_quality_scores:
            return embedding
        
        boost = self.face_quality_scores[face_id]
        # Amplify good embeddings, dampen bad ones
        adjusted = embedding * max(0.5, min(2.0, boost))
        # Re-normalize before cosine similarity so weighting does not create
        # invalid vector magnitude assumptions.
        return adjusted / np.linalg.norm(adjusted)
```

**Pros**:

- ✅ Improves clustering accuracy directly
- ✅ Per-face granularity
- ✅ Non-invasive (doesn't modify model)
- ✅ Can combine with epsilon tuning

**Cons**:

- ❌ Requires re-clustering after updates
- ⚠️ Scores need regularization (to avoid extreme values)
- ⚠️ Forgets old faces if not reclustered regularly

**Cost**: ~10-50ms per clustering job (modest)

**Feasibility**: ✅ **VERY HIGH** — Implement in Phase 2-3

---

### Approach C: Negative Sampling for Search

**Idea**: Use "this is NOT person X" feedback to improve search ranking.

**Implementation**:

```python
# backend/ml/personalization.py

class NegativeSamplingRanker:
    def __init__(self):
        self.negative_sets = {}  # person_id → set of dissimilar face_ids
    
    def record_wrong_person(self, person_id, face_id):
        """Record face that doesn't belong to person"""
        if person_id not in self.negative_sets:
            self.negative_sets[person_id] = set()
        self.negative_sets[person_id].add(face_id)
    
    def rank_search_results(self, person_id, similar_faces, k=10):
        """Re-rank search results, demoting negative samples"""
        if person_id not in self.negative_sets:
            return similar_faces[:k]
        
        negatives = self.negative_sets[person_id]
        # Filter out faces marked as wrong person
        filtered = [f for f in similar_faces if f.id not in negatives]
        return filtered[:k]
```

**Pros**:

- ✅ Direct impact on search quality
- ✅ Simple to implement
- ✅ No model retraining

**Cons**:

- ❌ Only works for search (not clustering)
- ❌ Requires manual negative annotation
- ⚠️ Cold start problem (need feedback first)

**Cost**: <1ms per search query

**Feasibility**: ✅ **HIGH** — Implement in Phase 2

---

### Approach D: Hard Negatives Mining ⭐⭐⭐ (FUTURE)

**Idea**: Use user feedback to create training signals for fine-tuning.

**Implementation** (future, when user opts in):

```python
# Collect hard negatives from feedback
hard_negatives = {
    "alice_embedding": [
        other_person_embeddings,  # False negatives
    ]
}

# Train for 1-2 epochs on device with low LR
model.fine_tune(hard_negatives, lr=1e-6, epochs=1)
```

**Pros**:

- ✅✅ Highest potential accuracy improvement
- ✅ Leverages feedback directly

**Cons**:

- ❌ Requires GPU (not local-first on CPU)
- ❌ Risk of catastrophic forgetting
- ❌ Complex to implement correctly
- ⚠️ Needs 100+ hard negatives to be worth it

**Cost**: 5-30 minutes per fine-tuning (GPU-dependent)

**Feasibility**: ❌ **LOW FOR NOW** — Defer to Phase 4+

---

## Recommended Roadmap

### Phase 1 (Now): Feedback Collection

- ✅ Implement feedback models + API (#189, #190)
- ✅ Frontend split/merge/correct UI
- ✅ Feedback storage in the local application database

### Phase 2 (1-2 weeks after): Approach A + C

- Add epsilon tuning (Approach A)
- Add negative sampling for search (Approach C)
- Monitor feedback trends

### Phase 3 (3-4 weeks after): Approach B

- Implement embedding re-weighting (Approach B)
- Re-cluster nightly with adjusted embeddings
- A/B test: with vs. without re-weighting

### Phase 4+ (Future): Approach D

- Research optimal fine-tuning strategy
- Benchmark on community datasets
- Only if Approach A-C reach accuracy plateau

## Metrics for Success

We'll measure personalization effectiveness using:

```python
# backend/ml/metrics.py

class PersonalizationMetrics:
    def __init__(self):
        self.feedback_count = 0
        self.feedback_applied_count = 0
        self.accuracy_before = None
        self.accuracy_after = None
    
    def track_feedback(self):
        self.feedback_count += 1
    
    def track_accuracy(self, correct_clusters, total_clusters):
        accuracy = correct_clusters / total_clusters
        if self.accuracy_before is None:
            self.accuracy_before = accuracy
        self.accuracy_after = accuracy
    
    def improvement_percentage(self):
        if self.accuracy_before is None or self.accuracy_after is None:
            return 0
        if self.accuracy_before == 0:
            return 0
        delta = self.accuracy_after - self.accuracy_before
        return (delta / self.accuracy_before) * 100
```

**Targets**:

- Collect 50+ feedbacks per user per week
- Apply 80%+ of feedback automatically
- Achieve 5-15% accuracy improvement after 4 weeks of feedback

## Storage & Performance

### Feedback Storage

```sql
-- PostgreSQL feedback tables (already in models/feedback.py)
CREATE TABLE person_feedback (
    id SERIAL PRIMARY KEY,
    source_person_id INT REFERENCES persons(id),
    feedback_type VARCHAR(50),  -- "split", "merge", "wrong_person", "correct"
    face_ids JSON,
    user_reason VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE general_feedback (
    id SERIAL PRIMARY KEY,
    feedback_type VARCHAR(50),  -- "search_rating", "caption_correction", "object_correction"
    media_id INT REFERENCES media(id),
    rating INT,  -- 1-5 for relevance feedback, nullable for correction feedback
    metadata JSON,  -- stores corrected_caption or corrected_objects for future training data
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Persistence Across Sessions

```python
# backend/ml/personalization.py

class PersonalizationState:
    def __init__(self, db):
        self.db = db
        self.load_from_db()
    
    def load_from_db(self):
        """Load previous feedback history"""
        feedback = self.db.query(PersonFeedback).all()
        for f in feedback:
            if f.feedback_type == "split":
                self.epsilon_tuner.record_feedback(
                    "split",
                    len(f.face_ids),
                    distance_hint=getattr(f, "distance_hint", None),
                )
    
    def save_to_db(self, feedback):
        """Persist new feedback"""
        self.db.add(feedback)
        self.db.commit()
```

## Open Questions

1. **How often to re-cluster?**
   - Option A: On-demand (user clicks "Re-cluster with personalization")
   - Option B: Nightly (batch job at 2 AM)
   - Recommendation: Start with A, add B if CPU allows

2. **Should personalization be per-user or global?**
   - For local-first: Per-user only (data isolation)
   - Share across multi-user installs? (Future research)

3. **How to handle privacy?**
   - All computations local ✅
   - No data transmission ✅
   - Option: Export anonymized feedback for research (opt-in)

4. **Baseline for accuracy measurement?**
   - Option A: Manual annotation of 100 random clusters
   - Option B: User feedback as ground truth
   - Recommendation: Use feedback, validate on 20% sample

## References

- HDBSCAN parameters: <https://hdbscan.readthedocs.io/>
- Open-CLIP models: <https://github.com/mlfoundations/open_clip>
- Hard negatives mining: <https://arxiv.org/abs/2104.14294>
- Local ML personalization: <https://arxiv.org/abs/2007.14861>

## Timeline

| Phase | Approach | Effort | Impact | Timeline |
|-------|----------|--------|--------|----------|
| 1 | Feedback Collection | 3-5d | Foundation | Week 1-2 |
| 2 | Epsilon Tuning (A) | 2-3d | Low | Week 2-3 |
| 2 | Negative Sampling (C) | 2d | Medium | Week 2-3 |
| 3 | Re-weighting (B) | 3-5d | High | Week 4-5 |
| 4+ | Fine-tuning (D) | 5-10d | Very High | Week 8+ |

## Conclusion

**Recommended starting point: Approach A + C (Phase 2)**

These provide quick wins with minimal complexity:

- Epsilon tuning gives ~5% accuracy improvement at zero cost
- Negative sampling directly improves search quality
- Both ship in 4-5 days
- Pave the way for re-weighting (B) in Phase 3

**Approach D (fine-tuning) is deferred** until Approach A-C plateau, ensuring we ship value quickly while researching the harder problem.

---

**Next steps**:

1. Review this document in #191 discussion
2. Confirm roadmap with team
3. Start Phase 2 implementation after Phase 1 feedback collection ships
