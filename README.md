---
title: Incident Triage Environment
emoji: 🚨
colorFrom: red
colorTo: blue
sdk: docker
pinned: false
base_path: /web
---

# Incident Triage Environment

An RL environment where AI agents learn to diagnose production incidents across microservices.
Built for the OpenEnv Hackathon (Scaler + HuggingFace + Meta).

## Why This Exists

Every engineering team running microservices deals with production incidents. An SRE gets paged
at 3am, opens dashboards, queries logs, checks which services depend on which, and tries to find
the root cause before the outage gets worse. This is a high-stakes reasoning task that happens
thousands of times a day across the industry -- and no RL environment exists to train or evaluate
agents on it.

This environment changes that. Scenarios are built from documented real-world outages:
- Meta 2021 BGP outage (6-hour global outage, all monitoring also blind)
- AWS us-east-1 December 2021 (Kinesis fails, takes CloudWatch with it)
- CrowdStrike July 2024 (bad config push crashes 8.5M machines simultaneously)
- GitHub Actions DB connection exhaustion (gradual leak, downstream cascade)
- ML pipeline staleness (Kafka disk full, predictions degrade silently for hours)

## Setup

```bash
pip install openenv-core
pip install -r requirements.txt

# Verify everything works
openenv validate
python -m pytest tests/ -v
```

## Running Locally

```bash
# Start server (recommended)
uv run server

# Or with uvicorn directly
uvicorn server.app:app --host 0.0.0.0 --port 7860

# Dry-run inference (no LLM needed)
INFERENCE_DRY_RUN=1 python inference.py
```

## Docker

```bash
docker build -t incident-triage-env .
docker run -p 7860:7860 incident-triage-env
```

## Deploy to HuggingFace

```bash
openenv push --repo-id your-username/incident-triage-env
```

## API

```bash
# Health check
curl http://localhost:7860/

# Start episode
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task": "easy"}'

# Take a step
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<sid>", "action": {"action_type": "check_topology"}}'

# Get state
curl -X POST http://localhost:7860/state \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<sid>"}'
```

## Tasks

| Task | Services | Causal Chain Depth | What makes it hard |
|------|----------|-------------------|-------------------|
| easy | 3-4 | 1-2 | Single service OOM or disk-full. Logs point directly at fault. |
| medium | 4-6 | 2-4 | Cascading failure (connection leak, simultaneous config crash). Requires correlating timestamps. |
| hard | 6-8 | 4-5 | Zero application-layer errors. Business metric degrades silently. Temporal reasoning required. |

## Action Space

| Action | Parameters | Reward |
|--------|-----------|--------|
| `query_logs(service)` | `target_service: str` | +0.05 if service in causal chain (first time) |
| `query_metrics(service)` | `target_service: str` | +0.03 if service in causal chain (first time) |
| `check_topology()` | none | +0.02 (first time) |
| `trace_request(service)` | `target_service: str` (optional) | +0.04 if service in causal chain (first time) |
| `check_alerts()` | none | +0.03 (first time) |
| `diagnose(service, fault_type, remediation)` | all required | see scoring below |

Repeated identical queries return `-0.01`. Invalid actions return `-0.02`.

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `incident_id` | string | Unique scenario identifier |
| `summary` | string | The alert text the on-call SRE received |
| `available_services` | list[string] | Services you can query |
| `available_actions` | list[string] | Full action list with signatures |
| `response` | string | Result of the last action (or action guide on reset) |
| `step` | int | Current step number |
| `done` | bool | Whether the episode has ended |
| `score` | float | Final diagnosis score (0.0-1.0), non-zero only after diagnose |

## Scoring

| Component | Points |
|-----------|--------|
| Correct root-cause service | 0.40 |
| Service in causal chain (partial) | 0.15 |
| Correct fault type | 0.35 |
| Correct remediation | 0.25 |
| Efficiency bonus (diagnosed in <= 50% of max steps) | +0.05 |

Valid fault types: `oom`, `cpu_saturated`, `connection_leak`, `disk_full`, `config_error`,
`network_partition`, `dependency_timeout`, `certificate_expired`, `memory_leak`,
`thread_deadlock`, `dns_failure`

Valid remediations: `restart`, `scale_up`, `fix_config`, `clear_disk`, `rollback`,
`failover`, `increase_pool`, `renew_certificate`, `kill_threads`, `flush_dns`,
`update_routes`, `resize_volume`

## Baseline Results

Results from running `Qwen/Qwen3.5-27B` via HuggingFace router:

| Task | Score | Steps |
|------|-------|-------|
| easy | TBD | TBD |
| medium | TBD | TBD |
| hard | TBD | TBD |

Run your own baseline:

```bash
export HF_TOKEN=hf_your_token
bash scripts/run_baseline.sh
```

## Running Inference

```bash
export API_BASE_URL=https://router.huggingface.co/v1
export MODEL_NAME=Qwen/Qwen3.5-27B
export HF_TOKEN=hf_your_token
python inference.py
```

## Real-World Sources

- LogHub (github.com/logpai/loghub) - real log templates from 16 distributed systems
- Dan Luu post-mortems (github.com/danluu/post-mortems) - 200+ real incident reports
- Meta 2021 BGP outage: engineering.fb.com/2021/10/05/networking-traffic/outage-details/
- AWS 2021 us-east-1: aws.amazon.com/message/12721/
- CrowdStrike 2024: crowdstrike.com/blog/falcon-content-update-preliminary-post-incident-report/
