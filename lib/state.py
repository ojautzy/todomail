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


def _discover_plugin_data() -> Path | None:
    """Decouvre le repertoire CLAUDE_PLUGIN_DATA canonique du plugin todomail.

    Cherche `~/.claude/plugins/data/todomail*` et retourne le repertoire
    le plus recemment modifie (heuristique : c'est l'installation active).
    Necessaire car les sous-processus Python lances depuis un skill
    n'heritent pas toujours de la variable d'environnement.
    """
    base = Path.home() / ".claude" / "plugins" / "data"
    if not base.is_dir():
        return None
    candidates = [p for p in base.glob("todomail*") if p.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _state_dir() -> Path:
    """Resolve the directory for state.json.

    Ordre de resolution :
    1. `$CLAUDE_PLUGIN_DATA` (defini par Claude Code aux hooks/MCP servers)
    2. Decouverte auto dans `~/.claude/plugins/data/todomail*` (skills)
    3. Fallback `${plugin_root}/.plugin-data/` (tests, dev hors Claude Code)
    """
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    discovered = _discover_plugin_data()
    if discovered is not None:
        return discovered
    return Path(__file__).resolve().parent.parent / ".plugin-data"


def _state_path() -> Path:
    return _state_dir() / "state.json"


def _discover_workspace() -> Path | None:
    """Decouvre la racine du workspace utilisateur (CLAUDE_PROJECT_DIR).

    Ordre :
    1. `$CLAUDE_PROJECT_DIR` (defini par Claude Code aux hooks)
    2. `os.getcwd()` SI le repertoire contient un marqueur workspace
       todomail (`.todomail-config.json`). Sinon refus pour eviter
       d'ecrire le mirror dans un repertoire arbitraire.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        project = Path(env)
        if project.is_dir():
            return project
    cwd = Path.cwd()
    if (cwd / ".todomail-config.json").is_file():
        return cwd
    return None


def _workspace_mirror_path() -> Path | None:
    """Chemin du mirror `.todomail-state.json` a la racine du workspace.

    Renvoie None si le workspace n'est pas resolu. Le mirror permet au
    dashboard (File System Access) d'acceder a l'etat persistant hors
    `${CLAUDE_PLUGIN_DATA}`.
    """
    workspace = _discover_workspace()
    return workspace / ".todomail-state.json" if workspace else None


def _touch_dashboard_invalidate() -> None:
    """Touche `dashboard_invalidate.txt` a la racine du workspace.

    Signal unifie pour le dashboard (polling 3s) : tout `save_state()`
    publie un top externe detectable via File System Access, sans dependre
    du hook `PostToolUse Bash(mv|rm)` — qui ne fire pas quand les skills
    bougent les fichiers via Python (`lib.fs_utils.safe_mv`, etc.).
    Best-effort, silencieux en cas d'erreur.
    """
    workspace = _discover_workspace()
    if workspace is None:
        return
    path = workspace / "dashboard_invalidate.txt"
    try:
        path.touch(exist_ok=True)
        now = datetime.now(timezone.utc).timestamp()
        os.utime(path, (now, now))
    except OSError:
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
    """Atomic write of state dict to state.json.

    Ecrit aussi un mirror `.todomail-state.json` a la racine du workspace
    (`$CLAUDE_PROJECT_DIR`) pour que le dashboard HTML y accede via File
    System Access. Le mirror est best-effort : toute erreur est avalee
    silencieusement pour ne pas bloquer le state canonique.
    """
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    state["last_update_at"] = _now_iso()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp), str(path))

    mirror = _workspace_mirror_path()
    if mirror is not None:
        try:
            mirror_tmp = mirror.with_suffix(".json.tmp")
            with open(mirror_tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(str(mirror_tmp), str(mirror))
        except OSError:
            pass

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
