#!/usr/bin/env python3
"""Diagnose partial LongMemEval banks after an interrupted ingestion.

Each bank should have one document per haystack session. A bank with fewer
documents than expected was interrupted mid-ingestion and will be wrongly
skipped by `ingest-benchmark-db.py` (its skip-if-exists check only looks for
count > 0). This script lists such partial banks and can delete them so the
resume pass re-ingests them cleanly.

Usage:
  # Dry-run (default) - lists status only
  HINDSIGHT_DOTENV_PATH=/path/to/.env HINDSIGHT_API_DATABASE_URL="pg0://<name>:<port>" \
    uv run python scripts/benchmarks/diagnose-partial-banks.py

  # Delete partial banks so resume picks them up
  ... --fix
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hindsight-dev"))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")


async def run(fix: bool) -> None:
    from benchmarks.common.benchmark_runner import create_memory_engine
    from benchmarks.longmemeval.longmemeval_benchmark import LongMemEvalDataset
    from hindsight_api.models import RequestContext

    dataset = LongMemEvalDataset()
    dataset_path = Path(__file__).parent.parent.parent / "hindsight-dev" / "benchmarks" / "longmemeval" / "datasets" / "longmemeval_s_cleaned.json"
    items = dataset.load(dataset_path, None)
    expected = {
        f"longmemeval_{dataset.get_item_id(item)}": len(item.get("haystack_sessions", []))
        for item in items
    }

    memory = await create_memory_engine()
    try:
        pool = await memory._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.bank_id,
                       COALESCE(f.fact_count, 0) AS fact_count,
                       COALESCE(d.doc_count, 0) AS doc_count
                FROM banks b
                LEFT JOIN (
                    SELECT bank_id, COUNT(*) AS fact_count FROM memory_units GROUP BY bank_id
                ) f ON f.bank_id = b.bank_id
                LEFT JOIN (
                    SELECT bank_id, COUNT(*) AS doc_count FROM documents GROUP BY bank_id
                ) d ON d.bank_id = b.bank_id
                WHERE b.bank_id LIKE 'longmemeval_%'
                """
            )

        status: dict[str, list[tuple[str, int, int, int]]] = {
            "COMPLETE": [],
            "PARTIAL": [],
            "EMPTY": [],
            "UNKNOWN": [],
        }
        seen = set()
        for r in rows:
            bid = r["bank_id"]
            seen.add(bid)
            exp = expected.get(bid)
            fc = r["fact_count"]
            dc = r["doc_count"]
            if exp is None:
                status["UNKNOWN"].append((bid, fc, dc, -1))
            elif dc == 0 and fc == 0:
                status["EMPTY"].append((bid, fc, dc, exp))
            elif dc < exp:
                status["PARTIAL"].append((bid, fc, dc, exp))
            else:
                status["COMPLETE"].append((bid, fc, dc, exp))

        missing = [b for b in expected if b not in seen]

        print(f"\n=== LongMemEval bank diagnosis ===")
        print(f"Expected banks: {len(expected)}")
        print(f"Found banks:    {len(seen)}")
        print(f"  COMPLETE:     {len(status['COMPLETE'])}")
        print(f"  PARTIAL:      {len(status['PARTIAL'])}  <-- will be wrongly skipped by resume")
        print(f"  EMPTY:        {len(status['EMPTY'])}   (skip-check will re-ingest these)")
        print(f"  UNKNOWN:      {len(status['UNKNOWN'])}")
        print(f"MISSING banks: {len(missing)}    (never started, resume will ingest)")

        if status["PARTIAL"]:
            print("\nPARTIAL banks (docs < expected):")
            for bid, fc, dc, exp in status["PARTIAL"][:30]:
                print(f"  {bid}  facts={fc:>5}  docs={dc:>3}/{exp}")
            if len(status["PARTIAL"]) > 30:
                print(f"  ... ({len(status['PARTIAL'])-30} more)")

        if status["EMPTY"]:
            print(f"\nEMPTY banks (sample): {[b for b, *_ in status['EMPTY'][:5]]}")

        if not fix:
            if status["PARTIAL"]:
                print("\nRun with --fix to delete partial banks so resume re-ingests them cleanly.")
            return

        if not status["PARTIAL"]:
            print("\nNo partial banks to fix.")
            return

        print(f"\n[FIX] deleting {len(status['PARTIAL'])} partial banks...")
        ctx = RequestContext()
        for i, (bid, fc, dc, exp) in enumerate(status["PARTIAL"], 1):
            await memory.delete_bank(bid, request_context=ctx)
            print(f"  [{i}/{len(status['PARTIAL'])}] deleted {bid} (had {fc} facts, {dc}/{exp} docs)")
        print("\nDone. Resume ingestion now; skip-if-exists will correctly re-ingest the cleared banks.")
    finally:
        await memory.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fix", action="store_true", help="Delete partial banks (default: dry-run)")
    args = p.parse_args()
    asyncio.run(run(args.fix))


if __name__ == "__main__":
    main()
