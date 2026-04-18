#!/usr/bin/env python3
"""Hook SessionStart — warm-up mémoire et signalement de reprise.

Exécuté au démarrage de chaque session Claude Code. Vérifie l'existence des
répertoires de travail, compile un index léger de la mémoire projet, et
signale toute reprise nécessaire après interruption.

Lit un payload JSON sur stdin (session_id, source, cwd, etc.).
Sortie : JSON hookSpecificOutput.additionalContext si quelque chose à
signaler, silence sinon. Jamais bloquant.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Accès aux helpers lib/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _project_dir(payload: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")


def _plugin_data_dir() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / ".plugin-data"


def _log_smoke(payload: dict) -> None:
    """Trace de déclenchement (activable via .hooks_debug à la racine projet).

    Capture source, cwd, PATH, python, session_id. Utile pour diagnostiquer
    les problèmes de déclenchement dans Claude Desktop (macOS GUI).
    """
    project = _project_dir(payload)
    if not (project / ".hooks_debug").exists():
        return
    data_dir = _plugin_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(data_dir / ".hooks_fired.log", "a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).isoformat()
            f.write(
                f"{ts} SessionStart "
                f"source={payload.get('source', '?')} "
                f"session={payload.get('session_id', '?')} "
                f"cwd={payload.get('cwd', '?')} "
                f"python={sys.executable} "
                f"PATH={os.environ.get('PATH', '?')[:200]}\n"
            )
    except OSError:
        pass


def _build_memory_cache(project: Path) -> dict:
    """Construit un index {nom -> chemin} des fichiers de memory/."""
    cache: dict = {"compiled_at": datetime.now(timezone.utc).isoformat(), "entries": {}}
    for sub in ("memory/people", "memory/projects", "memory/context"):
        root = project / sub
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            name = path.stem
            cache["entries"][name] = str(path.relative_to(project))
    return cache


def _write_memory_cache(cache: dict) -> None:
    data_dir = _plugin_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        tmp = data_dir / "memory_cache.json.tmp"
        final = data_dir / "memory_cache.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp), str(final))
    except OSError:
        pass


def _missing_dirs(project: Path) -> list[str]:
    expected = ("inbox", "todo", "mails", "to-send", "to-work", "docs")
    return [d for d in expected if not (project / d).is_dir()]


def _read_marker_ids(path: Path) -> list[str]:
    """Lit un fichier-marqueur (un ID par ligne, # pour commentaires)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    ids: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ids.append(stripped)
    return ids


def _consume_dashboard_markers(project: Path) -> list[str]:
    """Consomme les fichiers-marqueurs ecrits par le dashboard.

    - `retry_request.txt` : IDs de mails a relancer (ou fichier vide = tous).
      Marque les entries correspondantes dans `state.errors[]` avec
      `retry_requested: true` pour que `/process-todo --retry` les traite
      en priorite.
    - `errors_dismiss.txt` : IDs a retirer de `state.errors[]`.

    Les deux fichiers sont supprimes apres consommation. Renvoie une
    liste de notes a injecter dans le message de reprise.
    """
    notes: list[str] = []
    retry_path = project / "retry_request.txt"
    dismiss_path = project / "errors_dismiss.txt"
    if not retry_path.exists() and not dismiss_path.exists():
        return notes

    try:
        from lib.state import load_state, save_state
    except Exception:
        return notes

    try:
        state = load_state()
    except Exception:
        return notes

    errors = state.get("errors", [])

    if retry_path.exists():
        ids = _read_marker_ids(retry_path)
        if not ids:
            for e in errors:
                e["retry_requested"] = True
            notes.append(f"{len(errors)} erreur(s) marquees pour retry")
        else:
            count = 0
            for e in errors:
                if e.get("mail_id") in ids:
                    e["retry_requested"] = True
                    count += 1
            notes.append(f"{count} erreur(s) marquees pour retry")
        try:
            retry_path.unlink()
        except OSError:
            pass

    if dismiss_path.exists():
        ids = set(_read_marker_ids(dismiss_path))
        before = len(errors)
        state["errors"] = [e for e in errors if e.get("mail_id") not in ids]
        removed = before - len(state["errors"])
        if removed:
            notes.append(f"{removed} erreur(s) ignoree(s) (dashboard)")
        try:
            dismiss_path.unlink()
        except OSError:
            pass

    try:
        save_state(state)
    except Exception:
        pass

    return notes


def _resume_message(missing: list[str]) -> str | None:
    """Compose un message de reprise si state.json ou répertoires le justifient."""
    try:
        from lib.state import load_state, get_pending_errors
        state = load_state()
    except Exception:
        return None

    parts: list[str] = []
    lock = state.get("active_lock")
    if lock:
        parts.append(f"verrou actif `{lock}` (session precedente interrompue)")
    try:
        pending = get_pending_errors()
    except Exception:
        pending = []
    if pending:
        parts.append(f"{len(pending)} erreurs en attente (utiliser --retry)")
    if missing:
        parts.append("repertoires manquants: " + ", ".join(missing))

    if not parts:
        return None
    return "[todomail] Reprise possible : " + " | ".join(parts)


def main() -> None:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    _log_smoke(payload)

    project = _project_dir(payload)
    cache = _build_memory_cache(project)
    _write_memory_cache(cache)

    marker_notes = _consume_dashboard_markers(project)
    missing = _missing_dirs(project)
    msg = _resume_message(missing)
    if marker_notes:
        prefix = "[todomail] Dashboard : " + " | ".join(marker_notes)
        msg = prefix if not msg else prefix + "\n" + msg

    if msg:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": msg,
            }
        }
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
