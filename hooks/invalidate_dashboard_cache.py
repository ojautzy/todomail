#!/usr/bin/env python3
"""Hook PostToolUse (Bash mv|rm) — signal d'invalidation du dashboard.

Déclenché après une commande `mv` ou `rm` lancée par Claude. Filtre sur
les chemins touchés : on ne signale que si l'opération concerne `todo/`,
`inbox/` ou `mails/`. Touche `.todomail/invalidate.txt` dans le workspace
et incrémente le compteur de modifications dans state.json (ce qui touche
aussi `.todomail/invalidate.txt` au passage — redondance assumee, c'est le
fichier de signal, peu importe d'ou vient le top).

Toujours exit 0 (non bloquant). Lit le payload JSON sur stdin.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


WATCHED_DIRS = ("todo/", "inbox/", "mails/", "./todo/", "./inbox/", "./mails/")


def _project_dir(payload: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")


def _command_touches_watched(command: str) -> bool:
    if not command:
        return False
    # Doit être un mv ou rm (filtré normalement par "if:" côté hooks.json,
    # mais on re-vérifie par sécurité).
    if not re.search(r"\b(mv|rm)\b", command):
        return False
    return any(d in command for d in WATCHED_DIRS)


def _touch(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        now = datetime.now(timezone.utc).timestamp()
        os.utime(path, (now, now))
    except OSError:
        pass


def _bump_counter() -> None:
    try:
        from lib.state import load_state, save_state
        state = load_state()
        counters = state.setdefault("counters", {})
        counters["modifications"] = int(counters.get("modifications", 0)) + 1
        save_state(state)
    except Exception:
        pass


def main() -> None:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        return

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or ""
    if not _command_touches_watched(command):
        return

    project = _project_dir(payload)
    _touch(project / ".todomail" / "invalidate.txt")
    _bump_counter()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
