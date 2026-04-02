# Architecture Document

## System Design

```
+-------------------------------------------------------------+
|                    HuggingFace Space                         |
|                                                              |
|  +-----------------------------------------------------+    |
|  |                  FastAPI (app.py)                   |    |
|  |                                                     |    |
|  |  GET  /           -> health check (returns 200)     |    |
|  |  POST /reset      -> create session, load scenario  |    |
|  |  POST /step       -> process action, return obs+rwd |    |
|  |  POST /state      -> return full state              |    |
|  |  GET  /health     -> health status                  |    |
|  |  GET  /tasks      -> list available tasks           |    |
|  +-------------+---------------------------------------+    |
|                |                                            |
|  +-------------v---------------------------------------+    |
|  |           IncidentTriageEnv (env.py)                |    |
|  |                                                     |    |
|  |  State:                                             |    |
|  |    scenario (dict)         <- from scenarios.py     |    |
|  |    step_count (int)                                 |    |
|  |    done (bool)                                      |    |
|  |    score (float)                                    |    |
|  |    history (list[dict])                             |    |
|  |    queried_services (set)                           |    |
|  |    queried_actions (set)   <- track (action,svc)   |    |
|  |                                                     |    |
|  |  Handlers:                                          |    |
|  |    _do_query_logs(service)                          |    |
|  |    _do_query_metrics(service)                       |    |
|  |    _do_check_topology()                             |    |
|  |    _do_trace_request(service)                       |    |
|  |    _do_check_alerts()                               |    |
|  |    _do_diagnose(service, fault, remediation)        |    |
|  +-------------+---------------------------------------+    |
|                |                                            |
|  +-------------v---------------------------------------+    |
|  |         Scenario Data Layer                         |    |
|  |                                                     |    |
|  |  scenarios.py       <- Scenario definitions         |    |
|  |  real_incidents.py  <- Real incident mappings       |    |
|  |  log_templates.py   <- Realistic log generators     |    |
|  |  grader.py          <- Deterministic scoring        |    |
|  +-----------------------------------------------------+    |
|                                                             |
|  +-----------------------------------------------------+    |
|  |  Pydantic Models (models.py)                        |    |
|  |    IncidentAction   -- agent's input                |    |
|  |    IncidentObservation -- what agent sees           |    |
|  |    IncidentReward   -- score breakdown              |    |
|  +-----------------------------------------------------+    |
+-------------------------------------------------------------+

+-------------------------------------------------------------+
|                 inference.py (runs separately)              |
|                                                             |
|  Reads: API_BASE_URL, MODEL_NAME, HF_TOKEN                 |
|  Creates: OpenAI client                                     |
|  Loop:                                                      |
|    1. env.reset() -> observation                            |
|    2. Format observation into LLM prompt                    |
|    3. LLM returns JSON action                              |
|    4. Parse action -> IncidentAction                        |
|    5. env.step(action) -> obs, reward, done, info          |
|    6. Print [STEP] line                                     |
|    7. If not done, add obs to conversation, goto 3          |
|    8. Print [END] line                                      |
|  Repeat for each task: easy, medium, hard                   |
+-------------------------------------------------------------+
```

## State Machine

```
     +----------+
     |          |
     |  RESET   | <- reset(task) called
     |          |
     +----+-----+
          |
          v
     +----------+     step(action)     +----------+
     |          | ------------------> |          |
     | RUNNING  |                     | RUNNING  | (step_count < max_steps && no diagnose)
     |          | <------------------ |          |
     +----+-----+                     +----------+
          |
          | diagnose action OR max_steps reached
          v
     +----------+
     |          |
     |  DONE    | <- score computed, episode over
     |          |
     +----------+
```

## Scenario Selection Logic

```python
task="easy"    -> randomly pick from EASY_SCENARIOS pool  (or use scenario_index)
task="medium"  -> randomly pick from MEDIUM_SCENARIOS pool
task="hard"    -> randomly pick from HARD_SCENARIOS pool
```

Each pool has 2-3 scenarios for variety. The grading logic is the same
regardless of which specific scenario is loaded -- it always compares
agent's diagnosis against `scenario["root_cause"]`.
