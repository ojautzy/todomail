#!/usr/bin/env python3
"""Extraction de texte depuis les fichiers OpenDocument (.odt, .ods, .odp).

Usage:
    python3 read_odf.py <fichier>

Affiche le contenu texte sur stdout.
Codes de sortie : 0=OK, 1=fichier introuvable/extension non supportée,
                  2=odfpy manquant, 3=fichier corrompu.
"""

import argparse
import sys
from pathlib import Path

try:
    from odf import table as odf_table
    from odf import text as odf_text
    from odf.opendocument import load as odf_load
    from odf.teletype import extractText as odf_extract_text
except ImportError:
    print(
        "Erreur : odfpy n'est pas installé.\n"
        "Installez-le avec : pip3 install odfpy",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    from odf import draw as odf_draw
except ImportError:
    odf_draw = None

SUPPORTED_EXTENSIONS = {".odt", ".ods", ".odp"}


def extract_odt_text(doc) -> str:
    """Extrait le texte d'un document ODT (titres et paragraphes)."""
    headings = doc.getElementsByType(odf_text.H)
    paragraphs = doc.getElementsByType(odf_text.P)

    lines = []
    for element in headings + paragraphs:
        t = odf_extract_text(element)
        if t.strip():
            lines.append(t)
    return "\n".join(lines)


def extract_ods_text(doc) -> str:
    """Extrait le texte d'un tableur ODS (cellules separees par |)."""
    lines = []
    for sheet in doc.getElementsByType(odf_table.Table):
        sheet_name = sheet.getAttribute("name")
        if sheet_name:
            lines.append(f"[{sheet_name}]")
        for row in sheet.getElementsByType(odf_table.TableRow):
            cells = row.getElementsByType(odf_table.TableCell)
            cell_texts = []
            for cell in cells:
                repeat = cell.getAttribute("numbercolumnsrepeated")
                paras = cell.getElementsByType(odf_text.P)
                cell_text = " ".join(
                    odf_extract_text(p) for p in paras
                ).strip()
                if repeat and int(repeat) > 20 and not cell_text:
                    continue
                if cell_text:
                    cell_texts.append(cell_text)
            if cell_texts:
                lines.append(" | ".join(cell_texts))
    return "\n".join(lines)


def extract_odp_text(doc) -> str:
    """Extrait le texte d'une presentation ODP, diapositive par diapositive."""
    if odf_draw is None:
        return extract_odt_text(doc)

    pages = doc.getElementsByType(odf_draw.Page)
    if not pages:
        return extract_odt_text(doc)

    lines = []
    for i, page in enumerate(pages, 1):
        lines.append(f"--- Diapositive {i} ---")
        headings = page.getElementsByType(odf_text.H)
        paragraphs = page.getElementsByType(odf_text.P)
        for element in headings + paragraphs:
            t = odf_extract_text(element)
            if t.strip():
                lines.append(t)
    return "\n".join(lines)


EXTRACTORS = {
    ".odt": extract_odt_text,
    ".ods": extract_ods_text,
    ".odp": extract_odp_text,
}


def main():
    parser = argparse.ArgumentParser(
        description="Extraire le texte d'un fichier OpenDocument (.odt, .ods, .odp)"
    )
    parser.add_argument("fichier", help="Chemin du fichier OpenDocument")
    args = parser.parse_args()

    filepath = Path(args.fichier)

    if not filepath.exists():
        print(f"Erreur : fichier introuvable : {filepath}", file=sys.stderr)
        sys.exit(1)

    ext = filepath.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        print(
            f"Erreur : extension '{ext}' non supportee. "
            f"Extensions supportees : {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        doc = odf_load(str(filepath))
    except Exception as e:
        print(f"Erreur : impossible de lire le fichier : {e}", file=sys.stderr)
        sys.exit(3)

    text = EXTRACTORS[ext](doc)

    if not text.strip():
        print("Attention : aucun contenu texte extrait.", file=sys.stderr)

    print(text)


if __name__ == "__main__":
    main()
