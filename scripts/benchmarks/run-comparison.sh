#!/bin/bash
# Run the MemSense flag-matrix benchmark comparison.
#
# Drives 4 cells against the chosen benchmark (locomo by default) and
# writes each cell's results JSON into a timestamped directory under
# hindsight-dev/benchmarks/comparison/. After the last cell completes,
# _comparison_summary.py is invoked to render a markdown table.
#
# Prerequisites:
#   - .env populated with LLM keys + any API config
#   - DB available (or pg0 embedded)
#   - A full run can take 30+ minutes per cell depending on dataset size
#
# Usage:
#   scripts/benchmarks/run-comparison.sh
#   scripts/benchmarks/run-comparison.sh --benchmark longmemeval
#   scripts/benchmarks/run-comparison.sh --max-conversations 5 --max-questions 30
#   scripts/benchmarks/run-comparison.sh --cells baseline,all_on      # skip the middle cells

set -e
cd "$(dirname "$0")/../.."

BENCHMARK="locomo"
MAX_CONV=""
MAX_Q=""
CELLS_FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --benchmark)
      BENCHMARK="$2"; shift 2 ;;
    --max-conversations)
      MAX_CONV="$2"; shift 2 ;;
    --max-questions)
      MAX_Q="$2"; shift 2 ;;
    --cells)
      CELLS_FILTER="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# //'; exit 0 ;;
    *)
      echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

case "$BENCHMARK" in
  locomo|longmemeval) ;;
  *) echo "--benchmark must be 'locomo' or 'longmemeval' (got: $BENCHMARK)" >&2; exit 1 ;;
esac

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_DIR="hindsight-dev/benchmarks/comparison/${TIMESTAMP}-${BENCHMARK}"
mkdir -p "$OUT_DIR"
echo "Comparison run: $BENCHMARK"
echo "Output: $OUT_DIR"
echo ""

# Cell matrix — name : env overrides
declare -a CELLS=(
  "baseline|HINDSIGHT_API_RETAIN_POST_EXTRACTION_ENABLED=false HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED=false HINDSIGHT_API_RECALL_CACHE_ENABLED=false"
  "enrichment|HINDSIGHT_API_RETAIN_POST_EXTRACTION_ENABLED=true HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED=true HINDSIGHT_API_RECALL_CACHE_ENABLED=false"
  "cache|HINDSIGHT_API_RETAIN_POST_EXTRACTION_ENABLED=false HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED=false HINDSIGHT_API_RECALL_CACHE_ENABLED=true"
  "all_on|HINDSIGHT_API_RETAIN_POST_EXTRACTION_ENABLED=true HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED=true HINDSIGHT_API_RECALL_CACHE_ENABLED=true"
)

SOURCE_RESULT="hindsight-dev/benchmarks/${BENCHMARK}/results/benchmark_results.json"

for cell_spec in "${CELLS[@]}"; do
  cell_name="${cell_spec%%|*}"
  cell_env="${cell_spec##*|}"

  if [[ -n "$CELLS_FILTER" && ",$CELLS_FILTER," != *",$cell_name,"* ]]; then
    echo "[skip] $cell_name (not in --cells filter)"
    continue
  fi

  echo ""
  echo "============================================================"
  echo "Cell: $cell_name"
  echo "Overrides: $cell_env"
  echo "============================================================"

  EXTRA_ARGS=()
  [[ -n "$MAX_CONV" ]] && EXTRA_ARGS+=(--max-conversations "$MAX_CONV")
  [[ -n "$MAX_Q" ]] && EXTRA_ARGS+=(--max-questions "$MAX_Q")

  # shellcheck disable=SC2086
  env $cell_env bash "scripts/benchmarks/run-${BENCHMARK}.sh" "${EXTRA_ARGS[@]}"

  if [[ ! -f "$SOURCE_RESULT" ]]; then
    echo "Expected result file not produced: $SOURCE_RESULT" >&2
    exit 1
  fi

  cp "$SOURCE_RESULT" "$OUT_DIR/${cell_name}.json"
  echo "[ok] wrote $OUT_DIR/${cell_name}.json"
done

echo ""
echo "============================================================"
echo "All cells completed. Rendering summary..."
echo "============================================================"
uv run python scripts/benchmarks/_comparison_summary.py "$OUT_DIR"
