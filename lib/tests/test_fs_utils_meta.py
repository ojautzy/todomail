"""Tests du filtrage des blocs _meta égarés dans les listes v1/v2 (v2.3.2).

Exécution depuis la racine du plugin :

    python3 -m unittest lib.tests.test_fs_utils_meta

Contexte : le bug v2.3.1 (tuple (meta, emails) de read_pending_emails aplati
dans la liste des mails par le LLM exécutant sort-mails) injectait le bloc
_meta comme premier « mail » de chaque pending_emails.json — carte vide en
tête de catégorie dans le dashboard. Ces tests verrouillent la défense en
profondeur : is_meta_shaped, filtrage en lecture (read_v2_json) et en
écriture (write_v2_json).

Autonome (stdlib uniquement), aucune écriture hors tempdir.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Racine du plugin (lib/tests/ -> plugin)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.fs_utils import (  # noqa: E402
    is_meta_shaped,
    read_pending_emails,
    read_v2_json,
    write_v2_json,
)


META_PHANTOM = {
    "schema_version": 2,
    "session_id": "20260419-054329-f97c59",
    "generated_at": "2026-07-05T07:35:02.666413+00:00",
}

EMAIL = {
    "id": "2026-07-06_14h58m35",
    "sender": "Emmanuel GEORGES (DC)",
    "date": "06 Juil",
    "synth": "Signature RUM P2 + acte d'engagement RN106.",
}


class TestIsMetaShaped(unittest.TestCase):

    def test_phantom_meta_detected(self):
        self.assertTrue(is_meta_shaped(META_PHANTOM))

    def test_meta_with_consumes_session_id_detected(self):
        phantom = dict(META_PHANTOM, consumes_session_id="abc")
        self.assertTrue(is_meta_shaped(phantom))

    def test_partial_meta_detected(self):
        # Un sous-ensemble des clés _meta reste un bloc _meta égaré.
        self.assertTrue(is_meta_shaped({"session_id": "x"}))

    def test_empty_dict_detected(self):
        # Un dict vide n'est jamais une entrée métier valide.
        self.assertTrue(is_meta_shaped({}))

    def test_real_email_kept(self):
        self.assertFalse(is_meta_shaped(EMAIL))

    def test_entry_with_id_kept_even_if_meta_keys(self):
        self.assertFalse(is_meta_shaped(dict(META_PHANTOM, id="2026-07-06_08h00m00")))

    def test_instruction_without_id_kept(self):
        # {"action": "other"} porte une clé hors wrapper : pas un bloc _meta.
        self.assertFalse(is_meta_shaped({"action": "other"}))

    def test_non_dict_kept(self):
        self.assertFalse(is_meta_shaped("2026-07-06_08h00m00"))
        self.assertFalse(is_meta_shaped(None))


class TestReadFiltering(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name: str, payload) -> Path:
        p = self.dir / name
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return p

    def test_v2_contaminated_file_filtered_on_read(self):
        # Reproduction exacte des fichiers DIRMC contaminés (v2.3.1).
        p = self._write("pending_emails.json", {
            "_meta": {"schema_version": 2, "session_id": "s-new", "generated_at": "g"},
            "emails": [META_PHANTOM, EMAIL],
        })
        meta, emails = read_v2_json(p, "emails")
        self.assertEqual(meta["session_id"], "s-new")
        self.assertEqual(emails, [EMAIL])

    def test_v1_bare_array_filtered_on_read(self):
        p = self._write("pending_emails.json", [META_PHANTOM, EMAIL])
        meta, emails = read_v2_json(p, "emails")
        self.assertIsNone(meta)
        self.assertEqual(emails, [EMAIL])

    def test_clean_file_untouched(self):
        p = self._write("pending_emails.json", {
            "_meta": {"schema_version": 2, "session_id": "s", "generated_at": "g"},
            "emails": [EMAIL],
        })
        _meta, emails = read_v2_json(p, "emails")
        self.assertEqual(emails, [EMAIL])

    def test_read_pending_emails_wrapper_filters_too(self):
        cat_dir = self.dir / "do-self"
        cat_dir.mkdir()
        (cat_dir / "pending_emails.json").write_text(json.dumps({
            "_meta": {"schema_version": 2, "session_id": "s", "generated_at": "g"},
            "emails": [META_PHANTOM, EMAIL],
        }), encoding="utf-8")
        _meta, emails = read_pending_emails(cat_dir)
        self.assertEqual(emails, [EMAIL])

    def test_non_list_data_returned_as_is(self):
        p = self._write("weird.json", {"_meta": None, "emails": "pas-une-liste"})
        _meta, data = read_v2_json(p, "emails")
        self.assertEqual(data, "pas-une-liste")


class TestWriteFiltering(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_phantom_purged_on_write(self):
        p = self.dir / "pending_emails.json"
        write_v2_json(p, "emails", [META_PHANTOM, EMAIL], "session-x")
        raw = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(raw["emails"], [EMAIL])
        self.assertEqual(raw["_meta"]["session_id"], "session-x")

    def test_roundtrip_contaminated_then_rewritten_is_clean(self):
        # Scénario sort-mails : lecture d'un fichier contaminé, fusion,
        # réécriture — le fantôme ne survit à aucune des deux barrières.
        p = self.dir / "pending_emails.json"
        p.write_text(json.dumps({
            "_meta": {"schema_version": 2, "session_id": "s-old", "generated_at": "g"},
            "emails": [META_PHANTOM, EMAIL],
        }), encoding="utf-8")
        _meta, existing = read_v2_json(p, "emails")
        new_entry = dict(EMAIL, id="2026-07-07_09h00m00")
        write_v2_json(p, "emails", existing + [new_entry], "s-new")
        raw = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(raw["emails"], [EMAIL, new_entry])


if __name__ == "__main__":
    unittest.main()
