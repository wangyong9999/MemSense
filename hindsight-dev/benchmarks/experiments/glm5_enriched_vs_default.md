# Experiment: GLM-5 Enriched vs Default LoCoMo

Date: 2026-04-17
Status: **Net-neutral after correcting for Dashscope noise; critical bug found in `detail_preservation`**

## TL;DR

| Metric | Default | Enriched | Δ raw | Δ corrected* |
|---|---|---|---|---|
| Overall | 84.29% (1298/1540) | **85.19% (1312/1540)** | +0.90pp | **+0.12pp** |
| Cat1 Multi-hop | 85.46% | 84.04% | **-1.42pp** | — |
| Cat2 Single-hop | 81.93% | 82.55% | +0.62pp | — |
| Cat3 Temporal | 64.58% | 65.62% | +1.04pp | — |
| Cat4 Open-domain | 87.04% | 88.82% | +1.78pp | — |

\*Corrected = exclude Dashscope content-moderation errors from both denominators (default 62, enriched 48).

**Verdict**: the headline +0.90pp is almost entirely Dashscope randomness.
Category breakdown shows Multi-hop actually **regressed -1.42pp** — a real
concern. And a **critical substring-match bug** in `detail_preservation` is
polluting 14% of all facts with the junk suffix `(specifically: Hat)`.

## Setup

| Component | Setting |
|---|---|
| Bank (default) | `bench-locomo-glm` (2172 facts, ingested 2026-04-14, no enrichment) |
| Bank (enriched) | `bench-locomo-glm-enriched` (2199 facts, re-ingested 2026-04-16) |
| Enrichment flags ON | `RETAIN_POST_EXTRACTION_ENABLED=true`, `RETAIN_FACT_FORMAT_CLEAN_ENABLED=true` |
| Ingest stats | 55 date corrections, 404 detail enrichments, 2198 format cleanings |
| LLM (ingest / answer / judge) | GLM-5 via Anthropic-compat (113.46.219.251:8080) |
| Embeddings / Reranker | local BAAI bge-small / cross-encoder MiniLM |
| Eval | full, all 10 convs, 1540 questions, `--skip-ingestion` |

Enriched results saved to `benchmark_results_glm5_enriched.json`; default at
`benchmark_results_glm5_baseline.json`.

## Per-Conversation Delta

| Conv | Default | Enriched | Δ | Note |
|---|---|---|---|---|
| conv-26 | 86.84% (132/152) | **90.79% (138/152)** | **+3.95pp** | Real win |
| conv-42 | 59.30% (118/199) | 63.82% (127/199) | +4.52pp | **Dashscope noise** (see below) |
| conv-48 | 88.48% (169/191) | 90.05% (172/191) | +1.57pp | Real win |
| conv-49 | 86.54% (135/156) | 87.82% (137/156) | +1.28pp | Small win |
| conv-43 | 83.71% (149/178) | 84.83% (151/178) | +1.12pp | Small win |
| conv-41 | 90.79% (138/152) | 90.79% (138/152) | 0.00pp | Flat |
| conv-50 | 88.61% (140/158) | 88.61% (140/158) | 0.00pp | Flat |
| conv-47 | 90.67% (136/150) | 89.33% (134/150) | -1.33pp | Small loss |
| conv-44 | 87.80% (108/123) | 86.18% (106/123) | -1.63pp | Small loss |
| conv-30 | 90.12% (73/81) | **85.19% (69/81)** | **-4.94pp** | **Real regression** |

## Question-level Churn (1540 common questions)

- Both correct: 1219
- Both wrong: 149
- Newly WRONG (regression): **79**
- Newly RIGHT (improvement): **93**
- Net: +14

Regression distribution:
- By category: Cat4=37, Cat1=20, Cat2=17, Cat3=5
- By conv: conv-42=28, conv-50=10, conv-44=7, conv-49=6, conv-47=6, ...

Improvement distribution:
- By category: Cat4=52, Cat2=19, Cat1=16, Cat3=6
- By conv: conv-42=37, conv-26=11, conv-50=10, conv-49=8, conv-48=7, ...

The ~80-question churn on both sides is much larger than the net +14 — evidence
that a lot of the deltas are noise (Dashscope filter + LLM judge stochasticity
+ reranking ties) rather than signal.

## Root Cause 1 — Dashscope Content-Moderation Noise

| Bank | Dashscope-blocked answers | In conv-42 | In conv-43 |
|---|---|---|---|
| Default | 62 | 61 | 1 |
| Enriched | 48 | 48 | 0 |

14 fewer blocks in the enriched run. These questions look like they "improved"
because the default run got a hard `Error 400` for the predicted answer (counted
wrong) and the enriched run happened to bypass the filter.

Conv-42 corrected accuracy (excluding Dashscope errors):
- Default: 118/(199-61) = **85.51%**
- Enriched: 127/(199-48) = **84.11%**
- Corrected Δ = **-1.40pp** (enriched actually WORSE on conv-42 once the filter noise is removed)

The conv-42 headline +4.52pp is entirely noise from fewer filter hits.

## Root Cause 2 — `detail_preservation` Substring-Match BUG

Sampling the enriched DB directly:

| Stat | Count |
|---|---|
| Total facts | 2199 |
| Facts with `(specifically: …)` suffix | 404 (18.4%) |
| …of which contain `Hat` | **317 (78% of all enrichments)** |
| …contain `Tart` | 39 |
| …contain `Tea` | 4 |
| Genuinely useful additions (Hiking, Yoga, Basketball, Harry Potter, Pizza, Zelda, Salad) | ~30 |

Sample garbage enrichments from the bank:

```
Caroline attended an LGBTQ support group on May 7, 2023 … (specifically: Hat)
Melanie has pets: Oliver (dog), Luna, and Bailey (a new cat). (specifically: Hat)
Drawing flowers is one of Caroline's favorite art activities. (specifically: Hat)
The song "Brave" by Sara Bareilles has deep significance for Caroline … (specifically: Hat)
Melanie loves live music. (specifically: Hat)
```

None of these facts are about hats.

### The bug

`hindsight-api-slim/hindsight_api/engine/retain/post_extraction/detail_preservation.py` around line 143:

```python
def _find_specific_terms_in_text(text: str) -> list[tuple[str, str]]:
    text_lower = text.lower()
    found = []
    for term, category in sorted(_SPECIFIC_TERMS.items(), key=lambda x: len(x[0]), reverse=True):
        if term in text_lower:   # ← SUBSTRING match, not word boundary
            found.append((term, category))
    return found
```

Dictionary contains short terms like `"hat"`, `"tart"`, `"tea"`:

- `"hat"` matches as a substring inside `that`, `what`, `chat`, `somewhat`,
  `whatsoever`, `hatred`, `hate`, `shattered`, `Manhattan`, `chatting`, …
- `"tart"` matches `start`, `started`, `starting`, `restart`, `heartbeat`…
- `"tea"` matches `steak`, `team`, `teach`, `teacher`, `steady`, `instead`…

Combined with a permissive fallback (`_terms_share_sentence`), almost every
fact whose chunk contains any English text ends up tagged with `(specifically: Hat)`.

### Downstream damage

1. **Token waste**: `(specifically: Hat)` is pure noise occupying context tokens.
2. **Wrong semantic signal**: the phrase "specifically" primes the LLM to treat
   the token as important.
3. **Entity pollution**: line 267 adds the bogus term to `fact.entities`,
   corrupting BM25 signal as well.

## Root Cause 3 — Cat1 Multi-hop Regressed -1.42pp

Cat4 (open-domain) gained most of the headline lift (+1.78pp, 52 newly right
vs 37 newly wrong). Cat1 (multi-hop) went the other way: -1.42pp, 16 newly
right vs 20 newly wrong.

Looking at the regression samples, multi-hop questions often need the
`| When:` / `| Involving:` metadata that P1 `fact_format_clean` strips. A
multi-hop question like "which games have Jolene and her partner played
together" is answered better when each fact carries its pipe-delimited date
and actor context, because the LLM can chain facts across sessions. After P1
strips this, the LLM has to reconstruct the sequence from less structured text.

P1 was designed for token efficiency on open-domain questions. The -1.42pp
on Cat1 shows it has a real cost on reasoning-intensive categories.

## Root Cause 4 — conv-30 Regression (-4.94pp)

conv-30 has 5 newly-wrong questions. Samples:

- q7 "When did Gina launch an ad campaign?"
  Default: "around January 29, 2023" ✓
  Enriched: "January 2023, shortly before January 29, 2023" ✗ (judge rejected)
  → Judge strictness; both answers materially correct.

- q43 "What do the dancers in the photo represent?"
  Default gave a multi-photo breakdown ✓
  Enriched gave the same breakdown but started with the wrong photo ✗
  → Retrieval order differs slightly; fact ranking perturbed by `(specifically: Hat)`
    showing up in adjacent entries.

- q75 "What does Gina say to Jon about the grand opening?"
  Both answers paraphrase the same source; one is accepted, the other isn't.
  → Judge noise.

No systematic cause; mix of judge strictness + minor retrieval shuffling from
the polluted entity field.

## What Really Improved vs What Was Noise

**Genuine improvements (real signal):**

- **conv-26 +3.95pp**: detail_preservation's GOOD enrichments (e.g., specific
  game titles restored) helped answer "which games did X play" style questions.
- **conv-48 +1.57pp**: Same pattern — open-domain questions benefited from the
  few useful enrichments (Yoga, Hiking, Basketball).
- **Cat4 +1.78pp**: Open-domain is the category most aligned with
  detail_preservation's intent.
- **55 date corrections**: didn't move Cat3 Temporal much (+1.04pp) —
  most LoCoMo temporal questions aren't the kind that date_validation fixes.

**Noise:**
- **conv-42 +4.52pp**: entirely Dashscope randomness. Real Δ is **-1.40pp**.
- Judge stochasticity on near-miss answers (paraphrase scoring).
- Minor reranker reshuffles induced by polluted entity fields.

## Decisions

### Must fix before any redo

1. **Fix the substring-match bug in `_find_specific_terms_in_text`** — switch
   to word-boundary regex: `rf"\b{re.escape(term)}\b"`.
2. **Drop too-generic short tokens** that are legitimate substrings of common
   words even with word boundaries (e.g., remove `"hat"`, `"tea"`, `"tart"`
   from the dictionary — their information value is near zero and risk of
   false match is high).
3. **Add a test** for detail_preservation that feeds chunks containing "that",
   "steak", "start" and asserts no `(specifically: …)` is added.

### Re-evaluate after fix

The 404 detail_preservation enrichments shrink to roughly 30 after fixing the
bug. Most of the +0.12pp corrected improvement came from those 30 legit
enrichments. After the fix the expected real lift is small but positive on
Cat4; the Cat1 regression from P1 remains.

### Longer-term considerations

- **P1 trade-off**: token savings are real (~35%) but cost Cat1 -1.42pp. Could
  we keep `| When:` but drop `| Involving:`? The date metadata is what
  multi-hop reasoning actually needs.
- **conv-30 regression**: needs a second look after the detail_preservation
  fix to see whether the small regression persists or was fully bug-driven.
- **conv-42 Dashscope**: known infrastructure issue — not a Hindsight defect.
  Document as a measurement caveat; consider using a non-Dashscope judge model
  to re-score conv-42 answers.

## Artefacts

- `benchmark_results_glm5_baseline.json` — default run (Apr 16)
- `benchmark_results_glm5_enriched.json` — enriched run (Apr 17)
- `benchmark_results.json` — latest (currently enriched)
- `/tmp/analyze_enriched_diff.py` — diff script
- `/tmp/glm_enriched_regressions.json` — top 20 regression samples
- `/tmp/glm_enriched_improvements.json` — top 20 improvement samples
