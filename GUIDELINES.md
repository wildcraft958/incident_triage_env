# GUIDELINES.md — Development Rules & Standards

## CODE STANDARDS

### Python
- Python 3.11
- Type hints on ALL functions and method signatures
- Pydantic v2 for all data models
- Docstrings on all public classes and methods
- No global mutable state except in-memory session store in app.py
- All string literals for fault types, remediations, action types defined as constants/enums

### Naming
- Files: snake_case
- Classes: PascalCase
- Functions/methods: snake_case
- Constants: UPPER_SNAKE_CASE
- Scenario IDs: kebab-case (e.g., "easy-001", "medium-aws-kinesis")

### Imports
- Standard library first, then third-party, then local
- No star imports
- No unused imports

## MANDATORY STDOUT FORMAT FOR inference.py

This is the EXACT format. Any deviation = incorrect evaluation scoring.

```
[START] task=<task_name> env=<benchmark> model=<model_name>
[STEP] step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
[END] success=<true|false> steps=<n> rewards=<r1,r2,...,rn>
```

Rules:
- One [START] per episode
- One [STEP] per env.step() call, immediately after it returns
- One [END] after env.close(), ALWAYS emitted even on exception
- reward/rewards formatted to 2 decimal places
- done/success are lowercase: true or false
- error is raw string or null
- All fields on single line, no newlines within

Example:
```
[START] task=easy env=incident_triage model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action=check_topology() reward=0.02 done=false error=null
[STEP] step=2 action=query_logs(auth-service) reward=0.05 done=false error=null
[STEP] step=3 action=diagnose(auth-service,oom,restart) reward=1.00 done=true error=null
[END] success=true steps=3 rewards=0.02,0.05,1.00
```

## ENVIRONMENT VARIABLES (MANDATORY)

```bash
API_BASE_URL=https://router.huggingface.co/v1    # LLM endpoint
MODEL_NAME=Qwen/Qwen2.5-72B-Instruct             # Model identifier
HF_TOKEN=hf_xxxxx                                  # HuggingFace API key
```

inference.py MUST read these via os.getenv() with defaults for API_BASE_URL and MODEL_NAME.

## SCENARIO DESIGN RULES

### Every scenario MUST have:
```python
{
    "id": str,                    # e.g., "easy-meta-oom-001"
    "real_incident_ref": str,     # Real post-mortem this is based on
    "incident_summary": str,      # The alert the agent sees first
    "services": list[str],        # All services in the system
    "topology": dict,             # service -> [dependencies]
    "root_cause": {
        "service": str,           # The actual root cause service
        "fault_type": str,        # From VALID_FAULT_TYPES
        "remediation": str,       # From VALID_REMEDIATIONS
    },
    "causal_chain": list[str],    # Ordered: root -> ... -> symptom
    "logs": dict[str, list[str]], # service_name -> [log lines]
    "metrics": dict[str, dict],   # service_name -> {metric: value}
    "alerts": list[dict],         # Active alerts with timestamps
    "traces": dict,               # Sample request traces
}
```

### Log Line Format:
```
{timestamp} [{level}] {message}
```
Timestamps in ISO 8601: `2025-04-01T10:15:01Z`
Levels: DEBUG, INFO, WARN, ERROR, FATAL
Messages should look like real application logs -- stack traces, metric values, connection strings, query times.

### Valid Fault Types:
oom, cpu_saturated, connection_leak, disk_full, config_error,
network_partition, dependency_timeout, certificate_expired,
memory_leak, thread_deadlock, dns_failure

### Valid Remediations:
restart, scale_up, fix_config, clear_disk, rollback, failover,
increase_pool, renew_certificate, kill_threads, flush_dns,
update_routes, resize_volume

## GRADING RULES

1. Grading function MUST be pure -- same inputs -> same outputs ALWAYS
2. Score MUST be in [0.0, 1.0]
3. Partial credit MUST exist (not binary)
4. Different quality of play MUST produce meaningfully different scores
5. Easy task: competent agent scores 0.75+
6. Medium task: competent agent scores 0.40-0.75
7. Hard task: competent agent scores 0.15-0.50

## TESTING REQUIREMENTS

Before submission, ALL must pass:
- [ ] `python -m pytest tests/ -v` -- all green
- [ ] `docker build -t incident-triage-env .` -- succeeds
- [ ] `docker run -p 7860:7860 incident-triage-env` -- serves on 7860
- [ ] `curl localhost:7860/` -- returns 200
- [ ] `curl -X POST localhost:7860/reset -d '{"task":"easy"}'` -- returns observation
- [ ] `python inference.py` -- completes, produces [START]/[STEP]/[END] output
- [ ] `bash scripts/validate.sh https://your-space.hf.space` -- all checks pass
- [ ] Memory usage < 8GB during inference run
- [ ] Total inference.py runtime < 20 minutes for all 3 tasks

## REWARD DESIGN RULES

| Signal | Reward | Condition |
|--------|--------|-----------|
| Query logs of causal chain service | +0.05 | First time only |
| Query metrics of causal chain service | +0.03 | First time only |
| Check topology | +0.02 | First time only |
| Trace request through causal chain | +0.04 | First time only |
| Check alerts (reveals relevant alert) | +0.03 | First time only |
| Query irrelevant service (logs or metrics) | +0.00 | No penalty, no reward |
| Repeated query to same service (same action) | -0.01 | Discourage loops |
| Invalid/malformed action | -0.02 | Error handling |
| Diagnose: correct service | +0.40 | Or +0.15 if in causal chain |
| Diagnose: correct fault type | +0.35 | Exact match only |
| Diagnose: correct remediation | +0.25 | Exact match only |
| Max steps reached without diagnosis | 0.00 | Episode ends, score = 0 |
| Diagnose on step 1 (no investigation) | Apply score but no investigation bonus | Allowed but usually low |
| Efficiency bonus | +0.05 | If diagnosed correctly in <= 50% of max steps |

## DOCKER RULES

- Base image: python:3.11-slim
- Expose port 7860 (HuggingFace Spaces standard)
- No GPU required
- No external service dependencies (no real databases, no Redis, etc.)
- Everything runs in-memory with synthetic data
- Total image size should be < 500MB

## GIT WORKFLOW

- Main branch = submission-ready at all times
- Test before every commit
- Never commit .env files or API keys
- Tag final submission: `git tag v1.0-submission`
