#!/usr/bin/env python3
"""Hook PreToolUse (Write|Edit) — garde-fou structurel pour docs/.

Dans un workspace todomail (marqueur `.todomail-config.json`), refuse
toute écriture ou édition sous `docs/` qui n'est pas située dans
`docs/AURA/` ou `docs/MIN/`. Inerte partout ailleurs (v2.4.4). Voir `skills/classify-attachment/SKILL.md`
pour la règle canonique.

Lit le payload JSON sur stdin (tool_name, tool_input.file_path, etc.).
Sortie : JSON hookSpecificOutput.permissionDecision = "deny" si violation,
silence sinon. Exit 0 dans les deux cas (le JSON porte la décision).
Fallback exit 2 + stderr en cas d'erreur de sérialisation JSON.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


ALLOWED_ROOTS = ("docs/AURA/", "docs/MIN/")


def _normalize(path: str, project_dir: str | None) -> str:
    """Ramène un chemin absolu sous le projet à une forme relative à docs/."""
    if not path:
        return ""
    # Chemin relatif : on le renvoie tel quel (normalisé avec /)
    p = path.replace("\\", "/")
    if os.path.isabs(p) and project_dir:
        try:
            rel = os.path.relpath(p, project_dir).replace("\\", "/")
            return rel
        except ValueError:
            return p
    return p


def _is_in_docs(rel_path: str) -> bool:
    return rel_path == "docs" or rel_path.startswith("docs/")


def _is_allowed(rel_path: str) -> bool:
    return any(rel_path.startswith(root) for root in ALLOWED_ROOTS)


def _deny(file_path: str) -> None:
    reason = (
        f"Refus : la destination `{file_path}` est hors de la structure "
        "canonique `docs/AURA/` ou `docs/MIN/`. Consulte "
        "`skills/classify-attachment/SKILL.md` pour le classement correct."
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        return 0

    # v2.4.4 : inerte hors d'un workspace todomail (marqueur absent)
    from lib.workspace import hook_workspace
    workspace = hook_workspace(payload if isinstance(payload, dict) else {})
    if workspace is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0

    rel = _normalize(file_path, str(workspace))

    if not _is_in_docs(rel):
        return 0  # hors docs/ : autorisé
    if _is_allowed(rel):
        return 0  # docs/AURA/ ou docs/MIN/ : autorisé

    _deny(file_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Fallback : deny via exit 2 + stderr si le JSON a échoué
        sys.stderr.write(f"enforce_classify: erreur interne ({exc!r})\n")
        sys.exit(0)
