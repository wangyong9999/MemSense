# Experiment: Keyword Overlap Boost (OPTIMIZATION_INSIGHTS 2.1)

Date: 2026-04-10
Status: **Completed — No measurable improvement, flag kept OFF**

## Hypothesis

Prior work demonstrated +1.2% on LongMemEval by adding a keyword-overlap reranking
layer after BM25+semantic fusion. Applying the same technique to MemSense's recall
pipeline should yield +1-2% precision improvement.

## Implementation

Feature flag: `HINDSIGHT_API_KEYWORD_BOOST_ENABLED` (default: false)
Weight: `HINDSIGHT_API_KEYWORD_BOOST_WEIGHT` (default: 0.15, max +15% per-candidate boost)

Files created (independent, minimal coupling to upstream Hindsight):
- `engine/search/keyword_boost.py` — keyword extraction (EN+CN), overlap scoring, boost functions
- `tests/test_keyword_boost.py` — 26 unit tests

Call site: `memory_engine.py` Step 4.7, after combined scoring, before token filter.

Two variants tested:
1. **Pre-rerank** (Step 3.5): Boost `MergedCandidate.rrf_score` between RRF and cross-encoder
2. **Post-rerank** (Step 4.7): Boost `ScoredResult.weight` after cross-encoder + combined scoring

## Validation Method

Pure recall A/B test (no LLM calls needed):
- 30 questions sampled from baseline (15 wrong + 15 correct, conv-48)
- Metrics: Hit Rate @5, Hit Rate @10, MRR (Mean Reciprocal Rank)
- Each question run with flag OFF then flag ON, same memory bank

## Results

### Pre-rerank variant (Step 3.5, weight=0.15)

| Metric | OFF | ON | Delta |
|--------|-----|-----|-------|
| avg top-5 evidence | 1.80 | 1.80 | +0 |
| avg top-10 evidence | 3.00 | 3.00 | +0 |

**Zero change.** Cross-encoder completely overwrites RRF score adjustments.

### Post-rerank variant (Step 4.7, weight=0.15 and 0.50)

| Metric | OFF | ON (0.15) | ON (0.50) |
|--------|-----|-----------|-----------|
| Hit Rate @5 | 80.0% | 80.0% | 80.0% |
| Hit Rate @10 | 80.0% | 80.0% | 80.0% |
| MRR | 0.7204 | 0.7201 | 0.7201 |
| Rank changes | — | 1/30 (0↑ 1↓) | 1/30 (0↑ 1↓) |

**Negligible change.** Even 50% max boost cannot alter ranking meaningfully.

## Root Cause Analysis

1. **Cross-encoder absorbs keyword signal**: The cross-encoder (ms-marco-MiniLM-L-6-v2) inherently
   scores documents with query-keyword overlap higher. Keyword boost is redundant — it adds a
   signal that the cross-encoder already captures.

2. **Pre-filter doesn't trigger**: `reranker_max_candidates=175` exceeds typical candidate count,
   so pre-rerank boost doesn't change which candidates enter the cross-encoder.

3. **Prior work had no cross-encoder**: The +1.2% was measured on a pipeline without neural
   reranking — keyword overlap was the *only* exact-match signal. Hindsight's cross-encoder
   already captures this, making the boost redundant.

## Decision

- Feature flag stays `false` (default OFF)
- Code kept in codebase for potential future use:
  - Scenarios with `reranker_provider=none` (no cross-encoder)
  - Very large candidate sets where pre-filter becomes relevant
- **Not recommended** for any pipeline that includes cross-encoder reranking

## Lessons Learned

- Always validate borrowed techniques against your own pipeline — improvements measured on
  simpler architectures may not transfer to more sophisticated ones.
- Cross-encoder reranking is extremely effective at capturing exact-match signal; additional
  keyword-based scoring on top is redundant.
- The pure recall A/B test (no LLM) is a fast validation tool (~2 min for 30 questions) that
  should be used before investing in slow end-to-end eval.

## Next Steps (from OPTIMIZATION_INSIGHTS.md)

Skip 2.1, proceed to higher-ROI items:
- **2.2 Retrieval cache** — still valuable (reduces latency, no precision dependency)
- **2.3 L0/L1 digests** — still valuable (token savings, independent of ranking)
- **2.5 OOD detection** — still valuable (uses RRF/CE scores as threshold signals)
