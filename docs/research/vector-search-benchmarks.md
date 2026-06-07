# Vector Search Benchmark Evaluation

**Status:** Research plan / not implemented  
**Last reviewed:** 2026-05-28  
**Current implementation status:** The app still uses the existing pgvector search path. No ANN migration or benchmark harness from this document has landed.

## Goal

This document defines how Find should evaluate exact pgvector search against
approximate nearest-neighbor (ANN) options before adding indexing complexity.
It is a research and benchmark plan only. It does not propose shipping an ANN
migration without measured results.

## Current Find Baseline

Find currently stores one vector per indexed image in PostgreSQL with pgvector.
The `/api/search` endpoint:

- embeds the natural-language query with the active text embedder;
- searches `media.vector` with pgvector cosine distance:
  `1 - (vector <=> CAST(:embedding AS vector))`;
- filters to `status = 'indexed'` and `vector IS NOT NULL`;
- uses a similarity threshold of `0.45` in real ML mode and `-1.0` in mock
  mode;
- returns the top results ordered by similarity.

The current stored vector is a 768-dimensional SigLIP-style hybrid vector. In
real ML mode, Find generates it by averaging:

- image embedding;
- caption text embedding;
- detected-object text embedding.

That means the current baseline is not pure image retrieval. Any ANN or hybrid
ranking evaluation must compare against this exact behavior first.

Primary reference: pgvector supports cosine distance with `<=>`, and cosine
similarity can be computed as `1 - cosine distance`:
https://github.com/pgvector/pgvector

## Candidate Options

| Option | Fit for Find | Strengths | Risks |
| --- | --- | --- | --- |
| Exact pgvector scan | Current default | Simple, fully accurate recall baseline, no extra index lifecycle | Latency grows with indexed media count |
| pgvector HNSW | First serious candidate | Stays inside Postgres, supports cosine indexing, better speed/recall tradeoff than IVFFlat | Slower build time and higher memory use |
| pgvector IVFFlat | Secondary Postgres candidate | Faster build and lower memory than HNSW | Lower query performance and requires enough data before index creation |
| FAISS | Future large-scale candidate | Strong dense-vector search library, CPU/GPU support, broad evaluation tooling | Separate index lifecycle, packaging complexity, harder local desktop distribution |
| hnswlib | Future standalone HNSW candidate | Simple Python/C++ ANN library with cosine support and tunable `M`, `ef_construction`, `ef` | External index sync, update/delete complexity, memory tuning burden |
| Annoy | Future static-index candidate | Small memory footprint, mmap/static file indexes | Cannot add items after index build, weaker fit for frequently changing galleries |

Primary references:

- pgvector HNSW and IVFFlat: https://github.com/pgvector/pgvector
- FAISS: https://faiss.ai/
- hnswlib: https://github.com/nmslib/hnswlib
- Annoy: https://github.com/spotify/annoy

## Benchmark Dataset Plan

Run the benchmark at these indexed-media sizes:

| Size | Purpose |
| --- | --- |
| 1k vectors | Small local library sanity check |
| 10k vectors | Realistic active personal library |
| 50k vectors | Point where exact scan should be watched closely |
| 100k vectors | First serious ANN decision point |
| 1M vectors | Research/scale target, not current product baseline |

Dataset construction:

- Use real local media vectors where available.
- If the local library is smaller than a test size, scale with sampled or
  generated normalized vectors that match `EMBEDDING_DIM`.
- Keep a stable mapping from vector id to media id so recall can be measured.
- Do not use mock embeddings for final decisions; mock mode is only acceptable
  for tooling smoke tests.

Query set:

- At least 1,000 benchmark queries when possible.
- Include caption-style queries, object-style queries, OCR/text-heavy queries,
  and visually similar image queries.
- Include both easy queries with obvious matches and hard queries where the
  relevant item is visually or semantically ambiguous.

## Metrics

Measure database retrieval separately from total API time.

| Metric | What to report |
| --- | --- |
| DB latency | p50, p95, and p99 for only the vector retrieval query |
| API latency | Optional p50/p95/p99 including query embedding and response shaping |
| Recall | recall@5 and recall@10 against exact pgvector search |
| Memory | Postgres RSS and index memory where practical |
| Build time | Time to create the candidate index after data load |
| Update cost | Insert, delete, reprocess/update behavior for normal gallery changes |
| Complexity | Packaging, local-first impact, failure modes, and maintenance cost |

Exact pgvector search is the recall baseline. Candidate ANN results should be
compared against exact top-k results for the same query vectors.

## Numeric Adoption Gates

Find should stay on exact pgvector search while:

- p95 DB retrieval latency stays under `150 ms` at the target local collection
  size;
- total API latency does not create visible UI delay;
- memory remains acceptable for the default local Docker or future desktop
  runtime;
- recall is perfect by definition because exact search is still used.

Start ANN evaluation when either of these happens:

- p95 DB retrieval latency exceeds `200 ms` at `50k+` indexed images;
- exact search causes visible UI delay during normal use;
- memory or CPU pressure from exact scans becomes noticeable during repeated
  searches.

Adopt pgvector HNSW only if benchmark results show:

- recall@10 is at least `0.95` compared with exact search;
- p95 DB retrieval latency improves by at least `2x`;
- index memory/build time is acceptable for local-first use;
- insert/reprocess/delete behavior does not make the gallery stale or fragile.

Do not adopt an ANN option if:

- recall drops below the agreed floor for common user queries;
- metadata filtering or reranking breaks result quality;
- it requires a separate index service that complicates local installation;
- it increases memory enough to make idle/full-mode usage worse for normal
  users.

## Hybrid Ranking Evaluation

Find's current stored vector already mixes image, caption, and detected-object
signals. A future hybrid ranking system should be evaluated in stages:

1. Vector-only baseline: current exact pgvector behavior.
2. ANN candidate retrieval: HNSW/IVFFlat/other candidate returns a larger
   candidate pool, such as top 50 or top 100.
3. Metadata reranking: rerank candidates with caption, object, and OCR text
   signals.
4. Quality comparison: compare recall@k and subjective relevance against the
   exact baseline.

Important constraint: caption reliability issue #12 can block meaningful
caption-weighted evaluation. Until captions are reliable, object and OCR
metadata should be measured separately so bad captions do not hide vector-index
behavior.

## Recommended pgvector Experiments

Run these experiments before considering external libraries:

1. Exact pgvector baseline with the current query.
2. pgvector HNSW with `vector_cosine_ops`.
3. HNSW tuning with `hnsw.ef_search` values such as `40`, `100`, and `200`.
4. pgvector IVFFlat with list counts based on pgvector guidance and probes
   tuned for recall.
5. Optional rerank pass over a larger candidate set.

pgvector notes to account for:

- HNSW has better query performance than IVFFlat in speed/recall tradeoff, but
  uses more memory and builds more slowly.
- IVFFlat builds faster and uses less memory, but needs enough data before
  index creation and depends heavily on `lists` and `ivfflat.probes`.
- Approximate indexes can return fewer results when filtering is applied after
  index scan, so Find must test any future liked/status/visibility filters.

## Final Recommendation

Do not migrate away from exact pgvector search yet without measured local
benchmarks. Exact search is simpler, fully accurate, and likely acceptable for
small and medium local libraries.

The first serious ANN candidate should be pgvector HNSW because it preserves
the current Postgres architecture and avoids introducing a separate index
service. IVFFlat is worth measuring as a lower-memory Postgres option, but it
should not be selected unless recall and tuning behavior are good enough.

FAISS, hnswlib, and Annoy should remain future options only if pgvector cannot
meet the numeric gates above. They may be powerful, but they add index sync,
packaging, and local-first maintenance complexity that Find should not accept
without clear benchmark wins.
