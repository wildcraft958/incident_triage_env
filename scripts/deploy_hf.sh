#!/usr/bin/env bash
#
# deploy_hf.sh -- Deploy incident-triage-env to HuggingFace Spaces
#
# Preferred method: uses `openenv push` which handles Dockerfile rewriting
# and HF Space configuration automatically.
#
# Fallback: manual push via huggingface-cli if openenv push is not available.
#
# Usage:
#   bash scripts/deploy_hf.sh                              # uses openenv push
#   bash scripts/deploy_hf.sh --repo-id user/my-env        # custom repo
#   bash scripts/deploy_hf.sh --private                    # private space
#   bash scripts/deploy_hf.sh --manual user/my-env         # skip openenv push
#
set -euo pipefail

REPO_ID=""
PRIVATE=false
MANUAL=false

for arg in "$@"; do
    case "$arg" in
        --repo-id)  shift; REPO_ID="$1" ;;
        --repo-id=*) REPO_ID="${arg#*=}" ;;
        --private)  PRIVATE=true ;;
        --manual)   MANUAL=true; shift; REPO_ID="${1:-}" ;;
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

echo -e "${BOLD}=== Deploy to HuggingFace Spaces ===${NC}"
echo ""

# --- Check HF auth ---
if [ -z "${HF_TOKEN:-}" ]; then
    echo "Checking HF CLI login..."
    if ! huggingface-cli whoami &>/dev/null 2>&1; then
        echo -e "${RED}Not logged in to HuggingFace.${NC}"
        echo ""
        echo "Either:"
        echo "  export HF_TOKEN=hf_your_token"
        echo "  huggingface-cli login"
        exit 1
    fi
    HF_USER=$(huggingface-cli whoami 2>/dev/null | head -1)
    echo "  Logged in as: $HF_USER"
else
    echo "  Using HF_TOKEN from environment"
    HF_USER=$(python3 -c "
from huggingface_hub import HfApi
api = HfApi(token='${HF_TOKEN}')
print(api.whoami()['name'])
" 2>/dev/null || echo "unknown")
    echo "  Account: $HF_USER"
fi

if [ -z "$REPO_ID" ]; then
    REPO_ID="${HF_USER}/incident-triage-env"
fi

echo "  Target: $REPO_ID"
echo ""

# --- Pre-flight checks ---
echo -e "${BOLD}Pre-flight checks...${NC}"

if [ ! -f openenv.yaml ]; then
    echo -e "${RED}openenv.yaml not found. Run from the project root.${NC}"
    exit 1
fi

if [ ! -f Dockerfile ]; then
    echo -e "${RED}Dockerfile not found.${NC}"
    exit 1
fi

if [ ! -f README.md ]; then
    echo -e "${RED}README.md not found.${NC}"
    exit 1
fi

# Check README has required frontmatter
if ! grep -q 'tags:' README.md; then
    echo -e "${RED}README.md missing 'tags:' in frontmatter.${NC}"
    exit 1
fi
if ! grep -q 'openenv' README.md; then
    echo -e "${RED}README.md missing 'openenv' tag.${NC}"
    exit 1
fi
if ! grep -q 'app_port:' README.md; then
    echo -e "${RED}README.md missing 'app_port:' in frontmatter.${NC}"
    exit 1
fi

echo -e "  ${GREEN}All pre-flight checks passed${NC}"
echo ""

# --- Deploy ---
if [ "$MANUAL" = false ] && command -v openenv &>/dev/null; then
    echo -e "${BOLD}Deploying with openenv push...${NC}"
    CMD="openenv push --repo-id $REPO_ID"
    if [ "$PRIVATE" = true ]; then
        CMD="$CMD --private"
    fi
    echo "  Running: $CMD"
    echo ""
    $CMD
else
    echo -e "${BOLD}Deploying manually via huggingface-cli...${NC}"

    if [ -z "$REPO_ID" ]; then
        echo -e "${RED}--repo-id required for manual deploy${NC}"
        exit 1
    fi

    # Create space if it doesn't exist
    python3 -c "
from huggingface_hub import HfApi
api = HfApi()
try:
    api.create_repo('${REPO_ID}', repo_type='space', space_sdk='docker', private=${PRIVATE})
    print('  Created space: ${REPO_ID}')
except Exception as e:
    if 'already' in str(e).lower() or '409' in str(e):
        print('  Space already exists: ${REPO_ID}')
    else:
        raise
"

    # Upload all files
    python3 -c "
from huggingface_hub import HfApi
api = HfApi()
api.upload_folder(
    folder_path='.',
    repo_id='${REPO_ID}',
    repo_type='space',
    ignore_patterns=['.env', '.venv', '__pycache__', '.git', '*.pyc', '.pytest_cache',
                     'outputs', 'logs', '.claude', 'CLAUDE.md', 'uv.lock'],
)
print('  Upload complete')
"
fi

echo ""
echo "========================================="
echo -e "${GREEN}Deployed to: https://huggingface.co/spaces/${REPO_ID}${NC}"

# Extract username and space name for the URL
OWNER=$(echo "$REPO_ID" | cut -d'/' -f1)
SPACE=$(echo "$REPO_ID" | cut -d'/' -f2)
echo "Space URL:   https://${OWNER}-${SPACE}.hf.space"
echo ""
echo "Next steps:"
echo "  1. Wait for the Space to build (check the Logs tab)"
echo "  2. Verify: curl https://${OWNER}-${SPACE}.hf.space/"
echo "  3. Run: bash scripts/validate.sh https://${OWNER}-${SPACE}.hf.space"
