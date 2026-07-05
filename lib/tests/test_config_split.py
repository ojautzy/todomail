"""Tests du split config partagée / machine-locale (v2.3.0, Phase 8).

Exécution depuis la racine du plugin :

    python3 -m unittest lib.tests.test_config_split

Autonome (stdlib uniquement). Chaque test travaille dans un répertoire
temporaire : `TODOMAIL_CONFIG_HOME` pointe vers un faux home local et le
workspace est un répertoire `tmp` jetable — aucune écriture hors tempdir.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

# Racine du plugin (lib/tests/ -> plugin)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib import config as cfg  # noqa: E402


IMAP_A = {
    "hostname": "127.0.0.1",
    "port": 1143,
    "username": "user@example.com",
    "password": "secret-mac-A",
    "use_starttls": True,
}
DASHBOARD_A = {
    "port": 8770,
    "hostname": "todomail.example.com",
    "team_domain": "example",
    "access_aud": "aud-tag",
}


class ConfigSplitTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.workspace = base / "workspace"
        self.workspace.mkdir()
        self.config_home = base / "config-home"
        self._old_home = os.environ.get("TODOMAIL_CONFIG_HOME")
        os.environ["TODOMAIL_CONFIG_HOME"] = str(self.config_home)

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("TODOMAIL_CONFIG_HOME", None)
        else:
            os.environ["TODOMAIL_CONFIG_HOME"] = self._old_home
        self._tmp.cleanup()

    # --- helpers ------------------------------------------------------------

    def write_shared_v3(self, imap=None, dashboard=None):
        data = {
            "schema_version": 3,
            "expected_rag_name": "Archiva-Test",
            "configured_at": "2026-01-01T00:00:00+00:00",
        }
        if imap is not None:
            data["imap"] = imap
        if dashboard is not None:
            data["dashboard"] = dashboard
        path = cfg.config_path(self.workspace)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def read_shared(self):
        return json.loads(cfg.config_path(self.workspace).read_text(encoding="utf-8"))

    def read_local(self):
        return json.loads(cfg.local_config_path(self.workspace).read_text(encoding="utf-8"))

    # --- 1. split écriture ----------------------------------------------------

    def test_save_imap_config_writes_local_only(self):
        self.write_shared_v3()
        cfg.save_imap_config(self.workspace, **IMAP_A)

        # Rien dans le fichier partagé
        shared = self.read_shared()
        self.assertNotIn("imap", shared)
        self.assertNotIn("password", json.dumps(shared))

        # Le bloc est dans le fichier local, en 0o600
        local_path = cfg.local_config_path(self.workspace)
        self.assertTrue(local_path.is_file())
        mode = stat.S_IMODE(local_path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        local = self.read_local()
        self.assertEqual(local["imap"]["password"], "secret-mac-A")
        self.assertEqual(local["schema_version"], cfg.LOCAL_SCHEMA_VERSION)

    def test_local_dir_mode_700(self):
        d = cfg.local_config_dir(self.workspace)
        self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700)

    def test_save_dashboard_preserves_local_imap(self):
        cfg.save_imap_config(self.workspace, **IMAP_A)
        cfg.save_dashboard_config(self.workspace, **DASHBOARD_A)
        local = self.read_local()
        self.assertEqual(local["imap"]["password"], "secret-mac-A")
        self.assertEqual(local["dashboard"]["port"], 8770)

    # --- 2. vue fusionnée -------------------------------------------------------

    def test_load_config_merged_view(self):
        legacy_imap = dict(IMAP_A, password="secret-legacy")
        self.write_shared_v3(imap=legacy_imap)
        cfg.save_imap_config(self.workspace, **IMAP_A)

        merged = cfg.load_config(self.workspace)
        self.assertEqual(merged["expected_rag_name"], "Archiva-Test")
        # Précédence : local > legacy partagé
        self.assertEqual(merged["imap"]["password"], "secret-mac-A")

    def test_load_config_none_when_shared_absent(self):
        cfg.save_imap_config(self.workspace, **IMAP_A)
        self.assertIsNone(cfg.load_config(self.workspace))
        # Mais get_imap_config résout quand même le bloc local
        self.assertEqual(
            cfg.get_imap_config(self.workspace)["password"], "secret-mac-A"
        )

    # --- 3. migration -----------------------------------------------------------

    def test_migrate_full_v3(self):
        self.write_shared_v3(imap=IMAP_A, dashboard=DASHBOARD_A)
        report = cfg.migrate_legacy_config(self.workspace)
        self.assertFalse(report["already_clean"])
        self.assertCountEqual(report["migrated"], ["imap", "dashboard"])

        shared = self.read_shared()
        self.assertEqual(shared["schema_version"], cfg.SCHEMA_VERSION)
        self.assertNotIn("imap", shared)
        self.assertNotIn("dashboard", shared)
        self.assertNotIn("password", json.dumps(shared))
        self.assertEqual(shared["expected_rag_name"], "Archiva-Test")

        local = self.read_local()
        self.assertEqual(local["imap"]["password"], "secret-mac-A")
        self.assertEqual(local["dashboard"]["access_aud"], "aud-tag")

        # Ré-exécution = no-op
        report2 = cfg.migrate_legacy_config(self.workspace)
        self.assertTrue(report2["already_clean"])
        self.assertEqual(report2["migrated"], [])

    # --- 4. migration avec local pré-existant ------------------------------------

    def test_migrate_does_not_overwrite_local(self):
        cfg.save_imap_config(self.workspace, **IMAP_A)  # mot de passe de CE mac
        legacy = dict(IMAP_A, password="secret-autre-mac")
        self.write_shared_v3(imap=legacy)

        report = cfg.migrate_legacy_config(self.workspace)
        self.assertFalse(report["already_clean"])
        self.assertEqual(report["migrated"], [])  # rien copié : le local gagne

        local = self.read_local()
        self.assertEqual(local["imap"]["password"], "secret-mac-A")
        self.assertNotIn("migrated_from_legacy", local["imap"])
        # Le partagé est bien purgé malgré tout
        self.assertNotIn("imap", self.read_shared())

    # --- 4bis. flag de migration ---------------------------------------------------

    def test_migration_flag_then_resave_clears_it(self):
        self.write_shared_v3(imap=IMAP_A)
        cfg.migrate_legacy_config(self.workspace)
        local = self.read_local()
        self.assertTrue(local["imap"]["migrated_from_legacy"])

        # Ressaisie via save_imap_config → flag effacé
        cfg.save_imap_config(self.workspace, **dict(IMAP_A, password="nouveau"))
        local = self.read_local()
        self.assertNotIn("migrated_from_legacy", local["imap"])
        self.assertEqual(local["imap"]["password"], "nouveau")

    # --- 5. fallback legacy en lecture ----------------------------------------------

    def test_get_imap_config_legacy_fallback(self):
        self.write_shared_v3(imap=IMAP_A, dashboard=DASHBOARD_A)
        imap = cfg.get_imap_config(self.workspace)
        self.assertEqual(imap["password"], "secret-mac-A")
        dash = cfg.get_dashboard_config(self.workspace)
        self.assertEqual(dash["port"], 8770)

    def test_get_imap_config_none_when_nothing(self):
        self.write_shared_v3()
        self.assertIsNone(cfg.get_imap_config(self.workspace))
        self.assertIsNone(cfg.get_dashboard_config(self.workspace))

    # --- 6. slug ---------------------------------------------------------------------

    def test_slug_distinct_for_same_basename(self):
        base = Path(self._tmp.name)
        ws_a = base / "a" / "DIRMC"
        ws_b = base / "b" / "DIRMC"
        ws_a.mkdir(parents=True)
        ws_b.mkdir(parents=True)
        slug_a = cfg.workspace_slug(ws_a)
        slug_b = cfg.workspace_slug(ws_b)
        self.assertNotEqual(slug_a, slug_b)
        self.assertTrue(slug_a.startswith("DIRMC-"))
        self.assertTrue(slug_b.startswith("DIRMC-"))

    # --- divers : save_config migre d'abord -------------------------------------------

    def test_save_config_purges_legacy_via_migration(self):
        self.write_shared_v3(imap=IMAP_A)
        cfg.save_config(self.workspace, "Archiva-Nouveau")
        shared = self.read_shared()
        self.assertEqual(shared["schema_version"], cfg.SCHEMA_VERSION)
        self.assertEqual(shared["expected_rag_name"], "Archiva-Nouveau")
        self.assertNotIn("imap", shared)
        # Le secret a bien été préservé côté local
        self.assertEqual(self.read_local()["imap"]["password"], "secret-mac-A")


if __name__ == "__main__":
    unittest.main()
