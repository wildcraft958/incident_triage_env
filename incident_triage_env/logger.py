"""
Episode logger for the Incident Triage environment.

Writes structured JSON traces to logs/episodes/ so you can replay,
debug, and analyze agent behaviour after the fact.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Standard Python logger -- handlers are configured by the server/CLI layer.
log = logging.getLogger("incident_triage")

_LOGS_DIR = Path(os.getenv("LOGS_DIR", "logs/episodes"))


def _ensure_dir() -> Path:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return _LOGS_DIR


class EpisodeLogger:
    """
    Logs one complete episode to a JSON file.

    Usage::

        with EpisodeLogger(session_id, task) as el:
            el.log_reset(observation)
            el.log_step(action, observation, reward, done)
            # ... more steps ...
        # File is written on __exit__
    """

    def __init__(self, session_id: str, task: str) -> None:
        self.session_id = session_id
        self.task = task
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._steps: list[dict[str, Any]] = []
        self._reset_obs: dict = {}
        self._final_score: float = 0.0
        self._total_reward: float = 0.0

    def __enter__(self) -> "EpisodeLogger":
        return self

    def __exit__(self, *_) -> None:
        self._flush()

    def log_reset(self, obs: Any) -> None:
        self._reset_obs = _obs_to_dict(obs)
        log.info(
            "episode_start session=%s task=%s scenario=%s",
            self.session_id,
            self.task,
            obs.incident_id,
        )

    def log_step(self, action: Any, obs: Any, reward: float, done: bool) -> None:
        step_num = len(self._steps) + 1
        self._total_reward += reward
        if done:
            self._final_score = obs.score
        entry = {
            "step": step_num,
            "action": _action_to_dict(action),
            "reward": reward,
            "done": done,
            "score": obs.score,
            "response_preview": obs.response[:120] if obs.response else "",
        }
        self._steps.append(entry)
        log.info(
            "step session=%s step=%d action=%s reward=%.3f done=%s",
            self.session_id,
            step_num,
            action.action_type,
            reward,
            done,
        )

    def _flush(self) -> None:
        record = {
            "session_id": self.session_id,
            "task": self.task,
            "started_at": self._started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_steps": len(self._steps),
            "total_reward": round(self._total_reward, 4),
            "final_score": self._final_score,
            "initial_observation": self._reset_obs,
            "steps": self._steps,
        }
        try:
            path = _ensure_dir() / f"{self.session_id}.json"
            path.write_text(json.dumps(record, indent=2))
            log.info(
                "episode_end session=%s score=%.3f steps=%d file=%s",
                self.session_id,
                self._final_score,
                len(self._steps),
                path,
            )
        except OSError as e:
            log.warning("could not write episode log: %s", e)


def _obs_to_dict(obs: Any) -> dict:
    try:
        return obs.model_dump()
    except AttributeError:
        return {"summary": str(obs)}


def _action_to_dict(action: Any) -> dict:
    try:
        return {k: v for k, v in action.model_dump().items() if v is not None}
    except AttributeError:
        return {"raw": str(action)}
