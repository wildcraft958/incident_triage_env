.PHONY: install test lint docker-build docker-run docker-test validate inference clean

# --- Development ----------------------------------------------------

install:
	pip install -r requirements.txt
	pip install pytest httpx

test:
	python -m pytest tests/ -v --tb=short

test-grader:
	python -m pytest tests/test_grader.py -v

test-env:
	python -m pytest tests/test_env.py -v

test-scenarios:
	python -m pytest tests/test_scenarios.py -v

test-api:
	python -m pytest tests/test_api.py -v

# --- Quick Smoke Test -----------------------------------------------

smoke:
	@echo "=== Smoke Test ==="
	python -c "\
from incident_triage_env import IncidentTriageEnv, IncidentAction; \
env = IncidentTriageEnv(task='easy'); \
obs = env.reset(); \
print('reset() works:', obs.incident_id); \
obs, r, d, i = env.step(IncidentAction(action_type='check_topology')); \
print('step() works, reward:', r); \
obs, r, d, i = env.step(IncidentAction(action_type='diagnose', target_service='auth-service', fault_type='oom', remediation='restart')); \
print('diagnose works, score:', r, 'done:', d); \
print('state():', list(env.state().keys())); \
print('All smoke tests passed!')"

# --- Docker ---------------------------------------------------------

docker-build:
	docker build -f server/Dockerfile -t incident-triage-env .

docker-run:
	docker run -p 8000:8000 -e PORT=8000 incident-triage-env

docker-test: docker-build
	@echo "=== Docker Test ==="
	docker run -d --name ite-test -p 8000:8000 -e PORT=8000 incident-triage-env
	sleep 3
	curl -sf http://localhost:8000/ && echo " Health check passed" || echo " Health check failed"
	curl -sf -X POST http://localhost:8000/reset \
		-H "Content-Type: application/json" \
		-d '{"task":"easy"}' | python -m json.tool && echo " Reset works" || echo " Reset failed"
	docker stop ite-test && docker rm ite-test
	@echo "Docker test complete"

# --- Inference ------------------------------------------------------

inference:
	python inference.py

# Dry run without LLM (tests env + stdout format)
inference-dry:
	INFERENCE_DRY_RUN=1 python inference.py

# --- Validation -----------------------------------------------------

validate:
	@echo "=== Pre-submission Validation ==="
	@echo "1. Testing imports..."
	python -c "from incident_triage_env import IncidentTriageEnv, IncidentAction, IncidentObservation, IncidentReward"
	@echo "2. Testing all tasks..."
	python -c "\
from incident_triage_env import IncidentTriageEnv, IncidentAction; \
for task in ['easy', 'medium', 'hard']: \
    env = IncidentTriageEnv(task=task); \
    obs = env.reset(); \
    assert not obs.done; \
    assert len(obs.available_services) >= 3; \
    print(f'  {task}: {len(obs.available_services)} services')"
	@echo "3. Testing grader range..."
	python -c "\
from incident_triage_env.grader import grade_diagnosis; \
r = grade_diagnosis('wrong', 'wrong', 'wrong', {'service':'x','fault_type':'y','remediation':'z'}, []); \
assert 0.0 <= r['score'] <= 1.0; \
r = grade_diagnosis('x', 'y', 'z', {'service':'x','fault_type':'y','remediation':'z'}, ['x']); \
assert r['score'] == 1.0; \
print('  Grader range: 0.0-1.0, perfect score works')"
	@echo "4. Testing Docker build..."
	docker build -f server/Dockerfile -t incident-triage-env . > /dev/null 2>&1 && echo "  Docker builds" || echo "  Docker build failed"
	@echo "=== All validations passed ==="

# --- Clean ----------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	docker rmi incident-triage-env 2>/dev/null || true
