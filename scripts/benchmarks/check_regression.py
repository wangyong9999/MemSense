#!/usr/bin/env python3
"""Check benchmark results for precision regression.

Usage:
    python check_regression.py --results results.json --baseline-accuracy 0.89 --max-regression 0.02

Exit codes:
    0 - No regression (or within tolerance)
    1 - Regression exceeds threshold
    2 - Invalid input / missing file
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check benchmark precision regression")
    parser.add_argument("--results", required=True, help="Path to benchmark results JSON")
    parser.add_argument(
        "--baseline-accuracy",
        type=float,
        required=True,
        help="Expected baseline accuracy (0-100 scale, e.g. 89.0)",
    )
    parser.add_argument(
        "--max-regression",
        type=float,
        default=2.0,
        help="Max allowed regression in percentage points (default: 2.0)",
    )
    args = parser.parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        return 2

    try:
        with open(results_path) as f:
            results = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: Failed to read results: {e}", file=sys.stderr)
        return 2

    actual_accuracy = results.get("overall_accuracy")
    if actual_accuracy is None:
        print("ERROR: 'overall_accuracy' not found in results", file=sys.stderr)
        return 2

    total_valid = results.get("total_valid", results.get("total_questions", "?"))
    baseline = args.baseline_accuracy
    max_reg = args.max_regression
    delta = actual_accuracy - baseline

    print(f"Baseline accuracy:  {baseline:.1f}%")
    print(f"Actual accuracy:    {actual_accuracy:.1f}% ({total_valid} valid questions)")
    print(f"Delta:              {delta:+.1f}pp")
    print(f"Max regression:     {max_reg:.1f}pp")

    # Also print token stats if available
    if "token_stats" in results:
        ts = results["token_stats"]
        print(f"\nToken stats:")
        print(f"  Avg context tokens:    {ts.get('avg_context_tokens', 'N/A')}")
        print(f"  Median context tokens: {ts.get('median_context_tokens', 'N/A')}")
        print(f"  P95 context tokens:    {ts.get('p95_context_tokens', 'N/A')}")

    if delta < -max_reg:
        print(f"\nFAIL: Regression of {abs(delta):.1f}pp exceeds threshold of {max_reg:.1f}pp")
        return 1

    if delta < 0:
        print(f"\nWARN: Minor regression of {abs(delta):.1f}pp (within tolerance)")
    else:
        print(f"\nOK: No regression detected ({delta:+.1f}pp)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
