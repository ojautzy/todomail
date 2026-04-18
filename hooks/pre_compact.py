#!/usr/bin/env python3
"""Hook PreCompact — sauvegarde snapshot avant compaction du contexte.

Sauvegarde le state.json courant et les checkpoints dans un fichier
horodaté sous `${CLAUDE_PLUGIN_DATA}/precompact_snapshot_<ts>.json` pour
permettre une reprise post-compaction si besoin.

Ne bloque jamais la compaction (exit 0 toujours).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


MAX_SNAPSHOTS = 10  # garde les 10 plus récents


def _plugin_data_dir() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / ".plugin-data"


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

    data_dir = _plugin_data_dir()
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
