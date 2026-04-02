#!/usr/bin/env bash
#
# run_baseline.sh -- Run the baseline LLM agent against all tasks
#
# Runs inference.py with the configured model and saves structured output.
# Supports dry-run mode for testing without an LLM.
#
# Usage:
#   bash scripts/run_baseline.sh                  # full run (needs HF_TOKEN)
#   bash scripts/run_baseline.sh --dry-run        # no LLM, heuristic actions
#   bash scripts/run_baseline.sh --model Qwen/Qwen2.5-72B-Instruct
#
set -euo pipefail

# --- Defaults ---
DRY_RUN=false
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3.5-27B}"
API_BASE_URL="${API_BASE_URL:-https://router.huggingface.co/v1}"
OUTPUT_DIR="outputs"

# --- Parse args ---
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --model)   shift; MODEL_NAME="$1" ;;
        --model=*) MODEL_NAME="${arg#*=}" ;;
    esac
done

# --- Colors ---
if [ -t 1 ]; then
    BOLD='\033[1m'
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    NC='\033[0m'
else
    BOLD='' GREEN='' RED='' NC=''
fi

echo -e "${BOLD}=== Baseline Inference ===${NC}"
echo ""

# --- Check HF_TOKEN ---
if [ "$DRY_RUN" = false ]; then
    if [ -z "${HF_TOKEN:-}" ]; then
        echo -e "${RED}ERROR: HF_TOKEN not set.${NC}"
        echo ""
        echo "Set it with:"
        echo "  export HF_TOKEN=hf_your_token"
        echo ""
        echo "Or run in dry-run mode:"
        echo "  bash scripts/run_baseline.sh --dry-run"
        exit 1
    fi
fi

echo "  Mode:      $([ "$DRY_RUN" = true ] && echo 'DRY RUN (no LLM)' || echo 'LIVE')"
echo "  Model:     $MODEL_NAME"
echo "  API:       $API_BASE_URL"
echo ""

# --- Setup output ---
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
if [ "$DRY_RUN" = true ]; then
    LOGFILE="${OUTPUT_DIR}/dry_run_${TIMESTAMP}.log"
else
    LOGFILE="${OUTPUT_DIR}/baseline_${MODEL_NAME//\//_}_${TIMESTAMP}.log"
fi

# --- Run ---
export API_BASE_URL MODEL_NAME
if [ "$DRY_RUN" = true ]; then
    export INFERENCE_DRY_RUN=1
fi

START_TIME=$(date +%s)

python3 inference.py 2>&1 | tee "$LOGFILE"
EXIT_CODE=${PIPESTATUS[0]}

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "========================================="

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Inference completed in ${ELAPSED}s${NC}"
else
    echo -e "${RED}Inference failed with exit code $EXIT_CODE${NC}"
fi

# --- Parse scores from output ---
echo ""
echo -e "${BOLD}Score Summary:${NC}"
grep '^\[END\]' "$LOGFILE" | while IFS= read -r line; do
    task=$(grep '^\[START\]' "$LOGFILE" | head -1 | grep -oP 'task=\K[^ ]+')
    score=$(echo "$line" | grep -oP 'score=\K[0-9.]+')
    steps=$(echo "$line" | grep -oP 'steps=\K[0-9]+')
    success=$(echo "$line" | grep -oP 'success=\K[a-z]+')
    echo "  score=$score  steps=$steps  success=$success"
done

echo ""
echo "Full log: $LOGFILE"

if [ $ELAPSED -gt 1200 ]; then
    echo -e "${RED}WARNING: Runtime ${ELAPSED}s exceeds 20-minute limit!${NC}"
elif [ $ELAPSED -gt 900 ]; then
    echo -e "${RED}WARNING: Runtime ${ELAPSED}s approaching 20-minute limit.${NC}"
fi

exit $EXIT_CODE
