#!/bin/bash
# Ingest LoCoMo benchmark into a persistent memory database.
#
# Creates a named pg0 instance with all facts + observations (consolidation).
# After ingestion, use eval-locomo.sh with matching DB_INSTANCE for evaluation.
#
# Usage:
#   # Default: ingest with consolidation (recommended, matches Hindsight official)
#   ./scripts/benchmarks/ingest-locomo.sh minimax bench-locomo-minimax-with-obs
#
#   # Without consolidation (raw facts only, for comparison)
#   ENABLE_OBS=false ./scripts/benchmarks/ingest-locomo.sh minimax bench-locomo-minimax-raw
#
#   # Specific conversations only
#   MAX_ITEMS=2 ./scripts/benchmarks/ingest-locomo.sh minimax bench-locomo-smoke

set -e
cd "$(dirname "$0")/../.."

PROFILE="${1:?Usage: $0 <minimax|kimi|custom> <instance-name>}"
INSTANCE="${2:?Usage: $0 <profile> <instance-name> (e.g. bench-locomo-minimax-with-obs)}"

# Determine env file
case "$PROFILE" in
    kimi)    ENV_FILE="${ENV_FILE:-.env.kimi}" ;;
    minimax) ENV_FILE="${ENV_FILE:-.env}" ;;
    *)       ENV_FILE="${ENV_FILE:-.env}" ;;
esac

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

export HINDSIGHT_API_DATABASE_URL="pg0://${INSTANCE}"

# Consolidation control (default: enabled, matching Hindsight official)
ENABLE_OBS="${ENABLE_OBS:-true}"
export HINDSIGHT_API_ENABLE_OBSERVATIONS="${ENABLE_OBS}"

# Retain mission: precision-preserving instructions for concise extraction.
# Complements (not replaces) concise mode's selectivity:
# - Concise mode decides WHICH facts to extract (skip greetings, filler)
# - Mission controls HOW facts are written (preserve specific nouns, not generalize)
#
# Addresses 19/25 extraction-gap errors in LoCoMo baseline analysis:
# - 9 quantity losses (nine→multiple, four months→several)
# - 5 proper noun losses (hoodie→clothing, Mafia→board game)
# - 3 place name losses (Talkeetna→mountain, Indiana→state)
# - 2 health term losses (asthma→health condition)
if [ -n "${RETAIN_MISSION}" ]; then
    export HINDSIGHT_API_RETAIN_MISSION="${RETAIN_MISSION}"
elif [ -z "${HINDSIGHT_API_RETAIN_MISSION}" ]; then
    export HINDSIGHT_API_RETAIN_MISSION="When writing the what field for each fact, preserve specific details verbatim from the source text. Do not generalize specific terms into broad categories.

Preserve exactly:
- Quantities and durations: write the exact number (\"nine tournaments\" not \"multiple tournaments\", \"four months\" not \"several months\", \"twice\" not \"multiple times\")
- Product, game, book, and food names: use the exact name spoken (\"hoodie\" not \"clothing item\", \"Chicken Pot Pie\" not \"a recipe\", \"Zelda BOTW\" not \"a video game\", \"Mafia\" not \"a board game\")
- Place names: keep geographical specifics (\"Talkeetna\" not \"a mountain\", \"Indiana\" not \"a US state\", \"Phuket\" not \"a retreat location\")
- Health and medical terms: name the condition (\"asthma\" not \"health issue\", \"obesity\" not \"health problem\")

The concise format still applies — keep each fact to 1-2 sentences. But within that space, use the speaker's original specific words rather than generic substitutes."
fi

# Optional: max conversations to ingest
MAX_ITEMS_ARG=""
if [ -n "${MAX_ITEMS}" ]; then
    MAX_ITEMS_ARG="--max-items ${MAX_ITEMS}"
fi

echo "============================================"
echo "  LoCoMo Ingestion"
echo "============================================"
echo "  Profile:      $PROFILE"
echo "  Instance:     pg0://${INSTANCE}"
echo "  Env:          $ENV_FILE"
echo "  Observations: ${ENABLE_OBS}"
echo "  Mission:      $([ -n "${HINDSIGHT_API_RETAIN_MISSION}" ] && echo 'set' || echo 'none')"
echo "  Max items:    ${MAX_ITEMS:-all}"
echo "============================================"
echo ""

# Phase 1: Ingest facts (no --wait-consolidation, async consolidation
# doesn't survive engine close in this script)
echo ">>> Phase 1: Ingesting facts..."
uv run python scripts/benchmarks/ingest-benchmark-db.py locomo ${MAX_ITEMS_ARG}

# Phase 2: Run consolidation explicitly per bank (synchronous, waits for completion)
if [ "${ENABLE_OBS}" = "true" ]; then
    echo ""
    echo ">>> Phase 2: Running consolidation (generating observations)..."
    uv run python -c "
import asyncio, sys, os
sys.path.insert(0, 'hindsight-api-slim')
sys.path.insert(0, 'hindsight-dev')
from hindsight_api.models import RequestContext

async def run_consolidation():
    from benchmarks.common.benchmark_runner import create_memory_engine
    engine = await create_memory_engine()
    try:
        pool = engine._pool
        async with pool.acquire() as conn:
            banks = await conn.fetch(
                'SELECT DISTINCT bank_id FROM memory_units ORDER BY bank_id'
            )

        print(f'  Found {len(banks)} banks to consolidate')
        for row in banks:
            bank_id = row['bank_id']
            print(f'  Consolidating {bank_id}...')
            result = await engine.run_consolidation(
                bank_id=bank_id,
                request_context=RequestContext(),
            )
            created = result.get('created', 0)
            updated = result.get('updated', 0)
            processed = result.get('processed', 0)
            print(f'    processed={processed}, created={created}, updated={updated}')
    finally:
        await engine.close()

asyncio.run(run_consolidation())
"
fi

# Phase 3: Verify final state
echo ""
echo ">>> Phase 3: Verifying database state..."
uv run python -c "
import asyncio, sys, os
sys.path.insert(0, 'hindsight-api-slim')
sys.path.insert(0, 'hindsight-dev')
os.environ['HINDSIGHT_API_SKIP_LLM_VERIFICATION'] = 'true'

async def verify():
    from benchmarks.common.benchmark_runner import create_memory_engine
    engine = await create_memory_engine()
    try:
        pool = engine._pool
        async with pool.acquire() as conn:
            total = await conn.fetchval('SELECT COUNT(*) FROM memory_units')
            world = await conn.fetchval(\"SELECT COUNT(*) FROM memory_units WHERE fact_type='world'\")
            exp = await conn.fetchval(\"SELECT COUNT(*) FROM memory_units WHERE fact_type='experience'\")
            obs = await conn.fetchval(\"SELECT COUNT(*) FROM memory_units WHERE fact_type='observation'\")
            consolidated = await conn.fetchval('SELECT COUNT(*) FROM memory_units WHERE consolidated_at IS NOT NULL')
            pending = await conn.fetchval(
                \"SELECT COUNT(*) FROM memory_units WHERE consolidated_at IS NULL AND consolidation_failed_at IS NULL AND fact_type != 'observation'\"
            )

            print(f'  Total memory units: {total}')
            print(f'    world:       {world}')
            print(f'    experience:  {exp}')
            print(f'    observation: {obs}')
            print(f'  Consolidated:  {consolidated}')
            print(f'  Pending:       {pending}')

            if obs > 0:
                print(f'  ✓ Observations generated successfully')
            elif '${ENABLE_OBS}' == 'true':
                print(f'  ⚠ WARNING: No observations generated')
    finally:
        await engine.close()

asyncio.run(verify())
"

echo ""
echo "============================================"
echo "  Ingestion Complete"
echo "============================================"
echo "  Instance: pg0://${INSTANCE}"
echo ""
echo "  Run evaluation with:"
echo "    DB_INSTANCE=${INSTANCE} ./scripts/benchmarks/eval-locomo.sh ${PROFILE} quick"
echo "    DB_INSTANCE=${INSTANCE} ./scripts/benchmarks/eval-locomo.sh ${PROFILE} full"
echo "============================================"
