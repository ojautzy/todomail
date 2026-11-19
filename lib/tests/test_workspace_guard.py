"""Tests de la garde « espace de travail todomail » (v2.4.4).

Le plugin se charge dans toutes les sessions Claude Code : hors d'un
workspace marqué (`.todomail-config.json`), rien ne doit être créé.
Couvre :

1. `lib.workspace` : `is_todomail_workspace`, `resolve_workspace`,
   `hook_workspace` (critère unique, aucune création).
2. `lib.state.workspace_dir()` : `$CLAUDE_PROJECT_DIR` n'est plus accepté
   sans marqueur ; repli sur le cwd marqué ; message d'erreur explicite
   invitant à lancer /todomail:start ; aucun `.todomail/` créé.
3. `lib.rag_cache.RagCache.dump_for_observability()` : no-op hors workspace.

Exécution depuis la racine du plugin :

    python3 -m unittest lib.tests.test_workspace_guard

Autonome (stdlib uniquement), aucune écriture hors tempdir.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PLUGIN = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PLUGIN))

from lib import state  # noqa: E402
from lib.rag_cache import RagCache  # noqa: E402
from lib.workspace import (  # noqa: E402
    MARKER_FILENAME,
    hook_workspace,
    is_todomail_workspace,
    resolve_workspace,
)


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


class _TmpDirs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.ws = base / "workspace"
        self.foreign = base / "projet-sans-rapport"
        self.ws.mkdir()
        self.foreign.mkdir()
        (self.ws / MARKER_FILENAME).write_text("{}", encoding="utf-8")
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()


class TestCritere(_TmpDirs):
    def test_marqueur_present(self):
        self.assertTrue(is_todomail_workspace(self.ws))
        self.assertTrue(is_todomail_workspace(str(self.ws)))

    def test_marqueur_absent_ou_vide(self):
        self.assertFalse(is_todomail_workspace(self.foreign))
        self.assertFalse(is_todomail_workspace(None))
        self.assertFalse(is_todomail_workspace(""))
        self.assertFalse(is_todomail_workspace(self.foreign / "inexistant"))

    def test_marqueur_repertoire_refuse(self):
        (self.foreign / MARKER_FILENAME).mkdir()
        self.assertFalse(is_todomail_workspace(self.foreign))

    def test_resolve_premier_candidat_marque(self):
        self.assertEqual(resolve_workspace(None, self.foreign, self.ws), self.ws)
        self.assertIsNone(resolve_workspace(self.foreign, "", None))

    def test_hook_workspace_env_prioritaire(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.ws)}):
            self.assertEqual(hook_workspace({"cwd": str(self.foreign)}), self.ws)
        # Même candidat qu'avant v2.4.4 : env non marqué => inerte, pas de
        # repli silencieux sur la cwd du payload.
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.foreign)}):
            self.assertIsNone(hook_workspace({"cwd": str(self.ws)}))

    def test_hook_workspace_cwd_payload(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(hook_workspace({"cwd": str(self.ws)}), self.ws)
            self.assertIsNone(hook_workspace({"cwd": str(self.foreign)}))
            self.assertIsNone(hook_workspace({}))
            self.assertIsNone(hook_workspace(None))


class TestWorkspaceDir(_TmpDirs):
    def test_env_marque_accepte(self):
        os.chdir(self.foreign)
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.ws)}):
            self.assertEqual(state.workspace_dir(), self.ws)

    def test_env_non_marque_refuse_sans_rien_creer(self):
        os.chdir(self.foreign)
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.foreign)}):
            with self.assertRaises(RuntimeError) as ctx:
                state.workspace_dir()
            with self.assertRaises(RuntimeError):
                state.load_state()
        msg = str(ctx.exception)
        self.assertIn("/todomail:start", msg)
        self.assertIn(MARKER_FILENAME, msg)
        self.assertEqual(_tree(self.foreign), [])

    def test_env_non_marque_repli_cwd_marque(self):
        os.chdir(self.ws)
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.foreign)}):
            self.assertEqual(Path(state.workspace_dir()).resolve(), self.ws.resolve())

    def test_sans_env_cwd_marque(self):
        os.chdir(self.ws)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(Path(state.workspace_dir()).resolve(), self.ws.resolve())

    def test_workspace_marque_cree_le_state(self):
        os.chdir(self.foreign)
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.ws)}):
            state.load_state()
        self.assertTrue((self.ws / ".todomail" / "state.json").is_file())
        self.assertTrue((self.ws / ".todomail" / "invalidate.txt").is_file())


class TestRagCacheDump(_TmpDirs):
    def test_dump_hors_workspace_noop(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.foreign)}):
            RagCache().dump_for_observability()
        self.assertEqual(_tree(self.foreign), [])

    def test_dump_dans_workspace(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.ws)}):
            RagCache().dump_for_observability()
        self.assertTrue((self.ws / ".todomail" / "rag_cache.json").is_file())


if __name__ == "__main__":
    unittest.main()
