"""Baseline LLM agent that runs against IncidentTriageEnv for all three tasks."""

import json
import os
import sys
from typing import Any

from openai import OpenAI

from incident_triage_env.env import IncidentTriageEnv
from models import IncidentAction

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3.5-27B")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY") or ""
DRY_RUN = os.getenv("INFERENCE_DRY_RUN", "0") == "1"

SYSTEM_PROMPT = """You are an expert SRE investigating a production incident.
You have access to these actions (respond with JSON only):
- {"action_type": "query_logs", "target_service": "<name>"}
- {"action_type": "query_metrics", "target_service": "<name>"}
- {"action_type": "check_topology"}
- {"action_type": "trace_request", "target_service": "<name>"}
- {"action_type": "check_alerts"}
- {"action_type": "diagnose", "target_service": "<name>", "fault_type": "<type>", "remediation": "<fix>"}

Valid fault types: oom, cpu_saturated, connection_leak, disk_full, config_error, network_partition, dependency_timeout, certificate_expired, memory_leak, thread_deadlock, dns_failure
Valid remediations: restart, scale_up, fix_config, clear_disk, rollback, failover, increase_pool, renew_certificate, kill_threads, flush_dns, update_routes, resize_volume

Investigate methodically. Query logs and metrics of suspicious services before diagnosing.
When ready to diagnose, submit the diagnose action with your best assessment.
Respond with ONLY valid JSON, no explanation."""


def format_action_str(action: IncidentAction) -> str:
    """Format an action as the compact string used in [STEP] output."""
    atype = action.action_type
    if atype == "check_topology":
        return "check_topology()"
    if atype == "check_alerts":
        return "check_alerts()"
    if atype in ("query_logs", "query_metrics", "trace_request"):
        svc = action.target_service or ""
        return f"{atype}({svc})"
    if atype == "diagnose":
        svc = action.target_service or ""
        ft = action.fault_type or ""
        rem = action.remediation or ""
        return f"diagnose({svc},{ft},{rem})"
    return f"{atype}()"


def print_start(task: str, model: str) -> None:
    print(f"[START] task={task} env=incident_triage model={model}", flush=True)


def print_step(step: int, action: IncidentAction, reward: float, done: bool, error: Any) -> None:
    action_str = format_action_str(action)
    done_str = "true" if done else "false"
    error_str = str(error) if error else "null"
    print(
        f"[STEP] step={step} action={action_str} reward={reward:.2f} done={done_str} error={error_str}",
        flush=True,
    )


def print_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    success_str = "true" if success else "false"
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={success_str} steps={steps} score={score:.3f} rewards={rewards_str}", flush=True)


def dry_run_actions(obs: Any) -> list[IncidentAction]:
    """Fixed heuristic sequence used in dry-run mode."""
    services = obs.available_services
    first_service = services[0] if services else "unknown-service"
    return [
        IncidentAction(action_type="check_topology"),
        IncidentAction(action_type="query_logs", target_service=first_service),
        IncidentAction(
            action_type="diagnose",
            target_service=first_service,
            fault_type="disk_full",
            remediation="rollback",
        ),
    ]


def run_llm_action(client: OpenAI, messages: list[dict]) -> IncidentAction:
    """Call the LLM and parse its JSON response into an IncidentAction."""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.0,
        max_tokens=256,
    )
    raw = response.choices[0].message.content or ""
    raw = raw.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(raw)
    return IncidentAction(**data)


def run_episode(task: str) -> None:
    """Run one full episode for the given task difficulty."""
    env = IncidentTriageEnv(task=task)
    rewards: list[float] = []
    success = False
    steps = 0

    print_start(task, MODEL_NAME)

    client: OpenAI | None = None
    if not DRY_RUN:
        client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY or "dummy")

    try:
        obs = env.reset()

        if DRY_RUN:
            action_queue = dry_run_actions(obs)

        messages: list[dict] = []
        if not DRY_RUN:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Incident: {obs.summary}\n"
                        f"Available services: {', '.join(obs.available_services)}"
                    ),
                },
            ]

        dry_run_idx = 0

        while not obs.done:
            error_val = None
            action: IncidentAction | None = None

            if DRY_RUN:
                if dry_run_idx >= len(action_queue):
                    break
                action = action_queue[dry_run_idx]
                dry_run_idx += 1
            else:
                try:
                    action = run_llm_action(client, messages)
                except Exception as exc:
                    error_val = str(exc)
                    # Emit a malformed-action step so [STEP] is always printed
                    steps += 1
                    dummy = IncidentAction(action_type="__parse_error__")
                    rewards.append(-0.02)
                    print_step(steps, dummy, -0.02, False, error_val)
                    # Build a recovery prompt nudging the model back on track
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Your last response was not valid JSON. Error: {error_val}. Respond with ONLY valid JSON.",
                        }
                    )
                    continue

            obs, reward, done, info = env.step(action)
            steps += 1
            rewards.append(reward)
            error_val = info.get("error") if info else None
            print_step(steps, action, reward, done, error_val)

            if not DRY_RUN:
                # Add assistant turn (the action JSON) and next observation
                messages.append({"role": "assistant", "content": json.dumps(action.model_dump(exclude_none=True))})
                next_content = obs.response if obs.response else "No additional information."
                if done:
                    break
                messages.append({"role": "user", "content": next_content})

        success = env.score > 0.0
    except Exception as exc:
        error_val = str(exc)
        print(f"[ERROR] Unhandled exception: {error_val}", file=sys.stderr, flush=True)
    finally:
        final_score = env.score if env else 0.0
        env.close()
        print_end(success, steps, final_score, rewards)


def main() -> None:
    """Run all three task difficulties in order."""
    for task in ("easy", "medium", "hard"):
        run_episode(task)


if __name__ == "__main__":
    main()
