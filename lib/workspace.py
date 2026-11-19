"""Critère unique « ce dossier est un espace de travail todomail » (v2.4.4).

Le plugin est chargé dans TOUTES les sessions Claude Code de la machine,
y compris dans des projets sans rapport avec todomail. Tout code qui
agit sur un workspace (hooks, `lib.state`) doit d'abord vérifier qu'il
s'y trouve, sinon il crée `.todomail/`, des slugs dans
`~/.config/todomail/` ou refuse des écritures légitimes dans `docs/`.

Critère : présence du fichier marqueur `.todomail-config.json` à la
racine, écrit par `/todomail:start` (étape 0b) et jamais supprimé
(cf. CLAUDE.md). Module sans dépendance (stdlib seule) : importable par
les hooks sans coût.
"""

from __future__ import annotations

import os
from pathlib import Path

MARKER_FILENAME = ".todomail-config.json"


def is_todomail_workspace(path: str | os.PathLike | None) -> bool:
    """True si `path` est la racine d'un workspace todomail initialisé."""
    if not path:
        return False
    try:
        return (Path(path) / MARKER_FILENAME).is_file()
    except (OSError, ValueError):
        return False


def resolve_workspace(*candidates: str | os.PathLike | None) -> Path | None:
    """Premier candidat qui est un workspace todomail, sinon None.

    Les candidats vides ou None sont ignorés. Ne crée jamais rien.
    """
    for cand in candidates:
        if is_todomail_workspace(cand):
            return Path(cand)
    return None


def hook_workspace(payload: dict | None) -> Path | None:
    """Workspace d'un hook : `$CLAUDE_PROJECT_DIR`, à défaut la `cwd` du payload.

    Même dossier candidat qu'avant la v2.4.4 (aucun repli supplémentaire),
    mais retenu seulement s'il porte le marqueur. None = hors workspace :
    le hook doit sortir immédiatement, en silence.
    """
    project = os.environ.get("CLAUDE_PROJECT_DIR") or (payload or {}).get("cwd")
    return resolve_workspace(project)
