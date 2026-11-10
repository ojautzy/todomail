"""Registre des consultations `consult.md` (v2.4.1).

Source unique de la lecture/ecriture de `consult.md`, partagee par le
serveur du dashboard (`lib/serve_dashboard.py`) et par `/process-todo`
(etape 5). Format : table markdown a 4 colonnes

    | ID | Date | Destinataire | Résumé |
    |----|------|-------------|--------|
    | 2026-06-18_14h00m00 | 2026-06-22 | Véronique Bicilli (DPEE) | ... |

Invariants garantis par ce module (corrige en v2.4.1) :

- **Identite d'une consultation = la ligne entiere** (ID + Date +
  Destinataire + Resume, espaces normalises), PAS l'ID seul : un meme mail
  peut legitimement donner lieu a plusieurs consultations (destinataires
  differents). L'ancien dashboard utilisait l'ID comme cle React et comme
  critere de suppression — d'ou cartes fantomes et filtre inoperant des
  que deux lignes partageaient un ID.
- **Ajout idempotent** (`append_entries`) : une ligne deja presente n'est
  jamais reecrite. Les re-executions de `/process-todo` (reprise, retry)
  avaient duplique des blocs entiers du registre (130 lignes dont 44
  doublons exacts dans le workspace de reference).
- **Suppression ciblee cote serveur** (`remove_entry`) : le fichier est
  relu au moment de la suppression et seule la ligne visee (et ses
  doublons exacts) est retiree ; tout le reste — lignes ajoutees entre-
  temps par un cycle, texte hors table — est preserve. L'ancien PUT
  reecrivait tout le fichier depuis l'etat (potentiellement perime) du
  navigateur.
- Ecriture atomique (.tmp + os.replace), droits du fichier existant conserves (v2.4.3).

Stdlib uniquement.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable

from lib.fs_utils import copy_mode_from_existing

FIELDS = ("id", "date", "destinataire", "resume")

HEADER = (
    "# Registre des consultations\n"
    "\n"
    "| ID | Date | Destinataire | Résumé |\n"
    "|----|------|-------------|--------|\n"
)

_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_WS = re.compile(r"\s+")


# --- normalisation ---------------------------------------------------------

def _norm(value) -> str:
    """Normalise un champ : str, espaces internes compactes, bords retires."""
    return _WS.sub(" ", str(value if value is not None else "")).strip()


def _cell(value) -> str:
    """Valeur sure pour une cellule de table (pas de pipe ni de saut de ligne)."""
    return _norm(value).replace("|", "/")


def entry_key(entry: dict) -> tuple:
    """Identite d'une consultation : la ligne entiere normalisee."""
    return tuple(_norm(entry.get(f, "")) for f in FIELDS)


# --- parsing ---------------------------------------------------------------

def parse_row(line: str) -> dict | None:
    """Parse une ligne de donnees de la table, None si ce n'en est pas une.

    Ecarte la ligne d'en-tete (premiere cellule « ID ») et la ligne de
    separation. Les cellules vides sont conservees (positionnelles) ; un
    pipe eventuel dans le resume est recolle dans le resume.
    """
    s = line.strip()
    if not s.startswith("|"):
        return None
    inner = s[1:-1] if s.endswith("|") and len(s) > 1 else s[1:]
    cells = [c.strip() for c in inner.split("|")]
    if len(cells) < 4:
        return None
    if all(_SEPARATOR_CELL.match(c) for c in cells if c) and any(cells):
        return None
    if cells[0].lower() == "id":
        return None
    resume = " | ".join(cells[3:]).strip()
    entry = {"id": cells[0], "date": cells[1], "destinataire": cells[2], "resume": resume}
    if not any(entry.values()):
        return None
    return {k: _norm(v) for k, v in entry.items()}


def parse_entries(text: str, *, dedupe: bool = True) -> list[dict]:
    """Liste des consultations du registre, dans l'ordre du fichier.

    dedupe=True (defaut) : les doublons exacts ne sont rendus qu'une fois
    (premiere occurrence) — une carte par consultation distincte.
    """
    out: list[dict] = []
    seen: set = set()
    for line in text.splitlines():
        entry = parse_row(line)
        if entry is None:
            continue
        key = entry_key(entry)
        if dedupe and key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def format_row(entry: dict) -> str:
    return "| " + " | ".join(_cell(entry.get(f, "")) for f in FIELDS) + " |"


# --- E/S -------------------------------------------------------------------

def read_text(path: Path) -> str:
    """Contenu du registre, "" si absent (les autres erreurs d'E/S remontent)."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    # v2.4.3 : conserver les droits du registre existant (0o600 cree par
    # Claude) — sans cela os.replace le passait en 0o644.
    copy_mode_from_existing(path, tmp)
    os.replace(str(tmp), str(path))


def append_entries(path: Path, entries: Iterable[dict]) -> tuple[int, int]:
    """Ajoute des consultations au registre, de facon idempotente.

    Cree le fichier avec son en-tete s'il est absent. Une entree deja
    presente (meme ligne normalisee) ou en double dans le lot est ignoree.
    Retourne (ajoutees, ignorees).
    """
    path = Path(path)
    text = read_text(path)
    if not text.strip():
        text = HEADER
    existing = {entry_key(e) for e in parse_entries(text, dedupe=False)}
    new_lines: list[str] = []
    skipped = 0
    for entry in entries:
        if not entry:
            skipped += 1
            continue
        key = entry_key(entry)
        if key in existing or not key[0]:
            skipped += 1
            continue
        existing.add(key)
        new_lines.append(format_row(entry))
    if new_lines:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n".join(new_lines) + "\n"
        _atomic_write_text(path, text)
    return len(new_lines), skipped


def remove_entry(path: Path, entry: dict) -> tuple[int, list[dict]]:
    """Retire une consultation (et ses doublons exacts) du registre.

    Le fichier est relu au moment de l'appel : les lignes ajoutees depuis
    le dernier affichage et tout le texte hors table sont preserves.
    Retourne (lignes_retirees, consultations_restantes_dedupliquees).
    """
    path = Path(path)
    text = read_text(path)
    target = entry_key(entry)
    kept: list[str] = []
    removed = 0
    for line in text.splitlines(keepends=True):
        parsed = parse_row(line)
        if parsed is not None and entry_key(parsed) == target:
            removed += 1
            continue
        kept.append(line)
    new_text = "".join(kept)
    if removed:
        _atomic_write_text(path, new_text)
    return removed, parse_entries(new_text)


def dedupe_file(path: Path) -> int:
    """Supprime les doublons exacts du registre (premiere occurrence gardee).

    Retourne le nombre de lignes retirees. Outil de nettoyage ponctuel.
    """
    path = Path(path)
    text = read_text(path)
    seen: set = set()
    kept: list[str] = []
    removed = 0
    for line in text.splitlines(keepends=True):
        parsed = parse_row(line)
        if parsed is not None:
            key = entry_key(parsed)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        kept.append(line)
    if removed:
        _atomic_write_text(path, "".join(kept))
    return removed


if __name__ == "__main__":  # pragma: no cover - outil manuel
    # python3 -m lib.consult --dedupe /chemin/vers/consult.md
    if len(sys.argv) == 3 and sys.argv[1] == "--dedupe":
        n = dedupe_file(Path(sys.argv[2]))
        print(f"{n} doublon(s) exact(s) retire(s)")
    else:
        print("usage: python3 -m lib.consult --dedupe <consult.md>", file=sys.stderr)
        sys.exit(2)
