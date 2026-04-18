# Experiment: GLM-5 LoCoMo Baseline

Date: 2026-04-16
Status: **Baseline established; conv-42 anomaly pending investigation**

## Configuration

| Component | Setting |
|-----------|---------|
| LLM (ingestion) | GLM-5 via Anthropic-compatible API (113.46.219.251:8080) |
| LLM (answer gen) | GLM-5 (same) |
| LLM (judge) | GLM-5 (same) |
| Embeddings | local BAAI/bge-small-en-v1.5 |
| Reranker | local cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Database | pg0://bench-locomo-glm |
| Enrichment at ingest | Default (no mission, no P1, no date_validation) |
| Observations | No (raw facts only) |

Banks ingested: 2026-04-14, 10 conversations, 2172 total facts.
Evaluation: 2026-04-16, skip-ingestion, 1540 questions.

## Results

### Per-Conversation

| Conv | Total | Correct | Accuracy | Cat1(MH) | Cat2(SH) | Cat3(Temp) | Cat4(OD) |
|------|-------|---------|----------|----------|----------|------------|----------|
| conv-41 | 152 | 138 | 90.79% | 29/31 | 24/27 | 5/8 | 80/86 |
| conv-47 | 150 | 136 | 90.67% | 20/20 | 29/34 | 8/13 | 79/83 |
| conv-30 | 81 | 73 | 90.12% | 10/11 | 24/26 | — | 39/44 |
| conv-50 | 158 | 140 | 88.61% | 28/32 | 30/32 | 6/7 | 76/87 |
| conv-48 | 191 | 169 | 88.48% | 17/21 | 39/42 | 7/10 | 106/118 |
| conv-44 | 123 | 108 | 87.80% | 28/30 | 19/24 | 3/7 | 58/62 |
| conv-26 | 152 | 132 | 86.84% | 26/32 | 31/37 | 12/13 | 63/70 |
| conv-49 | 156 | 135 | 86.54% | 32/37 | 28/33 | 10/13 | 65/73 |
| conv-43 | 178 | 149 | 83.71% | 28/31 | 19/26 | 7/14 | 95/107 |
| **conv-42** | **199** | **118** | **59.30%** | 23/37 | 20/40 | 4/11 | 71/111 |

### Aggregate

| Metric | Value |
|--------|-------|
| **Overall** | **84.29% (1298/1540)** |
| **Excluding conv-42** | **88.00% (1180/1341)** |
| Cat1 (Multi-hop) | 81.85% (241/294) |
| Cat2 (Single-hop) | 84.55% (283/321) |
| Cat3 (Temporal) | 62.26% (62/106) |
| Cat4 (Open-domain) | 86.90% (712/819) |

### Category Analysis

- **Multi-hop (Cat1)**: 81.85% — GLM handles cross-session reasoning reasonably
- **Single-hop (Cat2)**: 84.55% — direct fact retrieval is solid
- **Temporal (Cat3)**: 62.26% — weakest category; date reasoning is a known LLM challenge
- **Open-domain (Cat4)**: 86.90% — general knowledge questions perform well

## conv-42 Anomaly

conv-42 scored 59.30%, dragging the overall accuracy down by ~5pp. Key observations:

- **Not caused by API errors**: 92 invalid JSON retries distributed evenly across
  all conversations (~30 each in three roughly equal chunks), not concentrated in conv-42
- **All categories uniformly low**: Cat1 62%, Cat2 50%, Cat3 36%, Cat4 64% — not
  a single-category failure
- **0 invalid questions**: All 199 questions were evaluated, none marked invalid
- **Bank has adequate data**: 236 facts ingested (above average)

Possible causes (to investigate):
1. GLM-5 answer generation quality is poor on conv-42's topic/style
2. GLM-5 as judge is overly strict on conv-42 answers
3. Retrieval quality issue specific to conv-42's entity/topic structure

**Recommended next step**: Re-run conv-42 evaluation with a different judge model
(e.g., MiniMax or GPT-4o-mini) to isolate answer-quality vs. judge-quality.

## Notes

- This is GLM-5's first LoCoMo evaluation — serves as the baseline for future
  optimization experiments
- GLM ingestion used default settings (no retain_mission, no post-extraction
  enrichment). Future experiments can measure the impact of enabling these features
  with GLM as the extraction LLM
- Results saved to `benchmark_results_glm5_baseline.json`
- 92 "invalid JSON" retries observed — GLM-5's structured JSON output is less
  reliable than MiniMax. May need prompt engineering or fallback parsing

## MiniMax M2.7 Reference (from prior experiments, NOT same-bank comparison)

These numbers are from MiniMax evaluation on MiniMax-ingested banks with datefix
enrichment. They are NOT directly comparable (different ingestion, different LLM
for all stages) but provide context:

| Conv | MiniMax (datefix) | GLM-5 (baseline) | Note |
|------|-------------------|-------------------|------|
| conv-30 | 87.65% (71/81) | 90.12% (73/81) | |
| conv-41 | 92.11% (140/152) | 90.79% (138/152) | |
| conv-42 | 89.45% (178/199) | 59.30% (118/199) | GLM anomaly |
| conv-43 | 85.96% (153/178) | 83.71% (149/178) | |
| conv-44 | 83.74% (103/123) | 87.80% (108/123) | |
| conv-47 | 90.00% (135/150) | 90.67% (136/150) | |
| conv-48 | 89.53% (171/191) | 88.48% (169/191) | |
| conv-49 | 90.38% (141/156) | 86.54% (135/156) | |
| conv-50 | 93.04% (147/158) | 88.61% (140/158) | |
| conv-26 | 88.82% (135/152) | 86.84% (132/152) | |
| **Overall** | **89.22% (1374/1540)** | **84.29% (1298/1540)** | |
| **Excl conv-42** | **89.19% (1196/1341)** | **88.00% (1180/1341)** | Gap narrows to 1.2pp |

**Important**: This is a cross-model reference, not an apples-to-apples comparison.
A fair comparison requires running MiniMax eval on the same GLM banks, or GLM eval
on MiniMax banks.
