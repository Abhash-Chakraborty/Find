# Research: HNSW Index Fidelity (Track A)

- **Status:** Measured on synthetic corpora. Real-corpus confirmation still outstanding.
- **Date:** 2026-08-03
- **Related:** Issue #99, Track A of `docs/research/search-retrieval-benchmark-plan.md`.
  Reproduced by `backend/scripts/benchmark_hnsw_recall.py`.

## Why this could be measured now

Track A is the one comparison in the benchmark plan that needs no labeled data
and no real photos: the ground truth is exact nearest-neighbour search over the
same vectors, not a human judgement. Everything else in #99 waits on a labeled
dataset over a real library.

The question: migration `hnsw_vector_idx_001` created
`ix_media_vector_hnsw ON media USING hnsw (vector vector_cosine_ops)` with
**default build parameters**, `hnsw.ef_search` is **never set anywhere** in the
codebase, and search issues `ORDER BY vector <=> :q LIMIT :k`, which the planner
normally satisfies from that index. So Find serves approximate results under
parameters nobody chose, and the cost had never been measured.

## Headline result, and a correction

**On clustered corpora — the realistic proxy for image embeddings — the shipped
default configuration returns exact results. Recall@10 = 1.0000, worst query
1.00, at both 1k and 10k, with the *lowest* latency of any configuration
tested.** No change to the index or to `ef_search` is indicated by this evidence.

This **corrects** the concern raised in `search-retrieval-benchmark-plan.md` and
in my comment on #99, where I wrote that Find was "very likely already serving
approximate results" with recall as "an unmeasured quantity" and called
measuring it the highest-value single measurement available. The first half was
right — it is approximate, and it was unmeasured. The implication that it was
therefore probably degraded is not supported. On the realistic distribution the
approximation is exact in practice, and the prior should move from "probably
losing recall" to "probably fine, confirm on real data."

## Results

pgvector 0.8.4, PostgreSQL 16.14, 768 dimensions (SigLIP ViT-B-16), k = 10,
200 queries per configuration, seed 20260803.

`margin` is the mean cosine gap between the 10th and 30th exact neighbour. It
is reported because it decides whether recall means anything at all — see
[Why the margin matters](#why-the-margin-matters).

### Clustered corpus (realistic proxy)

| n | build | ef_search | recall@10 | worst | p50 ms | index build |
| --- | --- | --- | --- | --- | --- | --- |
| 1 000 (margin 0.008) | default | **default (40)** | **1.0000** | 1.00 | 1.89 | 0.26 s |
| 1 000 | default | 100 | 1.0000 | 1.00 | 4.92 | 0.26 s |
| 1 000 | m=32, efc=128 | default (40) | 1.0000 | 1.00 | 3.86 | 0.75 s |
| 10 000 (margin 0.067) | default | **default (40)** | **1.0000** | 1.00 | **1.52** | 4.25 s |
| 10 000 | default | 100 | 1.0000 | 1.00 | 2.04 | 4.25 s |
| 10 000 | default | 200 | 1.0000 | 1.00 | 2.82 | 4.25 s |
| 10 000 | default | 400 | 1.0000 | 1.00 | 4.05 | 4.25 s |
| 10 000 | m=32, efc=128 | default (40) | 1.0000 | 1.00 | 1.74 | 13.3 s |
| 10 000 | m=32, efc=128 | 400 | 1.0000 | 1.00 | 30.03 | 13.3 s |

Every configuration is perfect. The defaults are simply the cheapest of them.

### Uniform corpus (pessimistic bound)

Points spread over the unit sphere. In 768 dimensions these are nearly
equidistant, which is the hardest possible case for a graph index and is *not*
what image embeddings look like.

| n | build | ef_search | recall@10 | worst | p50 ms |
| --- | --- | --- | --- | --- | --- |
| 1 000 (margin 0.018) | default | default (40) | 0.9905 | 0.80 | 1.73 |
| 1 000 | default | 100 | 1.0000 | 1.00 | 4.19 |
| 10 000 (margin 0.014) | default | default (40) | 0.5900 | 0.00 | 2.78 |
| 10 000 | default | 100 | 0.6905 | 0.30 | 4.37 |
| 10 000 | default | 200 | 0.8180 | 0.50 | 6.21 |
| 10 000 | default | 400 | 0.9245 | 0.60 | 8.64 |
| 10 000 | m=32, efc=128 | default (40) | 0.9175 | 0.50 | 4.58 |
| 10 000 | m=32, efc=128 | 400 | 1.0000 | 1.00 | 37.05 |

## Why the margin matters

Recall tracks the **neighbour margin**, not corpus size. Where the 10th and 30th
exact neighbours are well separated (clustered, margin 0.067) recall is perfect.
Where they are nearly tied (uniform, margin 0.014) recall falls — but in that
regime the "missed" neighbours are at almost the same distance as the ones
returned, so a low recall figure overstates the damage. Recall@k is measuring
tie-breaking, not retrieval quality.

This is why the benchmark reports the margin next to every recall number, and
why a recall figure quoted without one should not be trusted.

## A methodology error worth recording

The first run of this benchmark produced recall@10 ≈ 0.26–0.43 at 10k and looked
like clear evidence of a serious production problem. It was wrong, twice over,
and both faults are now covered by tests:

1. **The clustered generator did not cluster.** A per-component sigma of 0.35 in
   768 dimensions gives a noise vector of norm ≈ 9.7 against a unit-norm centre,
   so the structure was completely buried — "clustered" and "uniform" were
   silently the same distribution, and produced matching numbers (0.2635 vs
   0.2750) that looked like corroboration.
2. **Queries were generated independently of the corpus.** A second
   `make_vectors()` call picks fresh cluster centres, so queries landed nowhere
   near the corpus. Every candidate sat at roughly the same distance — the 10th
   and 60th neighbours differed by 0.0198 cosine — and recall@10 degenerated
   into rank agreement among near-ties.

Both were caught by sanity checks rather than by the numbers looking wrong: the
numbers looked plausible and alarming, which is the dangerous combination. What
exposed them was measuring intra- versus inter-cluster similarity (0.0105 vs
0.0005 — no clustering at all) and printing the distance to the Nth neighbour.

Queries are now perturbations of sampled corpus vectors, which is what a real
text query does: it embeds near the images it describes.

## Operational findings

- **Default build is cheap.** 10k vectors index in 4.25 s; raising to
  `m=32, ef_construction=128` costs 13.3 s for no recall gain on clustered data.
- **Raising `ef_search` costs latency for nothing on realistic data.** At 10k
  clustered, going 40 → 400 takes p50 from 1.52 ms to 4.05 ms with recall
  unchanged at 1.0000.
- **The expensive combination is genuinely expensive.** `m=32, efc=128` with
  `ef_search=400` costs 30 ms p50 at 10k — 20× the default for no benefit.
- **Large builds with raised parameters are painful.** A 50k build at
  `m=32, ef_construction=128` was still running after 15 minutes at default
  `maintenance_work_mem` and was aborted. If those parameters are ever adopted,
  build cost needs its own measurement and probably a `maintenance_work_mem`
  bump. The 50k tier is therefore **not** covered by the table above.

## What this does not establish

The vectors are synthetic, not SigLIP embeddings. This characterises the *index
configuration*; it is not a measurement of Find's search quality. Real
embeddings have their own intrinsic dimensionality and cluster structure, and
the honest summary is that they sit somewhere between the two distributions
tested — much closer to the clustered end, on the evidence of how image
embedding spaces normally behave.

Outstanding, and still requiring a real indexed library:

- Recall of the deployed configuration against exact search on real SigLIP
  vectors, with the neighbour margin reported alongside.
- The 50k+ tier, including build cost with raised parameters.
- Everything in Tracks B and C, which need labeled relevance judgements and are
  still blocked on a dataset.

## Recommendation

Scoped to what was actually measured — synthetic clustered corpora at 1k and
10k, 768 dimensions, pgvector 0.8.4:

**Make no index change on the strength of this evidence**, and drop the pending
action to raise `ef_search`. On the tested clustered corpora the defaults were
both exact and the cheapest option, so raising `ef_search` would buy latency and
nothing else. That is a reason *not to act yet*, not a clearance of the
configuration for all real libraries — the uniform results show the same
defaults falling to 0.59 recall once neighbours stop being separated, and
nothing here establishes which regime real SigLIP vectors sit in.

Keep the explicit-setting suggestion, but for a different reason than before:
`hnsw.ef_search` being unset is worth documenting as a deliberate choice rather
than an inherited default, so a future pgvector version changing it is a visible
event. That is a documentation change, not a tuning one.

### Confirming against a real library

`benchmark_hnsw_recall.py` **cannot** do this. It generates its corpus, has no
flag for real vectors, and DROPs/CREATEs its own `hnsw_bench` table — so it must
be pointed at a scratch database, never at a production DSN, and running it
against `$DATABASE_URL` would measure synthetic data while writing to the real
database.

A real-corpus Track A run needs a separate, read-only measurement against the
actual `media` table: sample query vectors from indexed rows, take exact top-k
with `enable_indexscan = off`, compare against the normal indexed path, and
report the neighbour margin alongside. That is the outstanding work.

## References

- `backend/scripts/benchmark_hnsw_recall.py` — reproduces every number here
- `backend/tests/test_hnsw_recall_benchmark.py` — pins both methodology errors
- `docs/research/search-retrieval-benchmark-plan.md` — Track A, and the concern
  this document corrects
- `docs/research/vector-search-benchmarks.md` — ANN candidate comparison
- `backend/alembic/versions/add_hnsw_vector_index.py` — the index under test
