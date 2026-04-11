#!/bin/bash
# Evaluate LoCoMo benchmark against a persistent memory database.
# Memory bank is READ-ONLY — no ingestion, no deletion, no pollution.
#
# Usage:
#   # Quick validation (3 conversations, ~30min):
#   ./scripts/benchmarks/eval-locomo.sh kimi quick
#
#   # Full evaluation (all 10 conversations, ~1-2h):
#   ./scripts/benchmarks/eval-locomo.sh kimi full
#
#   # Single conversation:
#   ./scripts/benchmarks/eval-locomo.sh minimax conv-49
#
#   # Custom env file + db instance:
#   ENV_FILE=.env.custom DB_INSTANCE=bench-locomo-custom ./scripts/benchmarks/eval-locomo.sh custom full

set -e
cd "$(dirname "$0")/../.."

PROFILE="${1:?Usage: $0 <kimi|minimax|custom> <quick|full|conv-XX>}"
MODE="${2:-quick}"

# Determine env file and DB instance from profile
case "$PROFILE" in
    kimi)
        ENV_FILE="${ENV_FILE:-.env.kimi}"
        DB_INSTANCE="${DB_INSTANCE:-bench-locomo-kimi}"
        ;;
    minimax)
        ENV_FILE="${ENV_FILE:-.env}"
        DB_INSTANCE="${DB_INSTANCE:-bench-locomo-minimax}"
        ;;
    *)
        # Custom profile — ENV_FILE and DB_INSTANCE must be set externally
        ENV_FILE="${ENV_FILE:-.env}"
        DB_INSTANCE="${DB_INSTANCE:-bench-locomo-${PROFILE}}"
        ;;
esac

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a
export HINDSIGHT_API_DATABASE_URL="pg0://${DB_INSTANCE}"

# Results go to a profile-specific file to avoid overwriting
RESULTS_DIR="hindsight-dev/benchmarks/locomo/results"
mkdir -p "$RESULTS_DIR"

echo "============================================"
echo "  LoCoMo Evaluation (READ-ONLY)"
echo "============================================"
echo "  Profile:  $PROFILE"
echo "  Mode:     $MODE"
echo "  DB:       pg0://${DB_INSTANCE}"
echo "  Env:      $ENV_FILE"
echo "  Memory bank will NOT be modified."
echo "============================================"
echo ""

QUICK_CONVS="conv-49 conv-44 conv-48"

case "$MODE" in
    quick)
        # Run 3 representative conversations sequentially, merge results
        for CONV in $QUICK_CONVS; do
            echo ""
            echo ">>> Evaluating $CONV ..."
            uv run python hindsight-dev/benchmarks/locomo/locomo_benchmark.py \
                --skip-ingestion --conversation "$CONV"
        done
        ;;
    full)
        # Run all conversations
        uv run python hindsight-dev/benchmarks/locomo/locomo_benchmark.py \
            --skip-ingestion
        ;;
    conv-*)
        # Run a specific conversation
        uv run python hindsight-dev/benchmarks/locomo/locomo_benchmark.py \
            --skip-ingestion --conversation "$MODE"
        ;;
    *)
        echo "Unknown mode: $MODE (use quick, full, or conv-XX)"
        exit 1
        ;;
esac

echo ""
echo "============================================"
echo "  Evaluation complete!"
echo "  Results: ${RESULTS_DIR}/benchmark_results.json"
echo "============================================"

# Show summary if check_regression.py exists
if [ -f "scripts/benchmarks/check_regression.py" ]; then
    echo ""
    python scripts/benchmarks/check_regression.py \
        --results "${RESULTS_DIR}/benchmark_results.json" \
        --baseline-accuracy 70.0 \
        --max-regression 5.0 || true
fi
