"""Tests des durcissements dashboard v2.4.0.

Couvre les quatre garde-fous issus du diagnostic du 2026-07-07 (processus
serveur au contexte dégradé servant des 403 muets et des catégories
faussement vides) :

1. `strict_io` (lib/fs_utils) : une lecture REFUSÉE (PermissionError) n'est
   plus assimilée à un fichier absent — elle est propagée à l'appelant.
2. `PathEscapeError` (lib/serve_dashboard) : la garde anti-traversée lève
   une classe dédiée, distincte des PermissionError du filesystem, pour que
   le serveur mappe évasion → 403 et panne d'E/S → 500.
3. `_read_plugin_version` : lecture de la version du plugin pour la
   détection de serveur périmé dans /api/poll.
4. Hook session_start : plus aucun slug fantôme dans `~/.config/todomail/`
   quand la session s'ouvre hors d'un workspace initialisé (marqueur
   `.todomail-config.json` absent).

Exécution depuis la racine du plugin :

    python3 -m unittest lib.tests.test_dashboard_hardening

Autonome (stdlib uniquement), aucune écriture hors tempdir
(`TODOMAIL_CONFIG_HOME` redirigé pour le test du hook).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Racine du plugin (lib/tests/ -> plugin)
_PLUGIN = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PLUGIN))

from lib.fs_utils import (  # noqa: E402
    atomic_read_json,
    read_pending_emails,
    read_v2_json,
)
from lib.serve_dashboard import (  # noqa: E402
    PathEscapeError,
    _read_plugin_version,
    resolve_under,
)


def _can_test_unreadable() -> bool:
    """chmod 000 est sans effet pour root : le test serait un faux positif."""
    return os.geteuid() != 0


class TestStrictIo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        # Restaure les droits pour que le cleanup du tempdir passe.
        for p in self.root.rglob("*"):
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass
        self._tmp.cleanup()

    def _unreadable_json(self, name: str = "pending_emails.json") -> Path:
        path = self.root / name
        path.write_text('{"_meta": {"schema_version": 2}, "emails": []}', encoding="utf-8")
        os.chmod(path, 0o000)
        return path

    def test_absent_vaut_none_dans_les_deux_modes(self):
        path = self.root / "absent.json"
        self.assertIsNone(atomic_read_json(path))
        self.assertIsNone(atomic_read_json(path, strict_io=True))

    def test_defaut_avale_la_lecture_refusee(self):
        if not _can_test_unreadable():
            self.skipTest("euid 0 : chmod 000 sans effet")
        path = self._unreadable_json()
        # Comportement historique conservé : None, pas d'exception.
        self.assertIsNone(atomic_read_json(path))

    def test_strict_propage_la_lecture_refusee(self):
        if not _can_test_unreadable():
            self.skipTest("euid 0 : chmod 000 sans effet")
        path = self._unreadable_json()
        with self.assertRaises(PermissionError):
            atomic_read_json(path, strict_io=True)

    def test_strict_traverse_read_v2_json_et_wrappers(self):
        if not _can_test_unreadable():
            self.skipTest("euid 0 : chmod 000 sans effet")
        self._unreadable_json()
        # Défaut : catégorie lue comme vide (historique).
        meta, emails = read_pending_emails(self.root)
        self.assertIsNone(meta)
        self.assertEqual(emails, [])
        # strict : la panne remonte.
        with self.assertRaises(PermissionError):
            read_pending_emails(self.root, strict_io=True)
        with self.assertRaises(PermissionError):
            read_v2_json(self.root / "pending_emails.json", "emails", strict_io=True)

    def test_json_corrompu_reste_none_en_strict(self):
        # Un JSON invalide est un problème de DONNÉES, pas d'infrastructure :
        # il ne doit pas lever, même en strict_io.
        path = self.root / "corrompu.json"
        path.write_text("{pas du json", encoding="utf-8")
        self.assertIsNone(atomic_read_json(path, strict_io=True))


class TestPathEscapeError(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def test_sous_classe_de_permission_error(self):
        # Compatibilité : tout code existant qui attrape PermissionError
        # continue d'attraper les évasions de chemin.
        self.assertTrue(issubclass(PathEscapeError, PermissionError))

    def test_evasion_leve_la_classe_dediee(self):
        with self.assertRaises(PathEscapeError):
            resolve_under(self.root, "todo", "..", "secret")
        with self.assertRaises(PathEscapeError):
            resolve_under(self.root, "a/b")

    def test_permission_error_fs_nest_pas_une_evasion(self):
        # Le mapping 403/500 du serveur repose sur cette distinction.
        self.assertFalse(isinstance(PermissionError(13, "denied"), PathEscapeError))


class TestReadPluginVersion(unittest.TestCase):
    def test_lit_la_version_du_manifeste(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp)
            (plugin / ".claude-plugin").mkdir()
            (plugin / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "todomail", "version": "9.9.9"}), encoding="utf-8"
            )
            self.assertEqual(_read_plugin_version(plugin), "9.9.9")

    def test_none_si_manifeste_illisible(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(_read_plugin_version(Path(tmp)))

    def test_version_du_plugin_reel(self):
        # Le serveur doit connaître sa propre version (fichier du dépôt).
        manifest = json.loads(
            (_PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(_read_plugin_version(_PLUGIN), manifest["version"])


class TestSessionStartGuard(unittest.TestCase):
    """Le hook session_start ne doit rien écrire hors d'un workspace initialisé."""

    HOOK = _PLUGIN / "hooks" / "session_start.py"

    def _run_hook(self, project: Path, config_home: Path) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project)
        env["TODOMAIL_CONFIG_HOME"] = str(config_home)
        payload = json.dumps({"session_id": "test", "source": "startup", "cwd": str(project)})
        return subprocess.run(
            [sys.executable, str(self.HOOK)],
            input=payload, capture_output=True, text=True, env=env, timeout=30,
        )

    def test_hors_workspace_aucun_slug_fantome(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "pas-un-workspace"
            project.mkdir()
            config_home = Path(tmp) / "config-home"
            res = self._run_hook(project, config_home)
            self.assertEqual(res.returncode, 0, res.stderr)
            # Ni slug machine-local, ni message « Reprise possible » parasite.
            self.assertFalse(config_home.exists() and any(config_home.iterdir()),
                             list(config_home.iterdir()) if config_home.exists() else None)
            self.assertEqual(res.stdout.strip(), "")

    def test_workspace_marque_ecrit_le_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "workspace"
            (project / "memory" / "people").mkdir(parents=True)
            (project / "memory" / "people" / "test.md").write_text("x", encoding="utf-8")
            (project / ".todomail-config.json").write_text(
                json.dumps({"schema_version": 4}), encoding="utf-8"
            )
            config_home = Path(tmp) / "config-home"
            res = self._run_hook(project, config_home)
            self.assertEqual(res.returncode, 0, res.stderr)
            caches = list(config_home.rglob("memory_cache.json"))
            self.assertEqual(len(caches), 1, caches)
            cache = json.loads(caches[0].read_text(encoding="utf-8"))
            self.assertIn("test", cache["entries"])


if __name__ == "__main__":
    unittest.main()
