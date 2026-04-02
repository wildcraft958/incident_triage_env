#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS: $1${NC}"; }
fail() { echo -e "${RED}FAIL: $1${NC}"; exit 1; }

echo "=== OpenEnv Pre-Submission Validator ==="
echo ""

# 1. Python imports
echo "1. Testing Python imports..."
python -c "from incident_triage_env import IncidentTriageEnv, IncidentAction, IncidentObservation, IncidentReward" \
    && pass "Imports work" || fail "Import error"

# 2. All 3 tasks work
echo "2. Testing all tasks..."
python -c "
from incident_triage_env import IncidentTriageEnv, IncidentAction
for task in ['easy', 'medium', 'hard']:
    env = IncidentTriageEnv(task=task)
    obs = env.reset()
    assert not obs.done
    assert len(obs.available_services) >= 3
    gt = env.scenario['root_cause']
    obs, r, done, info = env.step(IncidentAction(
        action_type='diagnose',
        target_service=gt['service'],
        fault_type=gt['fault_type'],
        remediation=gt['remediation'],
    ))
    assert done
    assert r == 1.0
    print(f'  {task}: perfect score = {r}')
" && pass "All tasks work" || fail "Task failure"

# 3. Grader determinism
echo "3. Testing grader determinism..."
python -c "
from incident_triage_env.grader import grade_diagnosis
gt = {'service': 'x', 'fault_type': 'y', 'remediation': 'z'}
scores = set()
for _ in range(100):
    r = grade_diagnosis('x', 'y', 'z', gt, ['x'])
    scores.add(r['score'])
assert len(scores) == 1 and 1.0 in scores
" && pass "Grader is deterministic" || fail "Grader not deterministic"

# 4. Score range
echo "4. Testing score range [0.0, 1.0]..."
python -c "
from incident_triage_env.grader import grade_diagnosis
gt = {'service': 's', 'fault_type': 'f', 'remediation': 'r'}
for s in ['s', 'x', None]:
    for f in ['f', 'x', None]:
        for r in ['r', 'x', None]:
            result = grade_diagnosis(s, f, r, gt, ['s'])
            assert 0.0 <= result['score'] <= 1.0
" && pass "All scores in [0.0, 1.0]" || fail "Score out of range"

# 5. Docker
echo "5. Testing Docker build..."
docker build -t incident-triage-env . > /dev/null 2>&1 \
    && pass "Docker builds" || fail "Docker build failed"

# 6. Docker run + API
echo "6. Testing Docker API..."
docker run -d --name ite-validate -p 7861:7860 incident-triage-env > /dev/null 2>&1
sleep 3
curl -sf http://localhost:7861/ > /dev/null \
    && pass "API responds to GET /" || fail "API not responding"
curl -sf -X POST http://localhost:7861/reset \
    -H "Content-Type: application/json" \
    -d '{"task":"easy"}' > /dev/null \
    && pass "reset() works via API" || fail "reset() failed"
docker stop ite-validate > /dev/null 2>&1
docker rm ite-validate > /dev/null 2>&1

# 7. inference.py exists
echo "7. Checking inference.py..."
[ -f inference.py ] && pass "inference.py exists" || fail "inference.py not found"

# 8. openenv.yaml exists
echo "8. Checking openenv.yaml..."
[ -f openenv.yaml ] && pass "openenv.yaml exists" || fail "openenv.yaml not found"

echo ""
echo "=== ALL CHECKS PASSED ==="
