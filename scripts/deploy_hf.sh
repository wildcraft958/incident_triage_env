#!/usr/bin/env bash
set -euo pipefail

SPACE_NAME="${1:-incident-triage-env}"
HF_USERNAME="${2:-your-hf-username}"

echo "=== Deploying to HuggingFace Spaces ==="
echo "Space: ${HF_USERNAME}/${SPACE_NAME}"
echo ""

# Check huggingface-cli
if ! command -v huggingface-cli &> /dev/null; then
    echo "Installing huggingface_hub..."
    pip install huggingface_hub
fi

echo "Creating/updating space..."
huggingface-cli repo create "${SPACE_NAME}" --type space --space-sdk docker -y 2>/dev/null || true

# Clone and push
TEMP_DIR=$(mktemp -d)
git clone "https://huggingface.co/spaces/${HF_USERNAME}/${SPACE_NAME}" "$TEMP_DIR"
cp -r ./* "$TEMP_DIR/" 2>/dev/null || true
cp .gitignore "$TEMP_DIR/" 2>/dev/null || true

cd "$TEMP_DIR"
git add -A
git commit -m "Deploy incident-triage-env" || true
git push

echo ""
echo "Deployed to: https://huggingface.co/spaces/${HF_USERNAME}/${SPACE_NAME}"
echo "Space URL:   https://${HF_USERNAME}-${SPACE_NAME}.hf.space"

rm -rf "$TEMP_DIR"
