#!/usr/bin/env python3
"""Hook UserPromptSubmit — injection silencieuse d'un résumé du state.

Lit `state.json` via `lib/state.py` et injecte un résumé compact dans
le contexte du prompt utilisateur, uniquement si quelque chose mérite
l'attention de Claude (phase en cours, verrou, erreurs).

Reste silencieux le reste du temps (aucune sortie). Toujours exit 0.
Totalement inerte hors d'un workspace todomail (v2.4.4).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _build_summary() -> str | None:
    # Appele uniquement dans un workspace marque (cf. main) : load_state()
    # cree state.json s'il manque, ce qui est voulu dans un workspace.
    try:
        from lib.state import load_state, get_pending_errors
        state = load_state()
    except Exception:
        return None

    phase = state.get("current_phase")
    lock = state.get("active_lock")
    try:
        errors = len(get_pending_errors())
    except Exception:
        errors = 0

    # Rien de notable : silencieux.
    if not phase and not lock and errors == 0:
        return None

    parts: list[str] = []
    if phase:
        parts.append(f"phase: {phase}")
    if lock:
        parts.append(f"lock: {lock}")
    if errors:
        parts.append(f"erreurs: {errors}")

    return "[todomail state] " + " | ".join(parts)


def main() -> None:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    # v2.4.4 : inerte hors d'un workspace todomail (avant, load_state()
    # creait .todomail/state.json dans n'importe quel projet ouvert).
    from lib.workspace import hook_workspace
    if hook_workspace(payload if isinstance(payload, dict) else {}) is None:
        return

    summary = _build_summary()
    if not summary:
        return

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": summary,
        }
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
