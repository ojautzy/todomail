"""Gestion du state.json persistant pour le plugin TodoMail.

A partir de la v2.0.0-alpha.8 : tout l'etat runtime du plugin vit dans
`$CLAUDE_PROJECT_DIR/.todomail/` (workspace utilisateur), pas dans
`$CLAUDE_PLUGIN_DATA`. Decision motivee par le fait que toutes les donnees
runtime du plugin sont specifiques au workspace (pas globales au plugin).
Avantages : isolation naturelle entre workspaces, plus de mirror a
synchroniser, plus de probleme de propagation des variables d'env aux
sous-processus Python lances par les skills, debug facilite.
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


def workspace_dir() -> Path:
    """Resolve la racine du workspace utilisateur.

    Ordre :
    1. `$CLAUDE_PROJECT_DIR` (defini par Claude Code dans les hooks ;
       passe via le payload aux scripts ; les sous-processus Python
       lances par un skill peuvent ne pas l'avoir, d'ou le fallback).
    2. `os.getcwd()` si le repertoire contient un marqueur workspace
       (`.todomail-config.json`). Sinon erreur explicite.

    Lever une exception est volontairement strict : sans workspace
    valide, aucune ecriture d'etat n'a de sens.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        project = Path(env)
        if project.is_dir():
            return project
    cwd = Path.cwd()
    if (cwd / ".todomail-config.json").is_file():
        return cwd
    raise RuntimeError(
        "Workspace todomail introuvable : ni $CLAUDE_PROJECT_DIR ni un "
        "cwd contenant .todomail-config.json. Lance /todomail:start "
        "depuis le repertoire de travail pour initialiser."
    )


def runtime_dir() -> Path:
    """Repertoire `.todomail/` a la racine du workspace, tout l'etat runtime.

    Cree le dossier a la volee s'il n'existe pas (idempotent).
    """
    rt = workspace_dir() / ".todomail"
    rt.mkdir(parents=True, exist_ok=True)
    return rt


def _state_path() -> Path:
    return runtime_dir() / "state.json"


def _touch_dashboard_invalidate() -> None:
    """Touche `.todomail/invalidate.txt` — signal pour le polling dashboard.

    Tout `save_state()` publie ce top externe detectable via File System
    Access, sans dependre du hook `PostToolUse Bash(mv|rm)` qui ne fire pas
    quand les skills bougent les fichiers via Python (`lib.fs_utils.safe_mv`).
    Best-effort, silencieux en cas d'erreur.
    """
    try:
        path = runtime_dir() / "invalidate.txt"
        path.touch(exist_ok=True)
        now = datetime.now(timezone.utc).timestamp()
        os.utime(path, (now, now))
    except (OSError, RuntimeError):
        pass


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
    """Atomic write of state dict to `.todomail/state.json`.

    Touche aussi `.todomail/invalidate.txt` pour notifier le polling
    dashboard. Plus de mirror a synchroniser depuis alpha.8 — le state
    canonique vit directement a un endroit accessible au dashboard.
    """
    path = _state_path()
    tmp = path.with_suffix(".json.tmp")
    state["last_update_at"] = _now_iso()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp), str(path))
    _touch_dashboard_invalidate()


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
