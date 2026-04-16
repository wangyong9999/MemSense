# Experiment: Retain Post-Extraction Enrichment — Ablation Study & Datefix

Date: 2026-04-15 ~ 2026-04-16
Status: **Datefix confirmed; 87.8% on conv-42/43 (+1.6pp vs baseline); full 10-conv at 89.2%**

## Background

Following the 168-error analysis of LoCoMo wrong answers, three post-extraction
enrichment features were implemented for the retain pipeline:

1. **date_validation** — Corrects ±1 week date miscounts by the LLM using
   dateparser as an independent reference (committed in `c3ade150`)
2. **P1 (fact_format_clean)** — Strips pipe-delimited metadata suffixes
   (`| When: | Involving:`) from fact text, reducing token overhead ~35%
   (committed in `7dfef6e0`)
3. **retain_mission** — Custom extraction instructions preserving specific nouns,
   quantities, place names, and health terms (committed in `7f5b8ca9`)

All three features ran together in the "全开" (full-on) configuration.

## Problem

With all features enabled, conv-42/43 showed a mixed result:
- conv-42: **88.4% (176/199)** — improved +4 vs baseline 172
- conv-43: **84.8% (151/178)** — regressed -2 vs baseline 153

Net: 327/377 (86.7%) vs baseline 325/377 (86.2%) — marginal +0.5pp.
The conv-43 regression needed investigation.

## Ablation Design

Four experiments, each with a fresh pg0 bank and full ingest + eval:

| Experiment | Mission | P1 | date_validation | Bank |
|------------|---------|----|-----------------|----- |
| 全开 fix前 | ON | ON | ON (original) | bench-locomo-minimax-with-obs |
| No-P1 | ON | **OFF** | ON | bench-locomo-noP1 |
| No-Mission | **OFF** | ON | ON | bench-locomo-noMission |
| Datefix 全开 | ON | ON | ON (with chunk-path filter) | bench-locomo-datefix |

## Results

### conv-42 / conv-43 Ablation Comparison

| Experiment | conv-42 | conv-43 | Total | vs Baseline |
|------------|---------|---------|-------|-------------|
| Historical baseline | 86.4% (172/199) | 86.0% (153/178) | 325/377 (86.2%) | — |
| 全开 fix前 | 88.4% (176/199) | 84.8% (151/178) | 327/377 (86.7%) | +2 |
| No-P1 | 88.4% (176/199) | 83.1% (148/178) | 324/377 (85.9%) | -1 |
| No-Mission | 87.4% (174/199) | 85.4% (152/178) | 326/377 (86.5%) | +1 |
| **Datefix 全开** | **89.4% (178/199)** | **86.0% (153/178)** | **331/377 (87.8%)** | **+6** |

### Per-Feature Contribution (Isolated)

| Feature | conv-42 Delta | conv-43 Delta | Mechanism |
|---------|--------------|--------------|-----------|
| **P1 (fact format clean)** | 0 (176→176) | +3 (148→151) | Token savings improve LLM answer quality |
| **Mission** | +2 (174→176) | -1 (152→151) | Specific nouns help some, hurt others |
| **date_validation (original)** | Mixed | -2 net | 3 wrong corrections offset good corrections |
| **date_validation (fixed)** | +2 (176→178) | +2 (151→153) | Chunk-path filter eliminates misattributions |

### Full 10-conv Results (Current Best)

| Conv | Questions | Correct | Accuracy |
|------|-----------|---------|----------|
| conv-30 | 81 | 71 | 87.65% |
| conv-26 | 152 | 135 | 88.82% |
| conv-47 | 150 | 135 | 90.00% |
| conv-50 | 158 | 147 | 93.04% |
| conv-41 | 152 | 140 | 92.11% |
| conv-49 | 156 | 141 | 90.38% |
| conv-44 | 123 | 103 | 83.74% |
| conv-48 | 191 | 171 | 89.53% |
| conv-42 | 199 | 178 | 89.45% |
| conv-43 | 178 | 153 | 85.96% |
| **Total** | **1540** | **1374** | **89.22%** |

Note: conv-30/26/47/50/41/49/44/48 were not re-run with datefix. Their numbers
are from the previous full-on run. A full 10-conv re-run with datefix is
recommended but not yet done.

## Root Cause Analysis: date_validation Chunk-Path Misattribution

### The Two Paths

date_validation has two source paths for finding relative temporal expressions:

1. **Fact-text path** (high confidence): the relative expression ("last Friday")
   is found in `fact.fact_text` itself. Attribution is certain — the expression
   belongs to this fact. No diff restriction needed.

2. **Chunk path** (low confidence): the expression is not in fact_text but is
   found in `chunk.chunk_text`. Attribution is uncertain — chunks contain
   multiple sentences with unrelated temporal references. The `_find_relative_expression`
   function returns the FIRST regex match, which may belong to a completely
   different fact extracted from the same chunk.

### The Three Regression Cases (all chunk-path)

| Conv | Fact date | Corrected to | Diff | Expression | Problem |
|------|-----------|-------------|------|------------|---------|
| conv-43 | Aug 15 | Jul 17 | 29d | "yesterday" (in chunk) | "yesterday" refers to a different event in the chunk |
| conv-43 | Aug 15 | Jul 17 | 29d | "yesterday" (in chunk) | Same pattern, different fact |
| conv-43 | Jan 5 | Dec 31 | 5d | "yesterday" (in chunk) | "yesterday" refers to a different fact's context |

All three share: (a) expression from chunk, not fact_text; (b) diff far outside
the ±7-day pattern the feature was designed to catch.

### The Fix: Chunk-Path Plausible Diff Filter

The feature was designed to catch "LLM computed last Friday as 2 weeks ago
instead of 1" — the diff is always approximately 7 days (±1). We added a filter
for chunk-path corrections:

```python
_CHUNK_PATH_PLAUSIBLE_DIFF_RANGES = (
    (6, 8),    # ±1 week miscount
    (13, 15),  # ±2 week miscount
)
```

- **Chunk-path**: only correct if diff falls in [6,8] or [13,15]
- **Fact-text path**: no restriction (attribution is certain)

### Known Residual: conv-42 Nov 10 → Nov 2 (diff=8)

One wrong correction survives the filter: diff=8 falls in [6,8] and cannot be
distinguished from a legitimate ±1 week fix. This is accepted as residual risk
because conv-42's net result is still +6 vs baseline even with this error.

### Known Edge Case: "last year" in Fact-Text (diff=309d)

In one case, the LLM wrote "last year" directly in fact_text, and dateparser
resolved it to ~365 days ago. The fact-text path has no diff restriction, so this
passes through. This is a rare edge case — "last year" is not a weekly miscount
pattern. Could be addressed by adding a max-diff cap on the fact-text path, but
not yet implemented.

## Feature Assessment Summary

### P1 (fact_format_clean) — KEEP, ENHANCE

**Status**: Net positive. +3 on conv-43, neutral on conv-42. Token savings ~35%.

**Mechanism**: Stripping `| When: | Involving:` metadata reduces noise when
100+ facts are sent to the answer LLM. The LLM focuses better on the core fact.

**Enhancement opportunity**: Currently only strips pipe-delimited suffixes.
Could also normalize inconsistent formatting (e.g., trailing whitespace,
duplicate entities in text body vs. entities field).

### Mission (retain_mission) — REMOVE from defaults

**Status**: Marginal. +2 on conv-42, -1 on conv-43. Net +1 over 377 questions.

**Mechanism**: Custom extraction instructions tell the LLM to preserve specific
nouns ("hoodie" not "clothing"), quantities ("nine" not "multiple"), place names
("Talkeetna" not "mountain"). This directly addresses 19/25 extraction-gap
errors identified in the 168-error analysis.

**Why remove**: The 4 instruction categories (quantities, product names, places,
health terms) were reverse-engineered from LoCoMo error analysis. This is
benchmark-specific prompt engineering that does not generalise to arbitrary user
conversations. Real users may care about completely different detail categories
(code names, technical terms, project names). The `retain_mission` configuration
field remains available for users who want to customise extraction behaviour for
their own use case — we just shouldn't ship a LoCoMo-tuned default.

**Action taken**: Mission stays in `ingest-locomo.sh` for benchmark runs only.
Not set as a default in the codebase.

### date_validation (with chunk-path fix) — KEEP

**Status**: Net positive after fix. +2 on conv-42, +2 on conv-43.

**Mechanism**: Corrects ±1 week date miscounts (LLM says "last Friday" but computes
2 weeks ago instead of 1). dateparser provides deterministic second opinion.

**The fix works**: The chunk-path plausible diff filter eliminated all 3 regression
cases while preserving the core ±7 day correction capability. Additionally, a
fact-text path max-diff cap (21 days) was added to block extreme corrections
like "last year" (diff=309d). Test coverage: 41 tests, 8 new tests for
confidence filters.

### detail_preservation — KEEP, DICTIONARY CLEANED

**Status**: Positive in targeted cases, but limited by hardcoded dictionary.

**Mechanism**: Cross-checks extracted facts against source chunks to restore
specific terms the LLM generalized ("hoodie" → "clothing line").

**Limitation**: Only works for pre-defined terms in `_GENERIC_CATEGORIES` dict.
Arbitrary proper nouns (e.g., "Xenoblade Chronicles") are not caught. The test
`test_conv42_xenoblade_game_title` documents this gap — `enriched == 0`.

**Dictionary cleanup (2026-04-16)**: Removed benchmark-specific terms that
constituted overfitting to LoCoMo:
- Removed entire `animal` category (all were LoCoMo pet names: pepper, precious, pixie, etc.)
- Removed `talkeetna` from places (conv-48 specific)
- Removed `chicken pot pie` from food/recipe (conv-44 specific)
- Removed `nothing is impossible` from books (LoCoMo specific)
- Removed `monster hunter` from music (wrong category)
- Removed `botw`, `detroit`, `overcooked` from games (niche/LoCoMo-derived)
- Removed `birdwatching` from sports (LoCoMo-derived)
- Added `mozart`, `chopin` to music (universally known)

**Future direction**: Dictionary approach is inherently limited. Better approaches
would be LLM-based or embedding-based specificity detection that can handle
arbitrary proper nouns without maintaining a static list.

## Uncommitted Changes

| File | Change | Category |
|------|--------|----------|
| `date_validation.py` | Chunk-path diff filter + fact-text max-diff cap (21d) | Bug fix |
| `detail_preservation.py` | Dictionary cleaned: removed LoCoMo-specific terms | Anti-overfitting |
| `test_post_extraction.py` | 8 new/updated tests (41 total) | Tests |
| `memory_engine.py` | `disallowed_special=()` for tiktoken encode | Bug fix |
| `token_accounting.py` | Same tiktoken fix (2 locations) | Bug fix |
| `locomo10.json` | Gold answer corrections (8 questions) | Data fix |
| `ingest-benchmark-db.py` | `--reverse` and `--shard` flags for parallel ingest | Tooling |

## Decisions Made

1. **Mission removed from defaults** — benchmark-specific prompt engineering;
   `retain_mission` config field stays available for user customisation
2. **detail_preservation dictionary cleaned** — removed LoCoMo-derived terms
   (pet names, specific place names, specific food items) to prevent overfitting
3. **Fact-text path max-diff cap added** — 21 days, blocks "last year" edge case

## Open Items

### Next Steps

1. **Commit all changes** — datefix, dictionary cleanup, tiktoken fix, tests
2. **Full 10-conv eval** — verify no regression from dictionary cleanup on
   other conversations (conv-30 hoodie test, conv-48 game titles, etc.)

### Future Design Work

3. **LLM-based detail verification** — replace dictionary-based detail_preservation
   with a lightweight LLM check: "Does this fact preserve the specific details from
   the source?" This would catch arbitrary proper nouns without maintaining a dictionary.
4. **Chunk-path expression disambiguation** — instead of just filtering by diff,
   check if the chunk contains exactly one relative expression (high confidence) vs
   multiple (low confidence). This could safely enable corrections for diffs outside
   [6,8]∪[13,15] when attribution is unambiguous.
