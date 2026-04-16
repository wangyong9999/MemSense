#!/usr/bin/env python3
"""Ingest benchmark data into a persistent database for reuse with --skip-ingestion.

This script ONLY does ingestion (no evaluation, no answer generation, no LLM judge).
After running, the database contains all ingested facts and can be reused by:

    ./scripts/benchmarks/run-locomo.sh --skip-ingestion
    ./scripts/benchmarks/run-longmemeval.sh --skip-ingestion

Usage:
    # Ingest LoCoMo (2 conversations for smoke test):
    uv run python scripts/benchmarks/ingest-benchmark-db.py locomo --max-items 2

    # Ingest LoCoMo (all 10 conversations):
    uv run python scripts/benchmarks/ingest-benchmark-db.py locomo

    # Ingest LongMemEval (10 questions for smoke test):
    uv run python scripts/benchmarks/ingest-benchmark-db.py longmemeval --max-items 10

    # List existing banks in database:
    uv run python scripts/benchmarks/ingest-benchmark-db.py --list-banks
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hindsight-dev"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def list_banks():
    """List all banks in the current database."""
    from benchmarks.common.benchmark_runner import create_memory_engine

    memory = await create_memory_engine()
    try:
        pool = await memory._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.bank_id,
                       COUNT(mu.id) as fact_count,
                       MIN(mu.created_at) as first_created,
                       MAX(mu.created_at) as last_created
                FROM banks b
                LEFT JOIN memory_units mu ON mu.bank_id = b.bank_id
                GROUP BY b.bank_id
                ORDER BY b.bank_id
                """
            )
            if not rows:
                print("No banks found in database.")
                return

            print(f"{'Bank ID':<35} {'Facts':>8} {'First Created':<22} {'Last Created':<22}")
            print("-" * 90)
            for row in rows:
                fc = row["fact_count"] or 0
                first = str(row["first_created"])[:19] if row["first_created"] else "N/A"
                last = str(row["last_created"])[:19] if row["last_created"] else "N/A"
                print(f"{row['bank_id']:<35} {fc:>8} {first:<22} {last:<22}")
    finally:
        await memory.close()


async def ingest_locomo(max_items: int | None, wait_consolidation: bool, force_item: str | None = None):
    """Ingest LoCoMo conversations into separate banks."""
    from benchmarks.common.benchmark_runner import create_memory_engine
    from benchmarks.locomo.locomo_benchmark import LoComoDataset

    memory = await create_memory_engine()
    try:
        dataset = LoComoDataset()
        dataset_path = Path(__file__).parent.parent.parent / "hindsight-dev" / "benchmarks" / "locomo" / "datasets" / "locomo10.json"
        items = dataset.load(dataset_path, max_items)
        print(f"Loaded {len(items)} conversations from {dataset_path}")

        from hindsight_api.models import RequestContext

        for i, item in enumerate(items):
            item_id = dataset.get_item_id(item)
            agent_id = f"locomo_{item_id}"
            print(f"\n[{i+1}/{len(items)}] Ingesting {item_id} into bank '{agent_id}'...")

            # Force mode: clear and re-ingest a specific item
            if force_item and item_id == force_item:
                print(f"  --force: clearing bank '{agent_id}' for re-ingestion...")
                await memory.delete_bank(agent_id, request_context=RequestContext())
            elif force_item and item_id != force_item:
                print(f"  Skipping (--force targets {force_item} only)")
                continue

            # Check if bank already has data (skip-if-exists)
            try:
                pool = await memory._get_pool()
                async with pool.acquire() as conn:
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM memory_units WHERE bank_id = $1", agent_id
                    )
                    if count and count > 0:
                        print(f"  Bank '{agent_id}' already has {count} facts. Skipping.")
                        continue
            except Exception as e:
                logger.debug(f"Skip check failed (table may not exist yet): {e}")

            # Ensure bank exists
            await memory.get_bank_profile(agent_id, request_context=RequestContext())

            # Prepare sessions for ingestion
            sessions = dataset.prepare_sessions_for_ingestion(item)
            print(f"  Prepared {len(sessions)} sessions")

            # Ingest in batch
            t0 = time.time()
            await memory.retain_batch_async(
                bank_id=agent_id,
                contents=sessions,
                request_context=RequestContext(),
            )
            await memory.wait_for_background_tasks()
            elapsed = time.time() - t0
            print(f"  Ingested in {elapsed:.1f}s")

            # Count facts
            pool = await memory._get_pool()
            async with pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM memory_units WHERE bank_id = $1", agent_id
                )
            print(f"  Bank '{agent_id}' now has {count} facts")

            if wait_consolidation:
                print("  Note: consolidation runs asynchronously in the background.")

        # Summary
        print("\n" + "=" * 60)
        print("  Ingestion Complete")
        print("=" * 60)
        print(f"  Conversations: {len(items)}")
        print(f"  DB URL: {os.environ.get('HINDSIGHT_API_DATABASE_URL', 'pg0 (default)')}")
        print(f"\n  Run evaluation with:")
        print(f"    ./scripts/benchmarks/run-locomo.sh --skip-ingestion")
        print("=" * 60)
    finally:
        await memory.close()


async def ingest_longmemeval(max_items: int | None, wait_consolidation: bool, force_item: str | None = None, reverse: bool = False, shard: tuple[int, int] | None = None):
    """Ingest LongMemEval questions into separate banks."""
    from benchmarks.common.benchmark_runner import create_memory_engine
    from benchmarks.longmemeval.longmemeval_benchmark import LongMemEvalDataset

    memory = await create_memory_engine()
    try:
        dataset = LongMemEvalDataset()
        dataset_path = Path(__file__).parent.parent.parent / "hindsight-dev" / "benchmarks" / "longmemeval" / "datasets" / "longmemeval_s_cleaned.json"
        items = dataset.load(dataset_path, max_items)
        if reverse:
            items = list(reversed(items))
        if shard is not None:
            shard_idx, shard_total = shard
            items = [item for i, item in enumerate(items) if i % shard_total == shard_idx]
        shard_label = f" shard={shard[0]}/{shard[1]}" if shard else ""
        print(f"Loaded {len(items)} questions from {dataset_path} (reverse={reverse}{shard_label})")

        from hindsight_api.models import RequestContext

        for i, item in enumerate(items):
            item_id = dataset.get_item_id(item)
            agent_id = f"longmemeval_{item_id}"
            print(f"\n[{i+1}/{len(items)}] Ingesting {item_id} into bank '{agent_id}'...")

            if force_item and item_id == force_item:
                print(f"  --force: clearing bank '{agent_id}' for re-ingestion...")
                await memory.delete_bank(agent_id, request_context=RequestContext())
            elif force_item and item_id != force_item:
                print(f"  Skipping (--force targets {force_item} only)")
                continue

            # Check if bank already has data (skip-if-exists)
            try:
                pool = await memory._get_pool()
                async with pool.acquire() as conn:
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM memory_units WHERE bank_id = $1", agent_id
                    )
                    if count and count > 0:
                        print(f"  Bank '{agent_id}' already has {count} facts. Skipping.")
                        continue
            except Exception:
                pass

            await memory.get_bank_profile(agent_id, request_context=RequestContext())

            sessions = dataset.prepare_sessions_for_ingestion(item)
            print(f"  Prepared {len(sessions)} sessions")

            t0 = time.time()
            await memory.retain_batch_async(
                bank_id=agent_id,
                contents=sessions,
                request_context=RequestContext(),
            )
            await memory.wait_for_background_tasks()
            elapsed = time.time() - t0
            print(f"  Ingested in {elapsed:.1f}s")

            pool = await memory._get_pool()
            async with pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM memory_units WHERE bank_id = $1", agent_id
                )
            print(f"  Bank '{agent_id}' now has {count} facts")

        print("\n" + "=" * 60)
        print("  Ingestion Complete")
        print("=" * 60)
        print(f"  Questions: {len(items)}")
        print(f"  DB URL: {os.environ.get('HINDSIGHT_API_DATABASE_URL', 'pg0 (default)')}")
        print(f"\n  Run evaluation with:")
        print(f"    ./scripts/benchmarks/run-longmemeval.sh --skip-ingestion")
        print("=" * 60)
    finally:
        await memory.close()


def main():
    parser = argparse.ArgumentParser(description="Ingest benchmark data into persistent database")
    parser.add_argument("benchmark", nargs="?", choices=["locomo", "longmemeval"],
                        help="Which benchmark to ingest")
    parser.add_argument("--max-items", type=int, default=None,
                        help="Max items to ingest (conversations for LoCoMo, questions for LongMemEval)")
    parser.add_argument("--list-banks", action="store_true",
                        help="List existing banks in database")
    parser.add_argument("--force", type=str, default=None,
                        help="Force re-ingest a specific item (e.g., conv-41). Clears its bank first.")
    parser.add_argument("--wait-consolidation", action="store_true",
                        help="Wait for observation consolidation after each item")
    parser.add_argument("--reverse", action="store_true",
                        help="Iterate items in reverse order (use to parallelize 2 workers)")
    parser.add_argument("--shard", type=str, default=None,
                        help="Shard partition K/N: this worker handles items where index %% N == K (e.g., --shard 0/5)")
    args = parser.parse_args()

    if args.list_banks:
        asyncio.run(list_banks())
        return

    if not args.benchmark:
        parser.error("benchmark is required (locomo or longmemeval)")

    shard = None
    if args.shard:
        k, n = args.shard.split("/")
        shard = (int(k), int(n))

    if args.benchmark == "locomo":
        asyncio.run(ingest_locomo(args.max_items, args.wait_consolidation, force_item=args.force))
    else:
        asyncio.run(ingest_longmemeval(args.max_items, args.wait_consolidation, force_item=args.force, reverse=args.reverse, shard=shard))


if __name__ == "__main__":
    main()
