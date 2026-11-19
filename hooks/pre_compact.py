#!/usr/bin/env python3
"""Hook PreCompact — sauvegarde snapshot avant compaction du contexte.

Sauvegarde le state.json courant et les checkpoints dans un fichier
horodaté sous `$CLAUDE_PROJECT_DIR/.todomail/precompact_snapshot_<ts>.json`
pour permettre une reprise post-compaction si besoin.

Ne bloque jamais la compaction (exit 0 toujours). Totalement inerte
hors d'un workspace todomail (v2.4.4).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


MAX_SNAPSHOTS = 10  # garde les 10 plus récents


def _runtime_dir() -> Path | None:
    """`.todomail/` du workspace, ou None hors workspace todomail (v2.4.4).

    Memes candidats que `lib.state.workspace_dir()` ($CLAUDE_PROJECT_DIR
    puis cwd), chacun retenu seulement s'il porte le marqueur.
    """
    from lib.workspace import resolve_workspace
    ws = resolve_workspace(os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd())
    return None if ws is None else ws / ".todomail"


def _load_state() -> dict:
    try:
        from lib.state import load_state
        return load_state()
    except Exception:
        return {}


def _prune(data_dir: Path) -> None:
    try:
        snaps = sorted(data_dir.glob("precompact_snapshot_*.json"))
        for old in snaps[:-MAX_SNAPSHOTS]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass


def main() -> None:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    data_dir = _runtime_dir()
    if data_dir is None:
        return
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    state = _load_state()
    snapshot = {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "trigger": payload.get("trigger") or payload.get("matcher"),
        "session_id": payload.get("session_id"),
        "state": state,
        "checkpoints": state.get("checkpoints", [])[-20:],
        "counters": state.get("counters", {}),
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = data_dir / f"precompact_snapshot_{ts}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

    _prune(data_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
