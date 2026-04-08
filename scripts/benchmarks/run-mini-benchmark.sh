#!/bin/bash
# Quick mini-benchmark for PR-level precision regression checking.
# Runs a small sample of LoCoMo questions and checks for regression.
#
# Usage:
#   ./scripts/benchmarks/run-mini-benchmark.sh                    # default: 2 convs, baseline 89%
#   ./scripts/benchmarks/run-mini-benchmark.sh --baseline 85.0    # custom baseline
#   ./scripts/benchmarks/run-mini-benchmark.sh --max-regression 5 # wider tolerance

set -e
cd "$(dirname "$0")/../.."

# Defaults
BASELINE_ACCURACY=89.0
MAX_REGRESSION=5.0
MAX_CONVERSATIONS=2
RESULTS_FILE="hindsight-dev/benchmarks/locomo/results/mini_benchmark_results.json"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --baseline) BASELINE_ACCURACY="$2"; shift 2 ;;
        --max-regression) MAX_REGRESSION="$2"; shift 2 ;;
        --max-conversations) MAX_CONVERSATIONS="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 2 ;;
    esac
done

# Load environment
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: Environment file $ENV_FILE not found"
    exit 2
fi
set -a
source "$ENV_FILE"
set +a

echo "=== Mini-Benchmark: LoCoMo ($MAX_CONVERSATIONS conversations) ==="
echo "Baseline: ${BASELINE_ACCURACY}%  Max regression: ${MAX_REGRESSION}pp"
echo ""

# Run LoCoMo with limited conversations
# Use a separate results file to avoid overwriting full benchmark results
RESULTS_FILENAME="mini_benchmark_results.json"
uv run python hindsight-dev/benchmarks/locomo/locomo_benchmark.py \
    --max-conversations "$MAX_CONVERSATIONS" \
    2>&1 | tail -20

# Check if results file exists (the benchmark writes to default location)
ACTUAL_RESULTS="hindsight-dev/benchmarks/locomo/results/benchmark_results.json"
if [ ! -f "$ACTUAL_RESULTS" ]; then
    echo "Error: Results file not found at $ACTUAL_RESULTS"
    exit 2
fi

echo ""
echo "=== Regression Check ==="
python scripts/benchmarks/check_regression.py \
    --results "$ACTUAL_RESULTS" \
    --baseline-accuracy "$BASELINE_ACCURACY" \
    --max-regression "$MAX_REGRESSION"
