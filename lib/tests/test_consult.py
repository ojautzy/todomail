"""Tests du registre des consultations `lib/consult.py` (v2.4.1).

Couvre les causes des deux bugs du suivi des consultations dans le
dashboard (carte « traitée » qui ne disparaît pas, filtre inopérant) :
lignes partageant un même ID, doublons exacts, ajout non idempotent,
suppression qui doit relire le fichier et préserver le reste.

Exécution depuis la racine du plugin :

    python3 -m unittest lib.tests.test_consult

Autonome (stdlib uniquement), aucune écriture hors tempdir.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.consult import (  # noqa: E402
    HEADER,
    append_entries,
    dedupe_file,
    entry_key,
    parse_entries,
    parse_row,
    remove_entry,
)

A = {"id": "2026-06-18_14h00m00", "date": "2026-06-22",
     "destinataire": "Véronique Bicilli (DPEE)", "resume": "Recensement SI à enjeu"}
B = {"id": "2026-07-17_11h35m22", "date": "2026-07-21",
     "destinataire": "Guillaume PERRIN (SG)", "resume": "SDIR Occitanie"}
# Même mail que B, autre consultation (destinataire différent) : légitime.
B2 = {"id": "2026-07-17_11h35m22", "date": "2026-07-21",
      "destinataire": "Antoine Crossay (COM)", "resume": "SDIR Occitanie — volet COM"}


def row(e):
    return f"| {e['id']} | {e['date']} | {e['destinataire']} | {e['resume']} |\n"


class TestParse(unittest.TestCase):
    def test_entete_et_separateur_ignores(self):
        self.assertEqual(parse_entries(HEADER), [])
        self.assertIsNone(parse_row("|----|------|-------------|--------|"))
        self.assertIsNone(parse_row("| ID | Date | Destinataire | Résumé |"))
        self.assertIsNone(parse_row("# Registre des consultations"))

    def test_doublons_exacts_rendus_une_fois(self):
        text = HEADER + row(A) + row(B) + row(A) + row(A)
        self.assertEqual(parse_entries(text), [A, B])
        self.assertEqual(len(parse_entries(text, dedupe=False)), 4)

    def test_meme_id_destinataires_differents_conserves(self):
        text = HEADER + row(B) + row(B2)
        entries = parse_entries(text)
        self.assertEqual(len(entries), 2)
        self.assertNotEqual(entry_key(entries[0]), entry_key(entries[1]))

    def test_cellule_vide_positionnelle_et_pipe_dans_resume(self):
        e = parse_row("| X1 |  | Jean | avant | après |")
        self.assertEqual(e, {"id": "X1", "date": "", "destinataire": "Jean",
                             "resume": "avant | après"})

    def test_espaces_normalises(self):
        e = parse_row("|  X1 | 2026-01-01 |  Jean   Dupont | a  b |")
        self.assertEqual(e["destinataire"], "Jean Dupont")
        self.assertEqual(e["resume"], "a b")


class TestAppend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "consult.md"

    def tearDown(self):
        self.tmp.cleanup()

    def test_cree_fichier_avec_entete(self):
        added, skipped = append_entries(self.path, [A])
        self.assertEqual((added, skipped), (1, 0))
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(HEADER))
        self.assertEqual(parse_entries(text), [A])

    def test_idempotent_sur_reexecution(self):
        append_entries(self.path, [A, B])
        added, skipped = append_entries(self.path, [A, B, B2])
        self.assertEqual((added, skipped), (1, 2))
        added, skipped = append_entries(self.path, [A, B, B2])
        self.assertEqual((added, skipped), (0, 3))
        self.assertEqual(len(parse_entries(self.path.read_text(), dedupe=False)), 3)

    def test_doublon_dans_le_lot_et_entree_sans_id(self):
        added, skipped = append_entries(self.path, [A, dict(A), {"id": ""}, None])
        self.assertEqual((added, skipped), (1, 3))

    def test_champs_assainis(self):
        append_entries(self.path, [{"id": "X", "date": "d",
                                    "destinataire": "a|b", "resume": "l1\nl2"}])
        self.assertEqual(parse_entries(self.path.read_text()),
                         [{"id": "X", "date": "d", "destinataire": "a/b", "resume": "l1 l2"}])


class TestRemove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "consult.md"

    def tearDown(self):
        self.tmp.cleanup()

    def test_retire_ligne_et_ses_doublons_exacts_seulement(self):
        self.path.write_text(HEADER + row(A) + row(B) + row(A) + row(B2), encoding="utf-8")
        removed, remaining = remove_entry(self.path, A)
        self.assertEqual(removed, 2)
        self.assertEqual(remaining, [B, B2])
        self.assertEqual(parse_entries(self.path.read_text(), dedupe=False), [B, B2])

    def test_meme_id_autre_destinataire_preserve(self):
        self.path.write_text(HEADER + row(B) + row(B2), encoding="utf-8")
        removed, remaining = remove_entry(self.path, B)
        self.assertEqual(removed, 1)
        self.assertEqual(remaining, [B2])

    def test_preserve_texte_hors_table_et_lignes_ajoutees(self):
        # Le fichier a été complété (cycle Claude) après l'affichage : la
        # suppression relit le disque et ne perd rien.
        self.path.write_text("Note libre\n\n" + HEADER + row(A) + row(B), encoding="utf-8")
        append_entries(self.path, [B2])
        remove_entry(self.path, A)
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("Note libre\n"))
        self.assertEqual(parse_entries(text), [B, B2])

    def test_entree_inconnue_ne_reecrit_pas(self):
        self.path.write_text(HEADER + row(A), encoding="utf-8")
        mtime = self.path.stat().st_mtime_ns
        removed, remaining = remove_entry(self.path, B)
        self.assertEqual((removed, remaining), (0, [A]))
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)

    def test_fichier_absent(self):
        self.assertEqual(remove_entry(self.path, A), (0, []))
        self.assertFalse(self.path.exists())


class TestDedupeFile(unittest.TestCase):
    def test_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "consult.md"
            path.write_text(HEADER + row(A) + row(B) + row(A) + row(B) + row(B2), encoding="utf-8")
            self.assertEqual(dedupe_file(path), 2)
            self.assertEqual(parse_entries(path.read_text(), dedupe=False), [A, B, B2])
            self.assertEqual(dedupe_file(path), 0)


if __name__ == "__main__":
    unittest.main()
