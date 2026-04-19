"""Render a summary of a flag-matrix benchmark comparison.

Reads the per-cell ``<cell>.json`` files produced by ``run-comparison.sh``
and writes a ``SUMMARY.md`` alongside them with accuracy, question counts,
and (where available) latency deltas.

Invoked by ``run-comparison.sh``. Can also be run directly against an
existing comparison directory to re-render the summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


CELL_ORDER = ["baseline", "enrichment", "cache", "all_on"]


def _load_cell(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _overall_accuracy(data: dict) -> tuple[int, int]:
    correct = 0
    total = 0
    for item in data.get("item_results", []):
        metrics = item.get("metrics", {})
        for detail in metrics.get("detailed_results", []):
            if detail.get("is_invalid"):
                continue
            total += 1
            if detail.get("is_correct"):
                correct += 1
    return correct, total


def _latency_stats(data: dict) -> dict[str, float]:
    latencies: list[float] = []
    for item in data.get("item_results", []):
        for detail in item.get("metrics", {}).get("detailed_results", []):
            latency = detail.get("latency_s") or detail.get("duration_s")
            if isinstance(latency, (int, float)) and latency > 0:
                latencies.append(float(latency))
    if not latencies:
        return {}
    latencies.sort()
    n = len(latencies)

    def _pct(p: float) -> float:
        idx = min(n - 1, int(round(p * (n - 1))))
        return round(latencies[idx], 3)

    return {
        "p50_s": _pct(0.50),
        "p95_s": _pct(0.95),
        "p99_s": _pct(0.99),
        "samples": n,
    }


def render(summary_dir: Path) -> None:
    rows: list[dict] = []
    for cell in CELL_ORDER:
        f = summary_dir / f"{cell}.json"
        if not f.exists():
            continue
        data = _load_cell(f)
        correct, total = _overall_accuracy(data)
        row = {
            "cell": cell,
            "correct": correct,
            "total": total,
            "accuracy": round(100.0 * correct / total, 2) if total else 0.0,
        }
        row.update(_latency_stats(data))
        rows.append(row)

    if not rows:
        print(f"No cell JSON files found under {summary_dir}", file=sys.stderr)
        sys.exit(1)

    baseline = next((r for r in rows if r["cell"] == "baseline"), None)

    lines: list[str] = []
    lines.append(f"# Benchmark comparison — `{summary_dir.name}`\n")
    lines.append(
        "| Cell | Accuracy | Δ vs baseline | Correct / Total | p50 latency | p95 latency | p99 latency |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")

    for row in rows:
        delta = ""
        if baseline and row["cell"] != "baseline":
            d = row["accuracy"] - baseline["accuracy"]
            delta = f"{d:+.2f}pp"
        p50 = f"{row['p50_s']}s" if "p50_s" in row else "—"
        p95 = f"{row['p95_s']}s" if "p95_s" in row else "—"
        p99 = f"{row['p99_s']}s" if "p99_s" in row else "—"
        lines.append(
            f"| {row['cell']} | {row['accuracy']}% | {delta} | {row['correct']}/{row['total']} | {p50} | {p95} | {p99} |"
        )

    lines.append("")
    lines.append("## Cells")
    lines.append("- **baseline** — all MemSense flags off (upstream default).")
    lines.append(
        "- **enrichment** — `RETAIN_POST_EXTRACTION_ENABLED=true`, `RETAIN_FACT_FORMAT_CLEAN_ENABLED=true`."
    )
    lines.append("- **cache** — `RECALL_CACHE_ENABLED=true`.")
    lines.append("- **all_on** — every MemSense flag on.")
    lines.append("")
    lines.append("Raw per-cell results live in this directory as `<cell>.json`.")

    out = summary_dir / "SUMMARY.md"
    out.write_text("\n".join(lines))
    print(f"Wrote {out}")
    print("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: _comparison_summary.py <comparison_dir>", file=sys.stderr)
        sys.exit(2)
    render(Path(sys.argv[1]))
