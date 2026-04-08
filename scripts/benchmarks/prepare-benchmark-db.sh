#!/bin/bash
# Prepare a persistent benchmark memory database.
#
# This script ingests benchmark conversations into a dedicated pg0 instance,
# then stops. The ingested data persists on disk and can be reused by
# running evaluations with --skip-ingestion.
#
# Usage:
#   # Ingest LoCoMo (all 10 conversations):
#   ./scripts/benchmarks/prepare-benchmark-db.sh locomo
#
#   # Ingest only 2 conversations (quick smoke test):
#   ./scripts/benchmarks/prepare-benchmark-db.sh locomo --max-conversations 2
#
#   # Ingest LongMemEval:
#   ./scripts/benchmarks/prepare-benchmark-db.sh longmemeval --max-instances 50
#
# After ingestion, run evaluation with:
#   HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo" \
#     ./scripts/benchmarks/run-locomo.sh --skip-ingestion
#
# The database lives in pg0's data directory under the instance name
# "bench-locomo" or "bench-longmemeval" and persists across process restarts.

set -e
cd "$(dirname "$0")/../.."

BENCHMARK="$1"
shift || { echo "Usage: $0 <locomo|longmemeval> [extra args...]"; exit 1; }

case "$BENCHMARK" in
    locomo)
        DB_INSTANCE="bench-locomo"
        SCRIPT="hindsight-dev/benchmarks/locomo/locomo_benchmark.py"
        ;;
    longmemeval)
        DB_INSTANCE="bench-longmemeval"
        SCRIPT="hindsight-dev/benchmarks/longmemeval/longmemeval_benchmark.py"
        ;;
    *)
        echo "Unknown benchmark: $BENCHMARK (use 'locomo' or 'longmemeval')"
        exit 1
        ;;
esac

# Load base environment
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

# Override database to use dedicated benchmark instance
export HINDSIGHT_API_DATABASE_URL="pg0://${DB_INSTANCE}"

echo "============================================"
echo "  Benchmark DB Preparation"
echo "============================================"
echo "  Benchmark:  $BENCHMARK"
echo "  DB instance: $DB_INSTANCE"
echo "  DB URL:      pg0://${DB_INSTANCE}"
echo "  Extra args:  $@"
echo "============================================"
echo ""
echo "This will ingest conversations into a persistent database."
echo "After completion, run evaluation with:"
echo ""
echo "  HINDSIGHT_API_DATABASE_URL=\"pg0://${DB_INSTANCE}\" \\"
echo "    ./scripts/benchmarks/run-${BENCHMARK}.sh --skip-ingestion"
echo ""

# Run the benchmark (ingestion will happen, evaluation will also run)
# The key: database persists after process exits because pg0 data is on disk
uv run python "$SCRIPT" "$@"

echo ""
echo "============================================"
echo "  DB preparation complete!"
echo "  Instance: $DB_INSTANCE"
echo "  Reuse with: HINDSIGHT_API_DATABASE_URL=\"pg0://${DB_INSTANCE}\""
echo "============================================"
