#!/usr/bin/env python3
"""Recall Replay: fast token efficiency evaluation without LLM calls.

Reads benchmark results JSON (which already contains retrieved_memories per question),
applies different output tier strategies, and reports token efficiency + coverage.

This enables sub-minute iteration on output tier logic:
  1. Run full benchmark ONCE (hours) → produces results JSON with recall data
  2. Develop new tier logic → run this script (seconds) → see impact

Usage:
    # Show baseline stats
    python recall_replay.py --results benchmark_results.json

    # Simulate Tier-A (top-3, L1-length budget)
    python recall_replay.py --results benchmark_results.json --max-results 3 --max-tokens 500

    # Simulate Tier-B (top-5, reduced budget)
    python recall_replay.py --results benchmark_results.json --max-results 5 --max-tokens 1500

    # Compare all tiers side by side
    python recall_replay.py --results benchmark_results.json --compare
"""

import argparse
import json
import sys
from pathlib import Path

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc.encode(text))


def load_questions(results_path: Path) -> list[dict]:
    """Extract all valid questions with their recall results and judge verdicts."""
    data = json.load(open(results_path))
    questions = []
    for item in data.get("item_results", []):
        for dr in item.get("metrics", {}).get("detailed_results", []):
            if dr.get("is_invalid"):
                continue
            mems = dr.get("retrieved_memories", [])
            if not mems:
                continue
            questions.append({
                "question": dr["question"],
                "correct_answer": dr["correct_answer"],
                "is_correct": dr.get("is_correct", False),
                "category": dr.get("category", "unknown"),
                "memories": mems,
            })
    return questions


def apply_tier(memories: list[dict], max_results: int | None, max_tokens: int | None) -> list[dict]:
    """Simulate output tier: limit by result count and/or token budget."""
    selected = []
    total_tokens = 0
    for mem in memories:
        if max_results is not None and len(selected) >= max_results:
            break
        tok = count_tokens(mem.get("text", ""))
        if max_tokens is not None and total_tokens + tok > max_tokens:
            break
        selected.append(mem)
        total_tokens += tok
    return selected


def check_coverage(original_mems: list[dict], filtered_mems: list[dict], correct_answer: str) -> bool:
    """Check if the filtered memories still contain the information needed for the correct answer.

    Heuristic: find which original memories contain keywords from the correct answer,
    then check if at least one of those memories survived filtering.
    """
    correct_answer = str(correct_answer) if correct_answer else ""
    if not correct_answer:
        return True

    # Extract significant keywords from correct answer (>= 4 chars, not common words)
    stop_words = {"that", "this", "with", "from", "have", "been", "were", "they", "their", "about", "would", "could", "should"}
    keywords = [
        w.lower().strip(".,!?\"'()[]")
        for w in correct_answer.split()
        if len(w) >= 4 and w.lower() not in stop_words
    ]
    if not keywords:
        return True

    # Find which original memories are "evidence" (contain answer keywords)
    def mem_has_evidence(mem: dict) -> bool:
        text = mem.get("text", "").lower()
        return any(kw in text for kw in keywords)

    evidence_ids = {mem.get("id") for mem in original_mems if mem_has_evidence(mem)}
    if not evidence_ids:
        # No original memory matched keywords — coverage check is inconclusive
        return True

    # Check if at least one evidence memory survived filtering
    filtered_ids = {mem.get("id") for mem in filtered_mems}
    return bool(evidence_ids & filtered_ids)


def evaluate_tier(questions: list[dict], max_results: int | None, max_tokens: int | None) -> dict:
    """Evaluate a tier configuration across all questions."""
    all_tokens = []
    all_counts = []
    coverage_hits = 0
    coverage_total = 0
    accuracy_preserved = 0
    accuracy_total = 0

    for q in questions:
        original = q["memories"]
        filtered = apply_tier(original, max_results, max_tokens)

        # Token stats
        tok = sum(count_tokens(m.get("text", "")) for m in filtered)
        all_tokens.append(tok)
        all_counts.append(len(filtered))

        # Coverage: does filtered set still contain evidence for correct answer?
        covered = check_coverage(original, filtered, q["correct_answer"])
        coverage_total += 1
        if covered:
            coverage_hits += 1

        # Accuracy preservation: if originally correct AND covered, likely still correct
        if q["is_correct"]:
            accuracy_total += 1
            if covered:
                accuracy_preserved += 1

    sorted_tokens = sorted(all_tokens)
    n = len(sorted_tokens)

    return {
        "num_questions": n,
        "max_results": max_results or "unlimited",
        "max_tokens": max_tokens or "unlimited",
        "avg_tokens": round(sum(all_tokens) / n, 1) if n else 0,
        "median_tokens": sorted_tokens[n // 2] if n else 0,
        "p95_tokens": sorted_tokens[int(n * 0.95)] if n else 0,
        "avg_memories": round(sum(all_counts) / n, 1) if n else 0,
        "coverage": round(coverage_hits / coverage_total * 100, 1) if coverage_total else 0,
        "accuracy_preserved": round(accuracy_preserved / accuracy_total * 100, 1) if accuracy_total else 0,
        "accuracy_preserved_count": f"{accuracy_preserved}/{accuracy_total}",
    }


def print_tier(name: str, stats: dict):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  Questions:          {stats['num_questions']}")
    print(f"  Max results:        {stats['max_results']}")
    print(f"  Max tokens:         {stats['max_tokens']}")
    print(f"  Avg tokens/query:   {stats['avg_tokens']}")
    print(f"  Median tokens:      {stats['median_tokens']}")
    print(f"  P95 tokens:         {stats['p95_tokens']}")
    print(f"  Avg memories/query: {stats['avg_memories']}")
    print(f"  Evidence coverage:  {stats['coverage']}%")
    print(f"  Accuracy preserved: {stats['accuracy_preserved']}% ({stats['accuracy_preserved_count']})")


def main():
    parser = argparse.ArgumentParser(description="Recall Replay: fast token efficiency evaluation")
    parser.add_argument("--results", required=True, help="Path to benchmark results JSON")
    parser.add_argument("--max-results", type=int, default=None, help="Limit number of results returned")
    parser.add_argument("--max-tokens", type=int, default=None, help="Limit total context tokens")
    parser.add_argument("--compare", action="store_true", help="Compare Tier-A/B/C side by side")
    args = parser.parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        print(f"ERROR: {results_path} not found", file=sys.stderr)
        return 1

    questions = load_questions(results_path)
    if not questions:
        print("ERROR: No valid questions found in results", file=sys.stderr)
        return 1

    correct = sum(1 for q in questions if q["is_correct"])
    print(f"Loaded {len(questions)} questions ({correct} correct, {len(questions)-correct} wrong)")

    if args.compare:
        tiers = [
            ("Tier-C (baseline: no limit)", None, None),
            ("Tier-C (4096 budget)", None, 4096),
            ("Tier-B (top-5, 1500 tok)", 5, 1500),
            ("Tier-B (top-5, 2000 tok)", 5, 2000),
            ("Tier-A (top-3, 500 tok)", 3, 500),
            ("Tier-A (top-3, 900 tok)", 3, 900),
        ]
        for name, mr, mt in tiers:
            stats = evaluate_tier(questions, mr, mt)
            print_tier(name, stats)

        # Summary comparison table
        print(f"\n{'='*60}")
        print(f"  COMPARISON SUMMARY")
        print(f"{'='*60}")
        print(f"  {'Tier':<30} {'Avg Tok':>8} {'Coverage':>9} {'Acc Kept':>9}")
        print(f"  {'-'*56}")
        for name, mr, mt in tiers:
            s = evaluate_tier(questions, mr, mt)
            print(f"  {name:<30} {s['avg_tokens']:>8} {s['coverage']:>8.1f}% {s['accuracy_preserved']:>8.1f}%")
    else:
        stats = evaluate_tier(questions, args.max_results, args.max_tokens)
        print_tier("Custom Tier" if (args.max_results or args.max_tokens) else "Baseline (no limit)", stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())
