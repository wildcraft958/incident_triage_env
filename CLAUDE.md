# CLAUDE.md — Project Context for Claude Code

## WORKFLOW

- TDD: write tests first, then implement.
- Do not use Plan or Explore agents. Read files directly and create plans yourself.
- When executing a plan, always create a task list to track progress.
- All projects must be git repositories.

## AUTHOR

Animesh Raj <animeshraj958@gmail.com>

## CODE STYLE

- Clean, readable code. Let the code speak for itself.
- Only add comments for architectural decisions or non-standard implementations. No restating what the code does.
- Match surrounding code conventions (naming, spacing, structure).

## GIT

- Commit after every change. Clean, to-the-point commit messages.
- Pull before starting any work.
- Push only after major changes and explicit approval.
- Never add Claude as co-author.
- Only use git add for modified files.
- Never stage or commit .claude, CLAUDE.md, or personal files (e.g. phase-1.md).
- Do not modify .gitignore unless asked.

## WRITING

- Write like a human. No em dashes or en dashes. No jargon.
- MR/PR descriptions: concise, plain language, checklist for remaining work.
- Get review on MR material before creating it.

---

## WHAT IS THIS PROJECT

This is a competition submission for the OpenEnv Hackathon (Scaler + HuggingFace + Meta).
We are building an RL environment (NOT an AI agent) that simulates SRE incident triage
across microservices. An AI agent plugs into our environment, investigates incidents by
querying logs/metrics/topology, and submits a root-cause diagnosis. We grade it.

We are building the TRAINING GROUND, not the player.

## COMPETITION REQUIREMENTS (NON-NEGOTIABLE)

### Instant Disqualification If:
- HF Space doesn't return 200 on GET /
- reset() doesn't return valid observation
- Docker doesn't build
- Fewer than 3 tasks
- Graders return same score always
- inference.py doesn't run or produce scores
- openenv validate fails

### Scoring Weights:
- Real-world utility: 30% -- MOST IMPORTANT
- Task & grader quality: 25%
- Environment design: 20%
- Code quality & spec compliance: 15%
- Creativity & novelty: 10%

### Hard Constraints:
- Runtime of inference.py < 20 minutes
- Must run on 2 vCPU, 8 GB RAM
- inference.py must use OpenAI client with env vars: API_BASE_URL, MODEL_NAME, HF_TOKEN
- stdout MUST follow exact format: [START], [STEP], [END] (see GUIDELINES.md)
- Dockerfile must work with `docker build && docker run`
- Must deploy to HuggingFace Spaces

## ARCHITECTURE

```
Agent (inference.py)
  |
  |  Uses OpenAI client to call LLM
  |  LLM returns JSON action
  |
  v
IncidentTriageEnv (env.py)
  |
  +-- reset(task="easy|medium|hard") -> Observation
  |     Loads scenario from scenarios.py + real_incidents.py
  |     Returns incident summary + available services
  |
  +-- step(action) -> (Observation, reward, done, info)
  |     action_type: query_logs | query_metrics | check_topology |
  |                  trace_request | check_alerts | diagnose
  |
  |     Dispatches to handler, returns realistic response
  |     Gives partial reward for investigating causal chain services
  |
  +-- state() -> full current state dict
  |
  +-- close() -> cleanup
```

## KEY DESIGN DECISIONS

### Why These Specific Actions:
Real SREs use exactly these investigation steps:
1. `query_logs` -- First thing any SRE does: check error logs
2. `query_metrics` -- Then check dashboards: CPU, memory, latency, error rates
3. `check_topology` -- Understand which services depend on which
4. `trace_request` -- Follow a specific request through the service mesh (NEW - adds realism)
5. `check_alerts` -- Review active alerts and their history (NEW - adds realism)
6. `diagnose` -- Submit final answer: root_cause_service + fault_type + remediation

### Why These Scenarios Are Based on Real Incidents:
- Easy scenarios modeled after: common single-service crashes (OOM, disk full)
- Medium scenarios modeled after: GitHub Actions DB connection leak, Google Cloud cascading config errors
- Hard scenarios modeled after: Meta 2021 BGP outage (adapted), CrowdStrike 2024 silent propagation, real ML pipeline staleness

### Grading Logic:
- root cause service correct: +0.40 (partial +0.15 if in causal chain)
- fault type correct: +0.35
- remediation correct: +0.25
- Investigation rewards: +0.03 to +0.05 per relevant service queried
- Penalties: -0.02 for invalid actions, -0.05 for repeated identical queries

## FILE RESPONSIBILITIES

| File | What It Does | Key Concern |
|------|-------------|-------------|
| `models.py` | Pydantic models for Action, Observation, Reward | Must be fully typed, all fields documented |
| `scenarios.py` | Scenario definitions with logs, metrics, topology, ground truth | Must feel REAL -- use log_templates.py and real_incidents.py |
| `real_incidents.py` | Maps real-world post-mortems to scenario structures | Source of truth for realistic incident patterns |
| `log_templates.py` | Realistic log line generators based on LogHub patterns | Timestamps, service names, actual error messages |
| `grader.py` | Deterministic scoring function | MUST be deterministic, range 0.0-1.0, partial credit |
| `env.py` | Main environment with reset/step/state | Clean state management, proper episode boundaries |
| `app.py` | FastAPI HTTP wrapper | Session management, proper error handling |
| `inference.py` | Baseline LLM agent | EXACT stdout format, uses OpenAI client, env vars |
| `openenv.yaml` | Metadata | Task list, action/observation space schemas |

## WHAT MAKES US WIN

1. Real incidents: Our scenarios aren't made up. They're modeled on Meta, AWS, GitHub, CrowdStrike post-mortems.
2. Realistic logs: Not "Error in service X". Actual log lines with timestamps, thread IDs, stack traces, metric values.
3. 6 actions not 4: We added trace_request and check_alerts -- what real SREs actually use.
4. Hard scenario genuinely hard: No error signals anywhere. 5-service causal chain. Temporal reasoning required.
5. Multiple scenarios per difficulty: Not just 1 easy scenario. Multiple variants for richer evaluation.
6. Reward shaping throughout: Investigation rewards, efficiency bonuses, penalties for redundancy.

## TESTING STRATEGY

Before ANY commit, run:
```bash
make test          # All unit tests pass
make docker-test   # Docker builds and serves
make validate      # Pre-submission validator
make inference-dry # Inference script runs (dry mode without LLM)
```

## COMMON MISTAKES TO AVOID

- Don't make the easy task too hard -- baseline agents MUST score 0.7+ on easy
- Don't make the hard task too easy -- frontier models should score <0.5
- Don't forget to handle: episode already done, unknown service name, missing fields in action
- Don't use any external API calls in the environment itself -- it's a simulator
- Don't exceed 8GB memory -- scenarios are dicts/strings, keep it lean
- inference.py MUST work with Qwen/Qwen2.5-72B-Instruct on HF router endpoint
- [STEP] lines must have EXACTLY the format shown -- field names, ordering, everything matters

## REAL-WORLD DATA SOURCES

1. LogHub -- github.com/logpai/loghub -- Real log templates from 16 distributed systems
2. Dan Luu's post-mortems -- github.com/danluu/post-mortems -- 200+ real incident reports
3. Meta 2021 Outage -- engineering.fb.com/2021/10/05/networking-traffic/outage-details/
4. AWS 2021 us-east-1 -- aws.amazon.com/message/12721/
5. CrowdStrike 2024 -- crowdstrike.com/blog/falcon-content-update-preliminary-post-incident-report/
6. Google 2019 Network -- status.cloud.google.com/incident/cloud-networking/19009
7. GitHub status history -- githubstatus.com/history
8. Cloudflare 2022 BGP -- blog.cloudflare.com/cloudflare-outage-on-june-21-2022/
9. Google SRE Book -- sre.google/books
10. PagerDuty Response Guide -- response.pagerduty.com
