# Local Search Quality Roadmap

- **Status:** Partially complete
- **Last reviewed:** 2026-05-29
- **Related:** Issue #98
- **Current implementation status:** Find already has semantic search backed by pgvector. The worker
  stores a normalized hybrid vector built from available image, caption, and detected-object signals;
  the search endpoint embeds the text query and ranks indexed, non-hidden media by cosine similarity.
  Evaluation, diagnostics, reranking, ANN tuning, and reliable quality targets remain planned work.

## Overview

This roadmap defines a measurable plan for improving local semantic image search quality in Find.

The goal is to improve retrieval relevance without making risky full-stack changes before benchmarks and evaluation exist.

This roadmap connects caption quality, embeddings, retrieval, reranking, diagnostics, and scalability into one staged plan.

Related issues:

- #12 - Caption reliability
- #17 - Natural-language search relevance
- #96 - Search timing and retrieval diagnostics
- #99 - Retrieval strategy benchmarking
- #100 - Offline evaluation harness
- #101 - ANN indexing and hybrid ranking
- #230 - Personalized ranking and feedback

---

## Current Search Pipeline

Current pipeline:

1. Generate image metadata: Florence-2 captions, object detection, and OCR text where available.
2. Generate SigLIP embeddings for the image plus usable caption/object text signals.
3. Store the normalized hybrid media vector in pgvector.
4. Convert the text query into a SigLIP text embedding.
5. Run pgvector cosine-similarity search over indexed, non-hidden media with a similarity threshold.
6. Return paginated results with similarity scores, media metadata, URLs, and thumbnail URLs.

Current strengths:

- Simple architecture
- Fast implementation
- Good baseline semantic retrieval

Current weaknesses:

- Caption failures can reduce hybrid retrieval quality
- Text-heavy images are inconsistent
- No measurable evaluation metrics
- No reranking stage
- No retrieval diagnostics
- Scaling behavior is unknown
- Static similarity threshold may remove valid results

---

## Target Metrics

The search system should optimize for measurable retrieval quality.

### Quality Metrics

| Metric | Goal |
|---|---|
| Recall@10 | >= 85% |
| Precision@10 | >= 75% |
| MRR (Mean Reciprocal Rank) | >= 0.70 |
| Caption failure rate | < 2% |
| Empty result rate | < 5% |

### Latency Targets

| Stage | Target |
|---|---|
| Query embedding generation | < 150ms |
| Vector retrieval | < 100ms |
| Reranking | < 150ms |
| Total search latency | < 500ms |

---

## Roadmap Stages

### Stage 1: Retrieval Diagnostics and Evaluation

Related issues:
- #96
- #100

Goal:
Create measurable evaluation infrastructure before changing retrieval logic.

Tasks:

- Add query timing instrumentation
- Add retrieval-stage timing logs
- Log similarity score distributions
- Track empty-result queries
- Build offline evaluation dataset
- Add labeled test queries
- Benchmark retrieval quality automatically

Deliverables:

- Search evaluation harness
- Retrieval metrics dashboard
- Baseline benchmark report

Dependencies:
None

---

### Stage 2: Caption Reliability

Related issue:
- #12

Goal:
Improve metadata quality for image understanding.

Tasks:

- Detect failed caption generations
- Add retry/fallback logic
- Improve long-caption truncation
- Improve OCR integration
- Normalize noisy captions
- Store caption confidence metadata

Why this matters:

Caption quality strongly affects:
- text-heavy image retrieval
- semantic search relevance
- hybrid ranking quality

Dependencies:
Can run independently from ANN or reranking work.

---

### Stage 3: Embedding Strategy Improvements

Related issues:
- #17
- #99

Goal:
Improve semantic representation quality.

Tasks:

- Benchmark SigLIP vs CLIP variants
- Compare caption-only, image-only, and current hybrid image/caption/object embeddings
- Test combined OCR + caption embeddings
- Evaluate multi-vector retrieval
- Measure embedding dimensionality tradeoffs

Evaluation Criteria:

- Recall@K improvement
- Better text-heavy retrieval
- Lower irrelevant-image matches
- Latency impact

Dependencies:
Requires evaluation harness from Stage 1.

---

### Stage 4: Retrieval and Ranking Improvements

Related issues:
- #17
- #101

Goal:
Improve ranking quality after initial vector retrieval.

Tasks:

- Add hybrid search
  - vector similarity
  - OCR keyword matching
  - metadata boosts
- Add reranking stage
- Add adaptive similarity thresholds
- Add query-aware ranking logic

Potential ranking signals:

- Caption relevance
- OCR relevance
- Object detection overlap
- User likes/history
- Recency
- Cluster similarity

Dependencies:
Requires Stage 1 metrics.

Caption quality improvements from Stage 2 improve reranking quality but are not strict blockers.

---

### Stage 5: Scale and ANN Optimization

Related issue:
- #101

Goal:
Ensure retrieval performance scales with dataset growth.

Tasks:

- Benchmark pgvector ANN indexes
- Compare IVFFlat vs HNSW
- Measure recall vs latency tradeoffs
- Evaluate memory usage
- Add large-dataset benchmarks

Scale Targets:

| Dataset Size | Target Query Time |
|---|---|
| 10K images | < 150ms |
| 100K images | < 300ms |
| 1M images | < 700ms |

Dependencies:
Requires baseline metrics from Stage 1.

---

## Dependency Map

| Area | Depends On |
|---|---|
| Diagnostics | None |
| Caption reliability | None |
| Embedding benchmarking | Evaluation harness |
| Reranking | Evaluation harness |
| ANN optimization | Retrieval benchmarks |
| Personalized ranking | Stable retrieval metrics |

---

## Benchmarking Principles

Before major retrieval changes:

- Benchmark against current baseline
- Measure both latency and relevance
- Avoid replacing the full stack without evidence
- Keep rollback paths simple
- Prefer measurable incremental improvements

---

## Success Criteria

The roadmap is successful if:

- Search quality becomes measurable
- Retrieval regressions become detectable
- Search improvements are benchmark-driven
- Scaling behavior is understood
- Future contributors can work independently on retrieval stages
