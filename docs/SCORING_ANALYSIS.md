# Scoring Analysis -- How We Maximize Competition Points

## Competition Scoring vs Our Design Decisions

### Real-World Utility (30 points)

**Target: 26-30 points**

Our claims:
- SRE incident triage is performed by every tech company with >50 engineers
- Companies (PagerDuty AI, incident.io, Observe) are commercially building this
- Meta's own SRE teams do this daily on one of world's largest distributed systems
- Our scenarios are modeled on REAL post-mortems (Meta 2021, AWS 2021, CrowdStrike 2024)
- The gap this fills: no existing RL environment for SRE incident investigation

Evidence in README:
- Link to Meta 2021 post-mortem blog -> "This is the type of incident we simulate"
- Link to PagerDuty AI SRE -> "This is the product space our env benchmarks"
- Cite LogHub dataset -> "Our logs follow real-world patterns"

### Task & Grader Quality (25 points)

**Target: 20-25 points**

Checklist:
- [x] 3+ tasks: easy, medium, hard
- [x] Difficulty range: single service -> cascade -> subtle degradation
- [x] Scores between 0.0 and 1.0
- [x] Deterministic: same action sequence -> same scores always
- [x] Hard task challenges frontier: no error signals, 5-service chain
- [x] Partial credit exists: causal chain membership
- [x] Multiple scenarios per difficulty

### Environment Design (20 points)

**Target: 16-20 points**

Checklist:
- [x] reset() produces clean state
- [x] 6 action types (more than minimum)
- [x] Typed observation/action models
- [x] Reward shaping throughout episode (not just terminal)
- [x] Episode boundaries sensible (max_steps or diagnose)
- [x] Penalties for bad behavior (repeated queries, invalid actions)
- [x] Efficiency bonus for fast correct diagnosis

### Code Quality (15 points)

**Target: 12-15 points**

Checklist:
- [x] openenv validate passes
- [x] Docker builds and runs
- [x] HF Space deploys
- [x] Baseline script reproduces
- [x] Full type hints
- [x] Docstrings on all public APIs
- [x] Clean project structure
- [x] Tests exist and pass

### Creativity (10 points)

**Target: 7-10 points**

Novel elements:
- Domain: SRE incident triage (not in any existing OpenEnv)
- trace_request and check_alerts actions (beyond basic query_logs/metrics)
- Scenarios based on REAL documented outages, not fabricated
- Hard scenario with zero error signals (quality degradation, not crash)
- Efficiency bonus in reward design
- Red herrings in scenarios
- Multiple scenarios per difficulty level

## Expected Scores by Agent Quality

| Agent Behavior | Easy Score | Medium Score | Hard Score |
|---------------|-----------|-------------|-----------|
| Random actions, random diagnosis | 0.05-0.15 | 0.05-0.10 | 0.02-0.08 |
| Queries all services, guesses randomly | 0.15-0.30 | 0.10-0.20 | 0.05-0.15 |
| Reads logs, finds obvious errors | 0.75-1.00 | 0.15-0.40 | 0.05-0.15 |
| Follows causal chain, good reasoning | 0.90-1.00 | 0.60-0.85 | 0.30-0.60 |
| Expert-level multi-step reasoning | 1.00 | 0.85-1.00 | 0.60-1.00 |

This distribution shows CLEAR differentiation -- exactly what judges want.
