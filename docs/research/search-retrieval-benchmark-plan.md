# Research: Search Retrieval and Ranking Benchmark Plan

- **Status:** Experimental design complete. **Results are blocked on #100** and are deliberately
  absent from this document.
- **Date:** 2026-08-03
- **Related:** Issue #99. Depends on the evaluation harness in #100. Extends
  `docs/research/vector-search-benchmarks.md` (index performance) and
  `docs/plans/partial/local-search-quality-roadmap.md` (targets and sequencing).
- **Scope:** Protocol, candidate matrix, and decision gates only. No production search change is
  proposed here, and no cloud or private evaluation service is used.

## Why there are no numbers in this document

Issue #99 states plainly: *"Do not start final comparisons until the same labeled dataset and
metrics can evaluate every candidate."* Issue #100, which builds that harness and defines the
versioned labeled query set, is still open.

Publishing relevance numbers before that exists would produce figures that cannot be reproduced,
cannot be compared across candidates, and would nonetheless get cited in later decisions. So this
document delivers everything that does **not** depend on the harness — the baseline audit, the
candidate matrix, the measurement protocol, and the adoption gates — and stops precisely where real
data is required. When #100 lands, the results table can be filled in without redesigning anything.

## Baseline audit: three stale assumptions

Before comparing anything, the assumed baseline had to be checked against the code. Three things
have drifted, and the third materially affects how #99 must be run.

**1. Reranking is not absent; it is partial.** The roadmap lists "no reranking stage" as a current
weakness, but `backend/src/find_api/ml/search_ranking.py` already exists and applies text-aware
boosting driven by a `TEXT_QUERY_TERMS` set (`invoice`, `receipt`, `screenshot`, `document`, …)
plus object-label extraction. The baseline for #99 is therefore *vector retrieval plus a keyword-
triggered metadata boost*, not raw cosine ranking. Measuring "add reranking" against a baseline
that already reranks would attribute the wrong effect.

**2. Latency instrumentation is already in place.** `routers/search.py` records `embedding_ms` and
separates query-embedding time from retrieval. #99 does not need to add timing plumbing; it needs
to record what is already emitted.

**3. Find is very likely already serving approximate results, and recall has never been measured.**
This is the important one. Migration `hnsw_vector_idx_001` created
`ix_media_vector_hnsw ON media USING hnsw (vector vector_cosine_ops)`, and search issues
`ORDER BY vector <=> :embedding … LIMIT :limit`, which the Postgres planner will normally satisfy
from that index. Meanwhile `docs/research/vector-search-benchmarks.md` still describes exact
pgvector scan as "current default" and frames its adoption gates as *when to start* evaluating ANN.

Two consequences follow:

- The index was created with **default HNSW build parameters** (`m`, `ef_construction`), and
  **`hnsw.ef_search` is never set anywhere in the codebase**, so pgvector's default query-time
  candidate list applies. Nobody chose these values against Find's data.
- The "recall is perfect by definition because exact search is still used" line in the existing gate
  list is no longer safe to rely on. **Recall against exact search is now an unmeasured quantity in
  production**, and quantifying it is the single highest-value measurement in this whole effort.

Practical effect on the protocol: every embedding-quality comparison below must pin retrieval to
exact search (`SET LOCAL enable_indexscan = off`, or a dedicated exact query path) so that ANN
approximation error cannot be mistaken for an embedding effect. That separation is also what the
issue's "separate embedding-quality findings from index-performance findings" criterion demands.

## Division of labour with the existing benchmark doc

`vector-search-benchmarks.md` already covers index performance thoroughly — ANN candidate
comparison, DB latency percentiles, build time, memory, and numeric adoption gates. That work is
not repeated here.

| Concern | Owner |
| --- | --- |
| ANN candidates (HNSW/IVFFlat/FAISS/hnswlib/Annoy), build time, index memory, DB latency percentiles, ANN adoption gates | `vector-search-benchmarks.md` |
| Embedding composition, query-side handling, reranking signals, threshold behaviour, end-to-end relevance | This document |
| Measured recall of the **currently deployed** HNSW configuration vs exact | This document — see [Track A](#track-a-index-fidelity) |

## Experiment tracks

### Track A: index fidelity

One question, and it is a correctness question rather than a tuning one: **how much recall is the
deployed HNSW configuration actually costing?**

- A1 — Exact search (`enable_indexscan = off`). Ground truth for every other measurement.
- A2 — Current HNSW, default build params, default `ef_search`. The configuration users run today.
- A3 — Current HNSW with `hnsw.ef_search` swept (e.g. 40 / 100 / 200 / 400).
- A4 — HNSW rebuilt with raised `m` / `ef_construction`, `ef_search` swept again.

Report recall@10 of each against A1 on identical query vectors, with DB latency percentiles
alongside. A2's recall number is the headline result of this track: if it is high, the existing gate
framing simply needs correcting; if it is low, this is a live quality regression that predates #99
and should be raised immediately rather than waiting for the full benchmark.

### Track B: embedding quality

All Track B runs use exact retrieval, so differences are attributable to the vector alone.

The current production vector is built by `generate_hybrid_embedding` in `workers/processors.py`:
image, caption, and detected-object text are embedded separately and combined by a weighted average
whose weights depend on which signals are present — equal thirds with all three, halves with two,
image alone otherwise — with OCR-aware weights renormalised across active signals when OCR text
exists. Empty strings are deliberately never embedded, because CLIP maps them to a fixed non-zero
vector that would bias every image lacking that signal.

| ID | Variant | Question it answers |
| --- | --- | --- |
| B0 | Current hybrid (baseline) | Reference for every delta |
| B1 | Image-only | How much do text signals contribute at all? Also the honest fallback if captioning proves unreliable |
| B2 | Text-weighted | Does upweighting caption/OCR help conceptual queries, and what does it cost on visual ones? |
| B3 | OCR/object-aware | Does routing weights by *query* type beat fixed per-image weights? |
| B4 | Caption-free | Isolates caption contribution — directly informs the caption-reliability stage of the roadmap |
| B5 | Dual-vector | Store image and text vectors separately, combine at query time. Costs storage and an index; buys per-query weighting instead of per-image |

B5 is the only variant that changes the storage schema. It is included because fixing the
image/text ratio at *index* time is the baseline's most questionable property — the right ratio
plainly differs between "photos of my dog" and "invoice from March" — but its cost means it needs
the clearest evidence before adoption.

### Track C: query-side and ranking

Baseline is B0 plus the existing `search_ranking` boost, exact retrieval.

| ID | Variant | Question it answers |
| --- | --- | --- |
| C0 | Current: static threshold + existing keyword boost | Reference |
| C1 | No threshold | How many valid results does the static cutoff discard? The roadmap already flags this as suspected |
| C2 | Adaptive threshold from score distribution | Can the cutoff adapt to per-query score spread instead of a constant? |
| C3 | Wider candidate pool, then metadata rerank | The issue's "candidate-pool reranking" requirement — retrieve k=100, rerank to 24 |
| C4 | C3 plus recency/favourite/album signals | Do non-semantic signals help or just add noise? |
| C5 | Query expansion for `TEXT_QUERY_TERMS` | Is the hardcoded keyword list earning its place, or is it overfit? |

C1 and C5 are deliberately framed as *challenges to existing behaviour*. Both are currently
unjustified by measurement, and a benchmark that only ever proposes additions will never remove
anything.

## Measurement protocol

**Dataset.** Whatever #100 defines, unchanged, at its pinned version. Recorded in every result row.
No candidate may be evaluated on a different set, and any dataset revision invalidates prior rows
rather than being merged with them.

**Library sizes.** The issue requires small/medium local results, not only synthetic scale. Report
three tiers separately and never average across them:

| Tier | Indexed media | Represents |
| --- | --- | --- |
| Small | ~1k | A new or casual library |
| Medium | ~10k | A realistic personal library — **the primary decision tier** |
| Synthetic scale | 50k+ | Where index behaviour, not embedding quality, dominates |

**Metrics per run.** Relevance: recall@5, recall@10, precision@10, MRR, empty-result rate. Latency:
p50/p95/p99 for query embedding, retrieval, and rerank separately, plus end-to-end. Cost: peak
worker RSS during indexing, wall-clock reindex time for the full corpus, per-image index time,
stored bytes per media. Failure modes: qualitative, and mandatory — see below.

**Repetitions.** Five runs per configuration, report median and spread. Latency on a laptop under
thermal variance is noisy enough that a single run can invert an ordering.

**Environment.** Record CPU model, RAM, `ML_MODE`, `ACCEL_MODE`, resolved device, Postgres version,
pgvector version, and whether the machine was on battery. Runs on different hardware are not
comparable and must not share a table.

**Isolation.** `ML_MODE=mock` must never be used for relevance measurement — the mock embedder's
fixed 0.45/0.55 blend is unrelated to the real weighting scheme and would produce meaningless
numbers. Mock is appropriate only for exercising harness plumbing.

**Failure-mode reporting is a required output, not a footnote.** For each variant, record the
queries where it does worst, not only its aggregate. A variant that lifts mean recall while
catastrophically failing one query class is worse for real users than its average suggests, and
aggregates hide exactly that. Minimum categories to report per variant: text-heavy documents,
faces/people, scenes with no salient object, queries with no correct answer in the corpus, and
single-word queries.

## Decision gates and rollback boundaries

**Adopt an embedding variant** only when, at the medium tier: recall@10 improves by ≥ 3 points
absolute over B0; no reported failure category regresses by more than 2 points; indexing time and
worker RSS stay within the local-first budget; and reindex cost is stated in wall-clock terms for a
10k library, because adoption implies a full reindex.

**Adopt a ranking variant** when: precision@10 improves by ≥ 3 points with recall@10 not regressing;
added rerank latency keeps end-to-end p95 under the roadmap's 500 ms target; and it introduces no
new service.

**Reject outright**, regardless of relevance: anything requiring a network service, anything
requiring a model that cannot be fetched by the existing model-cache path, anything pushing p95
end-to-end past 500 ms, and anything degrading `ML_MODE=mock` startup so the offline developer
experience breaks.

**Rollback boundaries**, by blast radius:

| Change class | Rollback | Reversible without reindex? |
| --- | --- | --- |
| `hnsw.ef_search` tuning | Change one setting | Yes — runtime only |
| Threshold / rerank logic (Track C) | Revert code | Yes — query-side only |
| HNSW rebuild with new `m` / `ef_construction` | Rebuild index | Yes, but requires an index build window |
| Embedding weights (B1–B4) | Revert code **and full reindex** | No |
| Dual-vector storage (B5) | Revert code, migration, **and full reindex** | No |

Anything below the line in that table needs a reindex to undo. That asymmetry, not the relevance
delta alone, should drive how much evidence is demanded: an `ef_search` change can ship on thin
evidence because it is free to revert; a schema change cannot.

## Suggested sequence

1. **Track A2 first**, immediately when #100 lands. It is one measurement, it validates or
   invalidates the existing gate framing, and it may surface a live regression.
2. Track A3/A4 — cheap, runtime-only, fully reversible.
3. Track C — query-side only, no reindex, so iteration is fast.
4. Track B1/B4 — establishes how much the text signals actually contribute before anything is tuned.
5. Track B2/B3 — tuning, only if B1/B4 show headroom.
6. Track B5 — last, and only with clear evidence, since it is the only irreversible schema change.

Ordering rationale: everything reversible is measured before anything irreversible, and the
cheapest measurement that could invalidate the plan runs first.

## Out of scope

- Shipping a production search rewrite.
- Any private or cloud evaluation service; all measurement stays local.
- Replacing SigLIP with a different backbone — that is a separate question with its own model-cache
  and download-size implications, and it would invalidate every baseline here.
- ANN engine selection beyond pgvector, which `vector-search-benchmarks.md` already owns.

## Follow-ups this audit raises

1. `docs/research/vector-search-benchmarks.md` describes exact scan as the current default and
   frames its gates as "when to start ANN evaluation." An HNSW index has since landed. That
   status needs correcting once Track A2 quantifies the actual recall.
2. `docs/plans/partial/local-search-quality-roadmap.md` lists "no reranking stage" as a current
   weakness; `search_ranking.py` exists. Worth correcting so the roadmap does not motivate work
   that is partly done.
3. No `hnsw.ef_search` is set anywhere. Even before benchmarking, making this an explicit,
   documented setting rather than an inherited default is worthwhile — it is currently a
   production-visible knob nobody chose.

## References

- `docs/research/vector-search-benchmarks.md` — index performance, ANN candidates, adoption gates
- `docs/plans/partial/local-search-quality-roadmap.md` — target metrics and stage sequencing
- `backend/src/find_api/workers/processors.py` — `generate_hybrid_embedding`, the B0 baseline
- `backend/src/find_api/ml/search_ranking.py` — existing keyword/object boosting
- `backend/src/find_api/routers/search.py` — retrieval query, static threshold, timing instrumentation
- `backend/alembic/versions/add_hnsw_vector_index.py` — the HNSW index and its default parameters
