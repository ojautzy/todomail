"""Gestion du state.json persistant pour le plugin TodoMail.

state.json vit dans ${CLAUDE_PLUGIN_DATA}/state.json avec fallback
vers {plugin_root}/.plugin-data/state.json si la variable
d'environnement n'est pas definie.
"""

import json
import os
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2

_DEFAULT_STATE = {
    "schema_version": SCHEMA_VERSION,
    "session_id": None,
    "current_phase": None,
    "started_at": None,
    "last_update_at": None,
    "active_lock": None,
    "counters": {},
    "checkpoints": [],
    "errors": [],
    "error_mode": "lenient",
}


def _state_dir() -> Path:
    """Resolve the directory for state.json."""
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / ".plugin-data"


def _state_path() -> Path:
    return _state_dir() / "state.json"


def _generate_session_id() -> str:
    now = datetime.now(timezone.utc)
    suffix = secrets.token_hex(3)
    return now.strftime("%Y%m%d-%H%M%S") + "-" + suffix


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    """Load state.json, creating it with defaults if absent."""
    path = _state_path()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    state = deepcopy(_DEFAULT_STATE)
    state["session_id"] = _generate_session_id()
    state["started_at"] = _now_iso()
    state["last_update_at"] = _now_iso()
    save_state(state)
    return state


def save_state(state: dict) -> None:
    """Atomic write of state dict to state.json."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    state["last_update_at"] = _now_iso()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp), str(path))


def update_checkpoint(phase: str, status: str, payload: dict[str, Any] | None = None) -> None:
    """Append a checkpoint entry to state.checkpoints[]."""
    state = load_state()
    entry: dict[str, Any] = {
        "phase": phase,
        "status": status,
        "at": _now_iso(),
    }
    if payload:
        entry["payload"] = payload
    state["checkpoints"].append(entry)
    state["current_phase"] = phase
    save_state(state)


def record_error(mail_id: str, phase: str, error_type: str, message: str) -> None:
    """Record an error in state.errors[] with retry_count tracking.

    If an entry for mail_id already exists, increments retry_count.
    If retry_count >= 3, marks as permanent_failure.
    """
    state = load_state()
    existing = next((e for e in state["errors"] if e["mail_id"] == mail_id), None)
    if existing:
        existing["retry_count"] = existing.get("retry_count", 0) + 1
        existing["last_error"] = message
        existing["last_at"] = _now_iso()
        if existing["retry_count"] >= 3:
            existing["permanent_failure"] = True
    else:
        state["errors"].append({
            "mail_id": mail_id,
            "phase": phase,
            "error_type": error_type,
            "message": message,
            "timestamp": _now_iso(),
            "last_at": _now_iso(),
            "retry_count": 0,
            "permanent_failure": False,
        })
    save_state(state)


def clear_error(mail_id: str) -> None:
    """Remove an error entry from state.errors[] (after successful retry)."""
    state = load_state()
    state["errors"] = [e for e in state["errors"] if e["mail_id"] != mail_id]
    save_state(state)


def get_pending_errors() -> list[dict]:
    """Return errors that are not permanent_failure and retry_count < 3."""
    state = load_state()
    return [
        e for e in state["errors"]
        if e.get("retry_count", 0) < 3 and not e.get("permanent_failure", False)
    ]


def acquire_lock(name: str) -> bool:
    """Set active_lock if currently None. Return True if acquired."""
    state = load_state()
    if state["active_lock"] is not None:
        return False
    state["active_lock"] = name
    save_state(state)
    return True


def release_lock() -> None:
    """Clear active_lock."""
    state = load_state()
    state["active_lock"] = None
    save_state(state)
