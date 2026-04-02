#!/usr/bin/env bash
set -euo pipefail

echo "=== Running Baseline Inference ==="
echo "Make sure HF_TOKEN is set!"
echo ""

if [ -z "${HF_TOKEN:-}" ]; then
    echo "HF_TOKEN not set. Run: export HF_TOKEN=hf_your_token"
    exit 1
fi

export API_BASE_URL="${API_BASE_URL:-https://router.huggingface.co/v1}"
export MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-72B-Instruct}"

echo "Using:"
echo "  API_BASE_URL: $API_BASE_URL"
echo "  MODEL_NAME:   $MODEL_NAME"
echo ""

python inference.py 2>&1 | tee baseline_results.log

echo ""
echo "Results saved to baseline_results.log"
