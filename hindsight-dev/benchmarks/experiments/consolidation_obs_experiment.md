# Experiment: Consolidation + Observations for LoCoMo (matching Hindsight official config)

Date: 2026-04-12
Status: **Observations cause -1.5pp regression on MiniMax M2.7**

## Hypothesis

Hindsight official achieves 92.0% on LoComo with observations enabled (blog post
cites observations as "#1 contributor"). Replicating this config should close the
gap from our 89.1% baseline.

## Setup

- New pg0 instance: `bench-locomo-minimax-with-obs`
- Ingest: 10 conversations, extraction_mode=concise (default)
- Consolidation: explicit `run_consolidation()` per bank after ingest
- Result: 2071 raw facts + 1461 observations = 3532 total memory units
- Eval: quick mode (conv-49/44/48, 470 questions)

## Results

| Conv | Without obs (89.1%) | With obs | Delta |
|------|-------------------|----------|-------|
| conv-49 | 91.0% (142/156) | 89.1% (139/156) | -1.9pp |
| conv-44 | 89.4% (110/123) | 83.7% (103/123) | -5.7pp |
| conv-48 | 87.4% (167/191) | 89.0% (170/191) | +1.6pp |
| **Total** | **89.1% (419/470)** | **87.7% (412/470)** | **-1.5pp** |

## Root Cause Analysis

Observations **compete with raw facts for the fixed 4096 token budget**:

1. In the "Audrey dresses up dogs" query, 51 observations consumed 1305 tokens
   (32% of budget), displacing ~30 precise raw facts
2. Cross-encoder ranks observations higher (broader semantic match) but they
   lack the specific details benchmark questions require
3. In one query, 9/10 top results were observations — almost no raw facts reached the LLM
4. Observation text is more general ("regularly plays fetch with dogs") vs raw fact
   ("Audrey dresses up dogs with party hats for birthdays")

## Why Hindsight official gets 92.0% with observations

Likely explanation: they use a stronger LLM (possibly GPT-4o) for answer generation
that can better extract precise answers from mixed observation+fact context.
MiniMax M2.7 struggles with this mixed context — it tends to use the observation's
general phrasing rather than finding the precise fact buried lower in the results.

## Conclusion

For MiniMax M2.7, observations are net negative on LoCoMo benchmark accuracy.
The token budget competition between observations and facts dilutes retrieval precision.
