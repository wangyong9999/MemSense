# LoCoMo 89.1% Baseline — 168 Wrong Answers Systematic Analysis

Date: 2026-04-12
Baseline: `locomo_minimax_m27_eval_baseline.json` (MiniMax M2.7, 1372/1540 correct)

## Methodology

For each of 168 wrong answers:
1. Extract keywords (≥3 chars, stopwords excluded) from the gold answer
2. Search ALL retrieved memories (not just top-10) for keyword presence
3. Classify the evidence position: top-10 / outside-top-10 / not found
4. Classify LLM behavior: gave wrong answer / said "no information"
5. Cross-reference with LoCoMo question category (1-4)

## Three Groups of Failure

### GROUP A: Evidence in top-10, LLM still wrong (116 cases, 69%)

The retrieval pipeline found the right information and ranked it high enough.
The failure is in answer generation or judging.

| Sub-mode | Count | Description |
|----------|-------|-------------|
| A1: LLM said "no info" | 37 | Evidence at rank 1-10, but LLM claims nothing relevant exists |
| A2: LLM gave wrong answer | 78 | Evidence present, LLM picked a different fact or paraphrased incorrectly |
| A3: Other | 1 | Edge case |

**A1 examples** (evidence at rank 1, LLM said "no info"):
- Q: "What projects is Jolene planning?" → Evidence #1 mentions "renewable energy" → LLM: "no explicit information"
- Q: "When did Jolene do yoga at Talkeetna?" → Evidence #1 mentions the date → LLM: "no information about Talkeetna"
- Pattern: LLM scans 100+ facts and fails to connect the query to the relevant evidence

**A2 examples** (evidence present, LLM picked wrong):
- Q: "What did Gina find on Feb 1?" → Evidence #1 has "perfect spot" → LLM: "received a reply from wholesaler" (different event on same date)
- Q: "What won't Jon do?" → Evidence #5 has "quit" → LLM: "won't let anything hold him back" (paraphrase, not precise enough)
- Cat 2 temporal: 34/47 wrong temporal answers are A2 — evidence has the right event but LLM extracts the wrong date

### GROUP B: Evidence outside top-10 (24 cases, 14%)

The correct information exists in the memory bank but the retrieval pipeline
ranked it too low (rank 11-51). Improving retrieval ranking would help.

| Sub-mode | Count | Description |
|----------|-------|-------------|
| B1: LLM said "no info" | 6 | Evidence at rank 11-20, LLM only looked at top results |
| B2: LLM gave wrong answer | 16 | Evidence at rank 11-51, LLM answered from top-ranked (wrong) facts |
| B3: Other | 2 | Numeric answers where LLM got close but not exact |

**B1 examples**:
- Q: "How old is Jolene?" → Evidence at rank 20 → LLM only checked top facts
- Q: "What game for calming?" → "Animal Crossing" at rank 11 → just outside top-10 cutoff

**B2 examples**:
- Q: "What does ideal dance studio look like?" → Evidence at rank 13 → LLM used top-ranked facts about different topic
- Q: "What games for Deborah?" → Zelda at rank 16 → LLM gave partial answer from top results

### GROUP C: No keyword evidence in any memory (28 cases, 17%)

The gold answer's key terms don't appear in any retrieved memory.
Either fact extraction didn't capture the detail, or the benchmark
answer requires world knowledge / inference.

| Sub-mode | Count | Description |
|----------|-------|-------------|
| C0: Answer too short | 3 | Gold answer is a number ("3", "6") — can't keyword-match |
| C1: LLM correctly said "no info" | 7 | Fact extraction genuinely missed this information |
| C2: LLM fabricated | 17 | No evidence but LLM gave a (wrong) answer anyway |
| C3: Other | 1 | Edge case |

**C1 examples** (genuine extraction gaps):
- "four months" (robotics project duration) — not in any fact
- "Obesity" (John's health) — not extracted from conversation  
- "seeking solitude" (John's mood) — not extracted

**C2 examples** (fabrication from partial context):
- "Hoodies" → Fact says "limited edition clothing line" (generalized during extraction)
- "six months" → LLM said "5 months" (close but wrong, no exact source)
- "Alaska" �� Conversation mentions "Talkeetna" but extraction didn't capture it; gold answer requires knowing Talkeetna is in Alaska

## By LoCoMo Category

| Category | Total | Correct | Wrong | Accuracy | Dominant failure mode |
|----------|-------|---------|-------|----------|----------------------|
| 1: Single-hop | 282 | 258 | 24 | 91.5% | C2 fabrication (5) + A2 wrong answer (8) |
| 2: Temporal | 321 | 274 | 47 | 85.4% | **A2 wrong date (34)** — largest single cluster |
| 3: Multi-hop | 96 | 63 | 33 | 65.6% | A1 ignored evidence (11) + A2 wrong answer (10) |
| 4: Descriptive | 841 | 777 | 64 | 92.4% | A2 wrong answer (26) + A1 ignored evidence (19) |

### Category 2 (Temporal) deep-dive

47 wrong answers, 34 are A2 (evidence in top-10 but wrong date extracted).

Typical pattern: LLM has the right fact in context but extracts a nearby date
instead of the correct one. Examples:
- Gold: "July 21" → LLM: "July 14" (1 week off)
- Gold: "October 21-22" → LLM: "October 14-15" (1 week off)
- Gold: "June 20" → LLM: "June 21" (1 day off)

Root cause: The fact text often contains the date in a narrative format
("last Friday", resolved to a date during extraction). If the extraction
resolved the relative date incorrectly by ±1 week, the LLM faithfully
reports the wrong date from the fact.

This could be a fact extraction issue (wrong date resolution) OR an LLM
answer generation issue (picking the wrong date from multiple candidates).
Need to check the actual fact text to distinguish.

### Category 3 (Multi-hop) deep-dive

33 wrong answers, 11 are A1 (evidence present but LLM said "no info").

These are inference questions where the answer isn't stated directly:
- "How old is Jolene?" → Need to infer from "she's in school" → "likely ≤30"
- "Was James lonely before meeting Samantha?" → Need to infer from "only creature that greeted him was his cat"
- "Why did Jolene put off yoga?" → Need to infer from "she plays video games instead"

MiniMax M2.7 tends to say "no explicit information" rather than make inferences.
This is a model capability issue — conservative reasoning rather than wrong reasoning.

## Summary Statistics

```
168 wrong answers:
├── GROUP A: Evidence in top-10 (116, 69%) — answer generation problem
│   ├── A1: Said "no info" (37)  — LLM too conservative
│   └── A2: Wrong answer (78)    — LLM picked wrong fact/date
│
├── GROUP B: Evidence outside top-10 (24, 14%) — retrieval ranking problem
│   ├── B1: Said "no info" (6)
│   └── B2: Wrong answer (16)
│
└── GROUP C: No evidence at all (28, 17%) — fact extraction gap
    ├── C1: Correctly said "no info" (7)
    └── C2: Fabricated answer (17)
```

## Improvement Ceiling by Root Cause

| Root cause | Cases | Ceiling | Fix mechanism |
|------------|-------|---------|---------------|
| Answer generation (A1+A2) | 116 | +7.5pp (89→96.5%) | Better answer prompt, stronger LLM |
| Retrieval ranking (B) | 24 | +1.6pp | Better ranking or higher max_tokens |
| Fact extraction (C) | 28 | +1.8pp | Better extraction prompt, verbose mode |
| **Combined ceiling** | **168** | **+10.9pp (→100%)** | **All of the above** |

The single largest actionable cluster is **Cat 2 temporal A2 (34 cases)** —
dates extracted or interpreted wrong. Fixing date handling alone could yield
+2.2pp improvement.
