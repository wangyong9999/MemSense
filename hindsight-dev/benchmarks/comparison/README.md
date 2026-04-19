# Benchmark comparison runs

This directory holds comparison reports that quantify the impact of the
MemSense flag matrix against the upstream Hindsight baseline.

## Running

```bash
# Default: LoComo, full dataset
scripts/benchmarks/run-comparison.sh

# LongMemEval with a trimmed dataset for a quick signal
scripts/benchmarks/run-comparison.sh --benchmark longmemeval --max-conversations 5 --max-questions 30

# Only a subset of cells
scripts/benchmarks/run-comparison.sh --cells baseline,all_on
```

Each run creates a timestamped subdirectory `YYYYMMDDTHHMMSSZ-<benchmark>/`
containing:

- `baseline.json`, `enrichment.json`, `cache.json`, `all_on.json` — raw
  results per cell (full detail per question and per conversation)
- `SUMMARY.md` — rendered comparison table

## Cell matrix

| Cell | `RETAIN_POST_EXTRACTION` | `RETAIN_FACT_FORMAT_CLEAN` | `RECALL_CACHE` |
|---|:-:|:-:|:-:|
| `baseline` | off | off | off |
| `enrichment` | on | on | off |
| `cache` | off | off | on |
| `all_on` | on | on | on |

The cells isolate retrieval accuracy changes (enrichment cell) from
latency/cost changes (cache cell) so each contribution is attributable.

## Interpreting

- **Accuracy delta (Δ vs baseline)** — the column to publish alongside any
  MemSense positioning claim. A delta within ±0.2pp with small sample
  sizes should be treated as noise; target ≥ 200 questions per cell
  before drawing conclusions.
- **p50 / p95 / p99 latency** — the cache cell should show a noticeable
  p50 drop when a warm bank is being queried by repeat or fuzzy-similar
  queries; baseline sets the reference.
- **Saved tokens** (from `token_usage` when `TOKEN_ACCOUNTING_ENABLED=true`)
  — not surfaced in SUMMARY.md today; query the DB directly via the
  `/v1/default/usage` endpoint if the token accounting flag was on.

## Prerequisites

- `.env` populated with LLM provider keys
- Database running (embedded pg0 or external)
- Enough LLM budget for 4 × dataset cost — expect several hours on the
  full LoComo set with small models, less with `--max-conversations` and
  `--max-questions` caps.

## Publishing

When a run produces numbers worth citing, copy the `SUMMARY.md` into
`docs/` under the appropriate version tag and link it from the README.
Keep the raw per-cell JSONs so anyone can reproduce the summary.
