"""Chaos evaluator -- stress-tests the LLM agent against hard procedural scenarios.

Runs N concurrent episodes of the hard task and aggregates failure telemetry:
- Loop defect rate (agent repeats same action >3 times)
- Evidence hallucination (agent cites data never returned by environment)
- Context saturation (malformed JSON after step 10)
- Blind guessing rate (diagnose before step 3 on hard)

Usage:
    # With real LLM (respects rate limits):
    python scripts/chaos_evaluator.py

    # Dry-run mode (no LLM, tests env + telemetry pipeline):
    INFERENCE_DRY_RUN=1 python scripts/chaos_evaluator.py

    # Custom concurrency:
    CHAOS_EPISODES=10 python scripts/chaos_evaluator.py
"""

import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incident_triage_env.env import IncidentTriageEnv
from models import IncidentAction

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3.5-27B")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY") or ""
DRY_RUN = os.getenv("INFERENCE_DRY_RUN", "0") == "1"
NUM_EPISODES = int(os.getenv("CHAOS_EPISODES", "20"))
MAX_RETRIES = 5

SYSTEM_PROMPT = """You are an expert SRE investigating a production incident.
You have access to these actions (respond with JSON only):
- {"action_type": "query_logs", "target_service": "<name>"}
- {"action_type": "query_metrics", "target_service": "<name>"}
- {"action_type": "check_topology"}
- {"action_type": "trace_request", "target_service": "<name>"}
- {"action_type": "check_alerts"}
- {"action_type": "diagnose", "target_service": "<name>", "fault_type": "<type>", "remediation": "<fix>", "hypothesis_evidence": "<cite specific log lines or metric values>"}

Valid fault types: oom, cpu_saturated, connection_leak, disk_full, config_error, network_partition, dependency_timeout, certificate_expired, memory_leak, thread_deadlock, dns_failure
Valid remediations: restart, scale_up, fix_config, clear_disk, rollback, failover, increase_pool, renew_certificate, kill_threads, flush_dns, update_routes, resize_volume

IMPORTANT: This environment simulates cascading failures that evolve over time.
Metrics degrade progressively. A service that looks healthy early may show critical failures later.
Check topology first, then follow the dependency chain toward infrastructure.
Include hypothesis_evidence citing specific log lines or metric values.
Respond with ONLY valid JSON, no explanation."""

KNOWN_FIELDS = {"action_type", "target_service", "fault_type", "remediation", "hypothesis_evidence"}


@dataclass
class EpisodeTelemetry:
    episode_id: int = 0
    scenario_id: str = ""
    score: float = 0.0
    steps: int = 0
    success: bool = False
    actions: list[str] = field(default_factory=list)
    responses: list[str] = field(default_factory=list)
    hypothesis_evidence: str = ""
    loop_defects: int = 0
    evidence_hallucinated: bool = False
    hallucination_details: str = ""
    context_saturation: bool = False
    context_saturation_step: int = 0
    blind_guess: bool = False
    blind_guess_step: int = 0
    parse_errors: int = 0
    parse_errors_after_step_10: int = 0
    error: str = ""


def call_llm_with_backoff(client: OpenAI, messages: list[dict]) -> str:
    """Call LLM with exponential backoff for rate limits."""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.0,
                max_tokens=256,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            err = str(exc)
            if "429" in err or "402" in err or "rate" in err.lower():
                wait = 2 ** attempt + 1
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} retries")


def parse_action(raw: str) -> IncidentAction | None:
    """Parse LLM output into IncidentAction."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    data = json.loads(raw)
    filtered = {k: v for k, v in data.items() if k in KNOWN_FIELDS}
    return IncidentAction(**filtered)


def dry_run_action(step: int, services: list[str], root_cause: dict) -> IncidentAction:
    """Heuristic action sequence for dry-run mode."""
    if step == 0:
        return IncidentAction(action_type="check_topology")
    if step == 1:
        return IncidentAction(action_type="check_alerts")
    if step == 2:
        return IncidentAction(action_type="query_logs", target_service=services[0])
    if step == 3:
        return IncidentAction(action_type="query_metrics", target_service=services[0])
    if step == 4 and len(services) > 1:
        return IncidentAction(action_type="query_logs", target_service=services[1])
    if step == 5 and len(services) > 2:
        return IncidentAction(action_type="query_metrics", target_service=services[2])
    # Diagnose with evidence
    return IncidentAction(
        action_type="diagnose",
        target_service=root_cause["service"],
        fault_type=root_cause["fault_type"],
        remediation=root_cause["remediation"],
        hypothesis_evidence=f"{root_cause['service']} error_rate at 95%, logs show {root_cause['fault_type']}",
    )


def detect_loop_defects(actions: list[str]) -> int:
    """Count actions repeated more than 3 times."""
    counts = Counter(actions)
    return sum(1 for a, c in counts.items() if c > 3)


def detect_evidence_hallucination(evidence: str, responses: list[str]) -> tuple[bool, str]:
    """Check if hypothesis_evidence cites data never seen in env responses."""
    if not evidence:
        return False, ""

    # Extract numbers from evidence
    evidence_numbers = set(re.findall(r"\d+\.?\d*", evidence))
    # Extract numbers from all env responses
    response_text = " ".join(responses)
    response_numbers = set(re.findall(r"\d+\.?\d*", response_text))

    # Look for numbers in evidence not present in any response
    # Filter out very common numbers (0, 1, 2, 100, etc.)
    common = {"0", "1", "2", "3", "4", "5", "10", "100", "200", "500"}
    evidence_specific = evidence_numbers - common
    if not evidence_specific:
        return False, ""

    hallucinated = evidence_specific - response_numbers
    if hallucinated and len(hallucinated) > len(evidence_specific) * 0.5:
        return True, f"Cited numbers not in env responses: {hallucinated}"
    return False, ""


def run_episode(episode_id: int, client: OpenAI | None) -> EpisodeTelemetry:
    """Run a single hard episode and collect telemetry."""
    tel = EpisodeTelemetry(episode_id=episode_id)

    try:
        env = IncidentTriageEnv(task="hard")
        obs = env.reset()
        tel.scenario_id = obs.incident_id

        messages = []
        if not DRY_RUN:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Incident: {obs.summary}\nAvailable services: {', '.join(obs.available_services)}"},
            ]

        step = 0
        while not obs.done and step < 15:
            action = None
            error_val = None

            if DRY_RUN:
                action = dry_run_action(step, obs.available_services, env.scenario["root_cause"])
            else:
                try:
                    raw = call_llm_with_backoff(client, messages)
                    action = parse_action(raw)
                except Exception as exc:
                    tel.parse_errors += 1
                    if step >= 10:
                        tel.parse_errors_after_step_10 += 1
                    error_val = str(exc)
                    messages.append({"role": "user", "content": f"Invalid JSON. Error: {error_val}. Respond with ONLY valid JSON."})
                    step += 1
                    continue

            # Track action
            action_str = f"{action.action_type}({action.target_service or ''})"
            tel.actions.append(action_str)

            # Detect blind guessing
            if action.action_type == "diagnose" and step < 3:
                tel.blind_guess = True
                tel.blind_guess_step = step

            # Execute step
            obs, reward, done, info = env.step(action)
            tel.responses.append(obs.response[:500])
            step += 1

            # Track evidence
            if action.action_type == "diagnose" and action.hypothesis_evidence:
                tel.hypothesis_evidence = action.hypothesis_evidence

            if not DRY_RUN and not done:
                messages.append({"role": "assistant", "content": json.dumps(action.model_dump(exclude_none=True, exclude={"metadata"}))})
                messages.append({"role": "user", "content": obs.response if obs.response else "No additional information."})

        tel.score = env.score
        tel.steps = step
        tel.success = env.score > 0.0

        # Post-episode analysis
        tel.loop_defects = detect_loop_defects(tel.actions)
        if tel.hypothesis_evidence:
            tel.evidence_hallucinated, tel.hallucination_details = detect_evidence_hallucination(
                tel.hypothesis_evidence, tel.responses
            )
        if tel.parse_errors_after_step_10 >= 2:
            tel.context_saturation = True
            tel.context_saturation_step = 10

    except Exception as exc:
        tel.error = str(exc)

    return tel


def main():
    print(f"=== Chaos Evaluator ===")
    print(f"Episodes: {NUM_EPISODES}")
    print(f"Task: hard")
    print(f"Model: {MODEL_NAME}")
    print(f"Dry run: {DRY_RUN}")
    print()

    client = None
    if not DRY_RUN:
        client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY or "dummy")

    results: list[EpisodeTelemetry] = []
    workers = min(NUM_EPISODES, 4) if not DRY_RUN else NUM_EPISODES

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_episode, i, client): i for i in range(NUM_EPISODES)}
        for future in as_completed(futures):
            eid = futures[future]
            tel = future.result()
            results.append(tel)
            status = "OK" if tel.score > 0.2 else "FAIL"
            flags = []
            if tel.loop_defects > 0:
                flags.append(f"loops={tel.loop_defects}")
            if tel.evidence_hallucinated:
                flags.append("hallucination")
            if tel.context_saturation:
                flags.append("ctx_saturated")
            if tel.blind_guess:
                flags.append(f"blind@step{tel.blind_guess_step}")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  [{status}] Episode {eid:2d}: score={tel.score:.3f} steps={tel.steps:2d} scenario={tel.scenario_id}{flag_str}")

    # Aggregate
    scores = [r.score for r in results]
    wins = sum(1 for s in scores if s > 0.2)
    catastrophic = [r for r in results if r.score < 0.2]
    loop_episodes = sum(1 for r in results if r.loop_defects > 0)
    hallucination_episodes = sum(1 for r in results if r.evidence_hallucinated)
    ctx_saturated = sum(1 for r in results if r.context_saturation)
    blind_guesses = sum(1 for r in results if r.blind_guess)
    total_parse_errors = sum(r.parse_errors for r in results)

    report = {
        "config": {
            "episodes": NUM_EPISODES,
            "task": "hard",
            "model": MODEL_NAME,
            "dry_run": DRY_RUN,
        },
        "summary": {
            "win_rate": round(wins / NUM_EPISODES, 3),
            "avg_score": round(sum(scores) / len(scores), 3) if scores else 0,
            "avg_steps": round(sum(r.steps for r in results) / len(results), 1) if results else 0,
            "min_score": round(min(scores), 3) if scores else 0,
            "max_score": round(max(scores), 3) if scores else 0,
        },
        "defects": {
            "loop_defect_rate": round(loop_episodes / NUM_EPISODES, 3),
            "evidence_hallucination_rate": round(hallucination_episodes / NUM_EPISODES, 3),
            "context_saturation_rate": round(ctx_saturated / NUM_EPISODES, 3),
            "blind_guess_rate": round(blind_guesses / NUM_EPISODES, 3),
            "total_parse_errors": total_parse_errors,
        },
        "catastrophic_failures": [
            {"episode": r.episode_id, "scenario_id": r.scenario_id, "score": r.score, "error": r.error}
            for r in catastrophic
        ],
        "hallucination_details": [
            {"episode": r.episode_id, "scenario_id": r.scenario_id, "details": r.hallucination_details}
            for r in results if r.evidence_hallucinated
        ],
    }

    print()
    print("=== CHAOS REPORT ===")
    print(f"Win rate:                {report['summary']['win_rate']}")
    print(f"Avg score:               {report['summary']['avg_score']}")
    print(f"Avg steps:               {report['summary']['avg_steps']}")
    print(f"Score range:             {report['summary']['min_score']} - {report['summary']['max_score']}")
    print(f"Loop defect rate:        {report['defects']['loop_defect_rate']}")
    print(f"Hallucination rate:      {report['defects']['evidence_hallucination_rate']}")
    print(f"Context saturation rate: {report['defects']['context_saturation_rate']}")
    print(f"Blind guess rate:        {report['defects']['blind_guess_rate']}")
    print(f"Total parse errors:      {report['defects']['total_parse_errors']}")
    print(f"Catastrophic failures:   {len(catastrophic)}")

    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "chaos_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
