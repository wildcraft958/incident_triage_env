#!/usr/bin/env bash
#
# validate.sh -- Pre-submission validation for incident-triage-env
#
# Checks everything the competition auto-evaluator will check:
#   1. Python imports and openenv validate
#   2. All 3 tasks reset/step/diagnose correctly
#   3. Grader determinism and score range
#   4. Inference dry-run produces correct stdout format
#   5. Docker builds and serves
#   6. API health, reset, step all respond
#   7. Required files exist
#
# Usage:
#   bash scripts/validate.sh              # full validation (includes Docker)
#   bash scripts/validate.sh --no-docker  # skip Docker checks (faster)
#
set -uo pipefail

SKIP_DOCKER=false
PING_URL=""
for arg in "$@"; do
    case "$arg" in
        --no-docker) SKIP_DOCKER=true ;;
        *) PING_URL="$arg" ;;
    esac
done

# --- Colors ---
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' RED='' YELLOW='' BOLD='' NC=''
fi

PASSED=0
FAILED=0
WARNINGS=0

pass()  { echo -e "  ${GREEN}PASS${NC}  $1"; PASSED=$((PASSED + 1)); }
fail()  { echo -e "  ${RED}FAIL${NC}  $1"; FAILED=$((FAILED + 1)); }
warn()  { echo -e "  ${YELLOW}WARN${NC}  $1"; WARNINGS=$((WARNINGS + 1)); }

echo -e "${BOLD}=== OpenEnv Pre-Submission Validator ===${NC}"
echo ""

# ------------------------------------------------------------------
# 1. Required files
# ------------------------------------------------------------------
echo -e "${BOLD}1. Required files${NC}"
for f in openenv.yaml models.py client.py inference.py README.md pyproject.toml server/app.py server/Dockerfile server/incident_triage_environment.py; do
    if [ -f "$f" ]; then
        pass "$f"
    else
        fail "$f missing"
    fi
done

# ------------------------------------------------------------------
# 2. openenv validate
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}2. openenv validate${NC}"
if command -v openenv &>/dev/null; then
    output=$(openenv validate 2>&1)
    if echo "$output" | grep -q "\[OK\]"; then
        pass "openenv validate: $output"
    else
        fail "openenv validate: $output"
    fi
else
    warn "openenv CLI not installed, skipping"
fi

# ------------------------------------------------------------------
# 3. Python imports
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}3. Python imports${NC}"
if python3 -c "from incident_triage_env import IncidentTriageEnv, IncidentAction, IncidentObservation, IncidentReward" 2>/dev/null; then
    pass "incident_triage_env imports"
else
    fail "incident_triage_env import error"
fi
if python3 -c "from models import IncidentAction, IncidentObservation" 2>/dev/null; then
    pass "root models.py imports (openenv types)"
else
    fail "root models.py import error"
fi

# ------------------------------------------------------------------
# 4. All 3 tasks: reset, step, diagnose
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}4. Task validation (easy/medium/hard)${NC}"
python3 -c "
from incident_triage_env import IncidentTriageEnv, IncidentAction

scores = {}
for task in ['easy', 'medium', 'hard']:
    env = IncidentTriageEnv(task=task)
    obs = env.reset()
    assert not obs.done, f'{task}: reset() returned done=True'
    assert len(obs.available_services) >= 3, f'{task}: fewer than 3 services'
    assert obs.summary, f'{task}: empty summary'
    assert obs.incident_id, f'{task}: empty incident_id'

    # test a non-terminal step
    obs2, r, done, info = env.step(IncidentAction(action_type='check_topology'))
    assert not done, f'{task}: check_topology ended episode'

    # test perfect diagnosis
    env2 = IncidentTriageEnv(task=task)
    env2.reset()
    gt = env2.scenario['root_cause']
    obs3, score, done2, _ = env2.step(IncidentAction(
        action_type='diagnose',
        target_service=gt['service'],
        fault_type=gt['fault_type'],
        remediation=gt['remediation'],
    ))
    assert done2, f'{task}: diagnose did not end episode'
    assert score == 1.0, f'{task}: perfect diagnosis scored {score}, expected 1.0'
    scores[task] = score
    print(f'  {task}: {len(obs.available_services)} services, perfect score = {score}')

# test wrong diagnosis gives different score
env3 = IncidentTriageEnv(task='easy')
env3.reset()
_, bad_score, _, _ = env3.step(IncidentAction(
    action_type='diagnose', target_service='wrong', fault_type='wrong', remediation='wrong',
))
assert bad_score != 1.0, 'wrong diagnosis returned 1.0 -- grader is constant!'
print(f'  grader variance: perfect=1.0, wrong={bad_score}')
" 2>&1 && pass "All tasks work, grader not constant" || fail "Task validation failed"

# ------------------------------------------------------------------
# 5. Grader determinism and range
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}5. Grader determinism and score range${NC}"
python3 -c "
from incident_triage_env.grader import grade_diagnosis

gt = {'service': 'svc-a', 'fault_type': 'oom', 'remediation': 'restart'}
chain = ['svc-a', 'svc-b']

# determinism: same input 100 times
scores = set()
for _ in range(100):
    r = grade_diagnosis('svc-a', 'oom', 'restart', gt, chain)
    scores.add(r['score'])
assert len(scores) == 1, f'non-deterministic: got {len(scores)} distinct scores'
print(f'  determinism: 100 identical calls -> {len(scores)} distinct score (1.0)')

# range: try all combos
for s in ['svc-a', 'svc-b', 'wrong', None]:
    for f in ['oom', 'wrong', None]:
        for rem in ['restart', 'wrong', None]:
            r = grade_diagnosis(s, f, rem, gt, chain)
            assert 0.0 <= r['score'] <= 1.0, f'score {r[\"score\"]} out of range for ({s},{f},{rem})'
print('  range: all combos in [0.0, 1.0]')
" 2>&1 && pass "Grader deterministic, all scores in [0.0, 1.0]" || fail "Grader check failed"

# ------------------------------------------------------------------
# 6. Inference dry-run
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}6. Inference dry-run${NC}"
DRY_OUTPUT=$(INFERENCE_DRY_RUN=1 python3 inference.py 2>&1)
DRY_EXIT=$?

if [ $DRY_EXIT -ne 0 ]; then
    fail "inference.py exited with code $DRY_EXIT"
else
    # Check format
    START_COUNT=$(echo "$DRY_OUTPUT" | grep -c '^\[START\]')
    STEP_COUNT=$(echo "$DRY_OUTPUT" | grep -c '^\[STEP\]')
    END_COUNT=$(echo "$DRY_OUTPUT" | grep -c '^\[END\]')

    if [ "$START_COUNT" -eq 3 ]; then
        pass "[START] emitted 3 times (one per task)"
    else
        fail "[START] emitted $START_COUNT times, expected 3"
    fi

    if [ "$STEP_COUNT" -ge 3 ]; then
        pass "[STEP] emitted $STEP_COUNT times"
    else
        fail "[STEP] emitted $STEP_COUNT times, expected >= 3"
    fi

    if [ "$END_COUNT" -eq 3 ]; then
        pass "[END] emitted 3 times (one per task)"
    else
        fail "[END] emitted $END_COUNT times, expected 3"
    fi

    # Check field format on a sample [STEP] line
    SAMPLE_STEP=$(echo "$DRY_OUTPUT" | grep '^\[STEP\]' | head -1)
    for field in "step=" "action=" "reward=" "done=" "error="; do
        if echo "$SAMPLE_STEP" | grep -q "$field"; then
            pass "[STEP] has $field field"
        else
            fail "[STEP] missing $field field: $SAMPLE_STEP"
        fi
    done

    # Check [END] has score field
    SAMPLE_END=$(echo "$DRY_OUTPUT" | grep '^\[END\]' | head -1)
    for field in "success=" "steps=" "score=" "rewards="; do
        if echo "$SAMPLE_END" | grep -q "$field"; then
            pass "[END] has $field field"
        else
            fail "[END] missing $field field: $SAMPLE_END"
        fi
    done
fi

# ------------------------------------------------------------------
# 7. Unit tests
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}7. Unit tests${NC}"
if command -v uv &>/dev/null; then
    TEST_OUT=$(uv run python -m pytest tests/ -v --tb=short 2>&1)
    TEST_EXIT=$?
    TOTAL=$(echo "$TEST_OUT" | grep -oP '\d+ passed' | head -1)
    if [ $TEST_EXIT -eq 0 ]; then
        pass "pytest: $TOTAL"
    else
        fail "pytest failed"
        echo "$TEST_OUT" | tail -20
    fi
else
    TEST_OUT=$(python3 -m pytest tests/ -v --tb=short 2>&1)
    TEST_EXIT=$?
    TOTAL=$(echo "$TEST_OUT" | grep -oP '\d+ passed' | head -1)
    if [ $TEST_EXIT -eq 0 ]; then
        pass "pytest: $TOTAL"
    else
        fail "pytest failed"
        echo "$TEST_OUT" | tail -20
    fi
fi

# ------------------------------------------------------------------
# 8. Docker (optional)
# ------------------------------------------------------------------
CONTAINER_NAME="ite-validate-$$"
if [ "$SKIP_DOCKER" = true ]; then
    echo ""
    echo -e "${BOLD}8. Docker (skipped with --no-docker)${NC}"
    warn "Docker checks skipped"
else
    echo ""
    echo -e "${BOLD}8. Docker build${NC}"
    if ! command -v docker &>/dev/null; then
        warn "Docker not installed, skipping"
    else
        BUILD_OUT=$(docker build -f server/Dockerfile -t incident-triage-env . 2>&1)
        if [ $? -eq 0 ]; then
            pass "docker build succeeded"
        else
            fail "docker build failed"
            echo "$BUILD_OUT" | tail -10
        fi

        echo ""
        echo -e "${BOLD}9. Docker API checks${NC}"
        docker rm -f "$CONTAINER_NAME" 2>/dev/null
        docker run -d --name "$CONTAINER_NAME" -p 8001:8000 incident-triage-env >/dev/null 2>&1

        # Wait for container to be ready
        READY=false
        for i in $(seq 1 15); do
            if curl -sf http://localhost:8001/health >/dev/null 2>&1; then
                READY=true
                break
            fi
            sleep 1
        done

        if [ "$READY" = true ]; then
            pass "Container healthy after ${i}s"

            # GET /
            if curl -sf http://localhost:8001/ >/dev/null 2>&1; then
                pass "GET / returns 200"
            else
                fail "GET / failed"
            fi

            # POST /reset
            RESET_OUT=$(curl -sf -X POST http://localhost:8001/reset \
                -H "Content-Type: application/json" \
                -d '{"task":"easy"}' 2>&1)
            if [ $? -eq 0 ] && echo "$RESET_OUT" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
                pass "POST /reset returns valid JSON"
            else
                fail "POST /reset failed"
            fi

            # GET /state
            if curl -sf http://localhost:8001/state >/dev/null 2>&1; then
                pass "GET /state returns 200"
            else
                fail "GET /state failed"
            fi

            # GET /metadata
            if curl -sf http://localhost:8001/metadata >/dev/null 2>&1; then
                pass "GET /metadata returns 200"
            else
                fail "GET /metadata failed"
            fi

            # GET /schema
            if curl -sf http://localhost:8001/schema >/dev/null 2>&1; then
                pass "GET /schema returns 200"
            else
                fail "GET /schema failed"
            fi
        else
            fail "Container did not become healthy in 15s"
        fi

        docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1
    fi
fi

# ------------------------------------------------------------------
# 10. Remote Space ping (optional)
# ------------------------------------------------------------------
if [ -n "$PING_URL" ]; then
    echo ""
    echo -e "${BOLD}10. Remote Space ping${NC}"
    if curl -sf "$PING_URL" >/dev/null 2>&1; then
        pass "Space responds at $PING_URL"
    else
        fail "Space not responding at $PING_URL"
    fi

    RESET_REMOTE=$(curl -sf -X POST "${PING_URL}/reset" \
        -H "Content-Type: application/json" \
        -d '{"task":"easy"}' 2>&1)
    if [ $? -eq 0 ]; then
        pass "Remote reset() works"
    else
        fail "Remote reset() failed"
    fi
fi

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo "========================================="
TOTAL=$((PASSED + FAILED))
echo -e "${BOLD}Results: ${GREEN}${PASSED} passed${NC}, ${RED}${FAILED} failed${NC}, ${YELLOW}${WARNINGS} warnings${NC} (${TOTAL} checks)"
echo "========================================="

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}FIX FAILURES BEFORE SUBMITTING${NC}"
    exit 1
else
    echo -e "${GREEN}ALL CHECKS PASSED -- ready to submit${NC}"
    exit 0
fi
