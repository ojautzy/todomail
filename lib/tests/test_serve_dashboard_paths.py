"""Tests des gardes de chemin du serveur dashboard (v2.3.1).

Couvre la correction du bug « segment invalide » : les noms de fichiers
réels (pièces jointes MIME-décodées avec espaces, accents, apostrophes,
parenthèses) doivent être acceptés, tandis que toute tentative d'évasion
du workspace (`..`, séparateurs réintroduits par décodage URL, symlinks
sortants) reste rejetée. Couvre aussi l'en-tête Content-Disposition
100 % ASCII (http.server encode les headers en latin-1).

Exécution depuis la racine du plugin :

    python3 -m unittest lib.tests.test_serve_dashboard_paths

Autonome (stdlib uniquement), aucune écriture hors tempdir.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Racine du plugin (lib/tests/ -> plugin)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.serve_dashboard import (  # noqa: E402
    _segment_ok,
    content_disposition,
    resolve_under,
)


class TestSegmentOk(unittest.TestCase):
    def test_accepte_noms_reels(self):
        for name in (
            "Indicateurs au 3 juillet 2026.docx",
            "récap détaillé (v2).pdf",
            "l'été – bilan & synthèse.docx",
            "œuvre complète.txt",
            "CR_réunion n°4 [final].odt",
            "message.eml",
            "2026-07-03_09h15m22",
            "Ürgent ! 100% ça marche.png",
        ):
            self.assertTrue(_segment_ok(name), name)

    def test_rejette_segments_dangereux(self):
        for seg in (
            "",
            ".",
            "..",
            "a/b",          # séparateur réintroduit par %2F décodé
            "a\\b",
            "a\x00b",
            "a\nb",
            "a\tb",
            "a\x7fb",
            "\x1b[31m",
        ):
            self.assertFalse(_segment_ok(seg), repr(seg))


class TestResolveUnder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def test_resout_nom_avec_espaces_et_accents(self):
        mail_dir = self.root / "todo" / "do-decide" / "2026-07-03_09h15m22"
        mail_dir.mkdir(parents=True)
        target = mail_dir / "Indicateurs au 3 juillet 2026.docx"
        target.write_bytes(b"contenu")
        resolved = resolve_under(
            self.root, "todo", "do-decide", "2026-07-03_09h15m22",
            "Indicateurs au 3 juillet 2026.docx",
        )
        self.assertEqual(resolved, target)
        self.assertEqual(resolved.read_bytes(), b"contenu")

    def test_racine_sans_segment(self):
        self.assertEqual(resolve_under(self.root), self.root)

    def test_rejette_dotdot(self):
        with self.assertRaises(PermissionError):
            resolve_under(self.root, "todo", "..", "secret")

    def test_rejette_separateur_dans_segment(self):
        # équivalent d'un %2F décodé dans un seul segment d'URL
        with self.assertRaises(PermissionError):
            resolve_under(self.root, "todo/../..")

    def test_rejette_symlink_sortant(self):
        outside = Path(tempfile.mkdtemp())
        try:
            (outside / "secret.txt").write_text("secret", encoding="utf-8")
            (self.root / "todo").mkdir()
            (self.root / "todo" / "lien").symlink_to(outside)
            with self.assertRaises(PermissionError):
                resolve_under(self.root, "todo", "lien", "secret.txt")
        finally:
            (outside / "secret.txt").unlink()
            outside.rmdir()


class TestContentDisposition(unittest.TestCase):
    def test_toujours_ascii(self):
        # http.server encode les headers en latin-1 : la valeur doit être
        # ASCII quel que soit le nom (y compris hors latin-1 : – , œ).
        for name in (
            "rapport.pdf",
            "Indicateurs au 3 juillet 2026.docx",
            "l'été – bilan & synthèse.docx",
            "œuvre \"citée\".txt",
        ):
            value = content_disposition(name)
            value.encode("ascii")  # ne doit pas lever
            self.assertTrue(value.startswith("inline; "), value)

    def test_forme_rfc5987_presente(self):
        value = content_disposition("récap détaillé.pdf")
        self.assertIn("filename*=UTF-8''", value)
        self.assertIn("r%C3%A9cap%20d%C3%A9taill%C3%A9.pdf", value)

    def test_guillemets_neutralises_dans_fallback(self):
        value = content_disposition('rapport "final".pdf')
        # le paramètre filename="..." ne doit pas contenir de guillemet brut
        fallback = value.split("filename=", 1)[1].split(";", 1)[0]
        self.assertEqual(fallback.count('"'), 2, value)  # uniquement les délimiteurs


if __name__ == "__main__":
    unittest.main()
