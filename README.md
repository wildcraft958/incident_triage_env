# Incident Triage Environment

An RL environment for benchmarking AI agents on SRE incident investigation tasks.
Built for the OpenEnv Hackathon (Scaler + HuggingFace + Meta).

## What This Is

This environment simulates real-world SRE incident triage. An agent investigates
microservice failures by querying logs, metrics, topology, traces, and alerts,
then submits a root-cause diagnosis. We grade it.

Scenarios are modeled on documented production outages:
- Meta 2021 BGP outage (6-hour global outage)
- AWS us-east-1 December 2021 (Kinesis/CloudWatch cascade)
- CrowdStrike July 2024 (bad config push, 8.5M machines)
- GitHub Actions DB connection exhaustion (2023-2024)
- ML pipeline staleness (Kafka disk full -> stale predictions)

## Quick Start

```bash
pip install -r requirements.txt
pip install pytest httpx

# Run all tests
make test

# Smoke test
make smoke

# Run inference (dry mode, no LLM needed)
make inference-dry
```

## API

```bash
# Start server
uvicorn app:app --host 0.0.0.0 --port 7860

# Reset environment
curl -X POST http://localhost:7860/reset -d '{"task":"easy"}' -H "Content-Type: application/json"

# Take a step
curl -X POST http://localhost:7860/step \
  -d '{"session_id":"<sid>","action":{"action_type":"check_topology"}}' \
  -H "Content-Type: application/json"
```

## Tasks

| Task | Services | Causal Chain | Description |
|------|----------|-------------|-------------|
| easy | 3-4 | 1-2 | Single service OOM or disk-full. Clear error signals. |
| medium | 4-6 | 2-4 | Cascading failure (connection leak, bad config push). |
| hard | 6-8 | 4-5 | Subtle degradation. No application errors. Temporal reasoning required. |

## Action Space

- `query_logs(service)` - Get recent log lines from a service
- `query_metrics(service)` - Get current metrics (CPU, memory, latency, error rate)
- `check_topology()` - View the service dependency graph
- `trace_request(service)` - Follow a request through the service mesh
- `check_alerts()` - View active alerts and history
- `diagnose(service, fault_type, remediation)` - Submit final answer

## Scoring

| Component | Weight |
|-----------|--------|
| Correct root-cause service | 0.40 |
| Correct fault type | 0.35 |
| Correct remediation | 0.25 |
| Partial credit (in causal chain) | 0.15 |
| Efficiency bonus (<=50% of max steps) | +0.05 |

## Docker

```bash
docker build -t incident-triage-env .
docker run -p 7860:7860 incident-triage-env
```

## Running the Baseline Agent

```bash
export HF_TOKEN=hf_your_token
bash scripts/run_baseline.sh
```

## Real-World Data Sources

- LogHub (github.com/logpai/loghub) - Real log templates from 16 distributed systems
- Dan Luu's post-mortems (github.com/danluu/post-mortems) - 200+ real incident reports
- Meta 2021 outage post-mortem
- AWS 2021 us-east-1 summary
- CrowdStrike 2024 preliminary post-incident report
