# Search Evaluation Harness

- **Status:** Implemented
- **Related:** Issue #100. Dependency for #99 and
  `docs/research/search-retrieval-benchmark-plan.md`.

Repeatable, local, offline scoring for Find's semantic search. Search changes
cannot be judged from screenshots, and "it feels better" is not a result that
survives the next change. This produces numbers two runs apart can be diffed.

**Nothing leaves the machine.** No images, embeddings, labels, or results are
uploaded. Datasets reference media by id only and never contain image bytes.

## Quick start

Prove the harness itself works, with no database, models, or photos:

```bash
cd backend
uv run python scripts/evaluate_search.py \
    --dataset tests/fixtures/search_eval/smoke_dataset_v1.json \
    --stub tests/fixtures/search_eval/smoke_run_v1.json
```

Score a live instance with an indexed library:

```bash
uv run python scripts/evaluate_search.py \
    --dataset my_dataset.json --api --base-url http://localhost:8000 \
    --json --out baseline.json
```

Then, after a change, produce `candidate.json` the same way and diff the two.

> **`ML_MODE=mock` results are not relevance measurements.** The mock embedder
> is unrelated to the real weighting scheme. Mock is for checking that the
> plumbing runs, nothing more.

## Dataset format

Versioned JSON, `schema_version: 1`:

```json
{
  "schema_version": 1,
  "dataset_id": "my-library-v1",
  "description": "what this set is for",
  "k_values": [5, 10],
  "queries": [
    {
      "id": "q-bicycle",
      "query": "red bicycle leaning on a wall",
      "relevant": ["1042", "1189"],
      "category": "object",
      "notes": "optional free text"
    }
  ]
}
```

`relevant` holds the `media_id` values your instance returns. `category` is
optional and drives per-slice reporting — use it, because an aggregate hides a
category that collapsed.

**`dataset_id` is load-bearing.** It is recorded in every result file, so a set
of numbers can never be silently compared against a different revision. Bump it
whenever queries or judgements change. Revisions are not mergeable with their
predecessors; a changed dataset invalidates prior results rather than extending
them.

## Metrics, and how they are defined

The exact conventions matter, because they change the numbers:

| Metric | Definition | Note |
| --- | --- | --- |
| Precision@K | hits in top K **/ K** | Returning fewer than K results is penalised for the slots left empty |
| Recall@K | hits in top K / **number of relevant** | Cannot reach 1.0 if a query has more relevant items than K |
| MRR | mean of 1/(rank of first hit) | Misses contribute 0, so they drag the mean down rather than being skipped |
| Empty-result rate | queries returning zero rows / all queries | |
| Latency | p50/p95/p99, nearest-rank | Not interpolated — an interpolated p95 over 20 samples invents a number no query produced |

Ranks are 1-based. Duplicate ids in a ranking count once, at their first
position.

If a query lists more relevant items than the smallest `k`, the loader emits a
warning into `dataset_warnings`, because that query's recall is capped below 1.0
and quietly drags the aggregate down.

## Writing a dataset without fooling yourself

This is the part that decides whether the numbers mean anything.

**Write queries before you look at results.** If you run a search, see what
comes back, and then write down what was relevant, you have measured that
search's current behaviour and called it ground truth. Every later change will
look like a regression. Decide what *should* match, then measure.

**Judge relevance by the query, not by the ranking.** An item is relevant
because it satisfies what the user asked, not because it scored well.

**Cover the categories that fail differently.** At minimum:

- text-heavy documents (receipts, screenshots, invoices)
- faces and people
- scenes with no salient object (landscapes, textures)
- single-word queries
- multi-concept queries ("dog on a beach at sunset")
- hard negatives — queries with no correct answer in the corpus, which catch a
  system that returns something plausible-looking for everything

**Keep relevant sets small.** Aim for fewer relevant items than the smallest
`k`. Large relevant sets cap recall and compress the differences you are trying
to see.

**Do not tune the dataset to make a change look good.** If a variant fails on
some queries, that is the result. Deleting inconvenient queries produces a
dataset that only rewards the change you already wanted to ship.

**Include queries you expect to fail.** A dataset every candidate passes cannot
distinguish between candidates.

**Size.** 30–50 queries is enough to see a real effect and small enough to
maintain honestly. Below ~20, single-query noise dominates the aggregate.

## Adding cases to an existing dataset

1. Add the query object with a new unique `id`.
2. Fill `relevant` by deciding what *should* match, then confirming those ids
   exist in your library.
3. Bump `dataset_id` — adding queries changes what the aggregate means.
4. Re-run the baseline. Prior numbers are not comparable across the bump.

## Output

`--json` (and `--out`) emit a `result_schema_version: 1` document containing
`dataset_id`, per-K precision and recall, MRR, empty-result rate, error count,
latency percentiles, per-category MRR, and `worst_cases` — every query with no
relevant hit, plus any retriever error.

`worst_cases` is a required output rather than a footnote. A variant that lifts
mean recall while destroying one query class is worse for real users than its
average suggests, and only the per-query view shows that.

## Scoring the Track C ranking variants

`--db` retrieves candidates straight from Postgres and ranks them with one of
the query-side variants defined in
`docs/research/search-retrieval-benchmark-plan.md` (issue #99). It needs database
access and real model weights in the same process.

```bash
cd backend

# One variant, end-to-end latency included
uv run python scripts/evaluate_search.py \
    --dataset my_dataset.json --db --variant C3 --out c3.json

# The whole matrix, one retrieval per query shared by all seven variants
uv run python scripts/evaluate_search.py \
    --dataset my_dataset.json --db --all-variants --out trackc.json
```

| Variant | Changes, relative to production |
| --- | --- |
| `C0` | Nothing — the production baseline |
| `C1` | No similarity threshold |
| `C2` | Adaptive threshold from the pool's score spread |
| `C3` | Candidate pool of 100 before reranking, instead of `k` |
| `C4` | `C3` plus recency, favourite, and album signals |
| `C5` | Drops the hardcoded `TEXT_QUERY_TERMS` bonus |
| `C6` | Reweighted boost coefficients and a higher cap |

Three things to know before reading the output:

- **`--all-variants` shares one candidate pool across variants.** That is what
  makes the comparison fair — identical input, so a metric difference is the
  ranking rule and nothing else. It also means the reported latency covers
  ranking only. For end-to-end latency, score a single variant. The output says
  which mode produced it.
- **Retrieval is pinned to exact search.** An HNSW index is deployed, so without
  pinning, ANN recall error would show up as a ranking difference. `--approximate`
  opts back into the index when the deployed path is what you want to measure.
- **`ML_MODE=mock` is refused, not silently used.** The mock embedder is
  unrelated to the production weighting scheme, so it would emit a complete,
  plausible results table that means nothing. Use `--stub` to exercise plumbing.

## Extending with a new retriever

A retriever is any callable `(EvalQuery, k) -> Sequence[str]` returning ranked
media ids. Three ship today: `stub_retriever` (canned rankings), the `--api`
retriever (HTTP against a live instance), and `--db` (pgvector plus a Track C
variant). Scoring is identical for all of them — which is the point, since two
runs are only comparable when the scoring path is the same. To benchmark an
experimental branch, add a retriever rather than forking the scoring.

For a query-side experiment specifically, prefer adding a `RankingVariant` in
`find_api.evaluation.variants` over a whole retriever: variants are pure
functions over a `Candidate` pool, so they are unit-testable without a database
and they automatically share the pool with every other variant in a run.

## Validation

```bash
cd backend
uv run python scripts/evaluate_search.py \
    --dataset tests/fixtures/search_eval/smoke_dataset_v1.json \
    --stub tests/fixtures/search_eval/smoke_run_v1.json
uv run ruff check . && uv run ruff format --check .
ML_MODE=mock uv run pytest -q
```

The smoke fixture is deterministic and hand-checkable. Its five queries cover a
perfect hit, a mid-rank hit, a partial hit, a total miss, and an empty response,
giving P@5 = 0.16, R@5 = 0.50, MRR = 0.3667, empty-result rate = 0.20. Those
values are asserted in `backend/tests/test_search_eval.py`, so a change to the
scoring math fails the suite rather than silently shifting every future result.

## References

- `docs/research/search-retrieval-benchmark-plan.md` — the experiment matrix
  this harness feeds
- `docs/plans/partial/local-search-quality-roadmap.md` — target metrics
- `backend/src/find_api/evaluation/` — dataset, metrics, runner
- `backend/scripts/evaluate_search.py` — CLI entry point
