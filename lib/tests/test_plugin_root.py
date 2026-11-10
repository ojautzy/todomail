"""Tests de la résolution de la racine du plugin sans `bin/` (v2.4.2).

Les plugins hébergés sur claude.ai refusent tout répertoire `bin/` de
premier niveau. La racine est désormais résolue par `_todomail_root()`
(préambule des blocs Python des commandes/skills) : variable
d'environnement, puis substitution inline de `${CLAUDE_PLUGIN_ROOT}` par
Claude Code, puis pointeur `~/.config/todomail/plugin_root` écrit par le
hook SessionStart.

Exécution depuis la racine du plugin :

    python3 -m unittest lib.tests.test_plugin_root

Autonome (stdlib uniquement), aucune écriture hors tempdir.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent.parent
MD_FILES = sorted(list((PLUGIN / "commands").glob("*.md"))
                  + list((PLUGIN / "skills").glob("*/SKILL.md")))
BLOCK_RE = re.compile(r"```bash\n(python3 - .*?<<'PY'\n.*?\nPY)\n```", re.S)
FUNC_RE = re.compile(r"def _todomail_root\(\):\n(?:    .*\n)+")


def _python_blocks():
    for md in MD_FILES:
        for m in BLOCK_RE.finditer(md.read_text(encoding="utf-8")):
            yield md, m.group(1)


def _clean_env(config_home: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    env["TODOMAIL_CONFIG_HOME"] = config_home
    return env


def _resolve(func_src: str, env: dict):
    """Exécute `_todomail_root()` extrait d'un bloc, dans un env contrôlé."""
    code = "import os, sys\n" + func_src + "print(_todomail_root())\n"
    return subprocess.run([sys.executable, "-I", "-c", code], env=env,
                          capture_output=True, text=True, cwd=tempfile.gettempdir())


class TestPackaging(unittest.TestCase):
    def test_pas_de_repertoire_bin(self):
        self.assertFalse((PLUGIN / "bin").exists(),
                         "bin/ est refusé par les plugins hébergés sur claude.ai")

    def test_plus_aucun_appel_a_todomail_plugin_root(self):
        for md in MD_FILES:
            text = md.read_text(encoding="utf-8")
            self.assertNotIn("$(todomail-plugin-root)", text, md)
            self.assertNotIn('shutil.which("todomail-plugin-root")', text, md)


def _frontmatter(path: Path) -> dict:
    """Parse minimal du frontmatter YAML (scalaires et blocs `>` / `|`)."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    out, key = {}, None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if km:
            key = km.group(1)
            val = km.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val.strip("\"'")
        elif key and line.startswith((" ", "\t")):
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


class TestValidationClaudeAi(unittest.TestCase):
    """Contraintes du validateur des plugins hébergés sur claude.ai (v2.4.2).

    Refus constatés à l'import : `bin/` de premier niveau, puis
    « SKILL.md description cannot contain XML tags » (fetch-imap :
    `inbox/<timestamp>/`). On applique aussi les règles connues des skills
    (nom kebab-case <= 64, mots réservés, description <= 1024) aux skills,
    commandes et agents.
    """

    FILES = sorted(list((PLUGIN / "skills").glob("*/SKILL.md"))
                   + list((PLUGIN / "commands").glob("*.md"))
                   + list((PLUGIN / "agents").glob("*.md")))
    TAG = re.compile(r"<[^>]*>|&lt;|&gt;")

    def test_manifeste_a_la_racine(self):
        self.assertTrue((PLUGIN / ".claude-plugin" / "plugin.json").is_file())

    def test_descriptions_sans_balise_et_bornees(self):
        for f in self.FILES:
            fm = _frontmatter(f)
            desc = fm.get("description", "")
            self.assertTrue(desc, f"{f}: description absente")
            self.assertLessEqual(len(desc), 1024, f"{f}: description > 1024 caractères")
            self.assertIsNone(self.TAG.search(desc), f"{f}: balise dans la description : {desc}")
            hint = fm.get("argument-hint", "")
            self.assertIsNone(self.TAG.search(hint), f"{f}: balise dans argument-hint")

    def test_noms_de_skills_et_agents(self):
        for f in self.FILES:
            if f.parent.name == "commands":
                continue
            name = _frontmatter(f).get("name", "")
            self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$", f)
            self.assertLessEqual(len(name), 64, f)
            self.assertNotRegex(name, r"claude|anthropic", f)
            if f.name == "SKILL.md":
                self.assertEqual(name, f.parent.name, f"{f}: name != nom du répertoire")


class TestPreambules(unittest.TestCase):
    def test_tout_bloc_lib_embarque_le_preambule(self):
        n = 0
        for md, block in _python_blocks():
            if "from lib" in block or "import lib" in block or "plugin_root" in block:
                n += 1
                self.assertIn("def _todomail_root():", block, md)
        self.assertGreaterEqual(n, 20)

    def test_preambules_identiques(self):
        funcs = {FUNC_RE.search(b).group(0) for _, b in _python_blocks() if "_todomail_root" in b}
        self.assertEqual(len(funcs), 1, "toutes les copies du préambule doivent être identiques")

    def _func(self):
        for _, block in _python_blocks():
            m = FUNC_RE.search(block)
            if m:
                return m.group(0)
        self.fail("aucun préambule trouvé")

    def test_echec_explicite_sans_aucune_source(self):
        with tempfile.TemporaryDirectory() as home:
            r = _resolve(self._func(), _clean_env(home))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("racine du plugin todomail introuvable", r.stderr)

    def test_pointeur_du_hook(self):
        with tempfile.TemporaryDirectory() as home:
            Path(home, "plugin_root").write_text(str(PLUGIN) + "\n", encoding="utf-8")
            r = _resolve(self._func(), _clean_env(home))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(PLUGIN))

    def test_pointeur_invalide_ignore(self):
        with tempfile.TemporaryDirectory() as home:
            Path(home, "plugin_root").write_text(home, encoding="utf-8")
            r = _resolve(self._func(), _clean_env(home))
        self.assertNotEqual(r.returncode, 0)

    def test_substitution_inline_prioritaire_sur_le_pointeur(self):
        func = self._func().replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
        with tempfile.TemporaryDirectory() as home:
            Path(home, "plugin_root").write_text("/nulle/part", encoding="utf-8")
            r = _resolve(func, _clean_env(home))
        self.assertEqual(r.stdout.strip(), str(PLUGIN), r.stderr)

    def test_variable_d_environnement(self):
        with tempfile.TemporaryDirectory() as home:
            env = _clean_env(home)
            env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
            r = _resolve(self._func(), env)
        self.assertEqual(r.stdout.strip(), str(PLUGIN), r.stderr)


class TestHookSessionStart(unittest.TestCase):
    def _run_hook(self, home, cwd):
        env = _clean_env(home)
        env.pop("CLAUDE_PROJECT_DIR", None)
        return subprocess.run(
            [sys.executable, str(PLUGIN / "hooks" / "session_start.py")],
            input=json.dumps({"cwd": cwd}), env=env, cwd=cwd,
            capture_output=True, text=True, timeout=20)

    def test_pointeur_ecrit_meme_hors_workspace(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
            self._run_hook(home, cwd)
            pointer = Path(home, "plugin_root")
            self.assertTrue(pointer.is_file())
            self.assertEqual(pointer.read_text(encoding="utf-8").strip(), str(PLUGIN))
            # aucun slug fantôme (garde v2.4.0 préservée)
            self.assertEqual([p.name for p in Path(home).iterdir()], ["plugin_root"])

    def test_pointeur_perime_mis_a_jour(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
            Path(home, "plugin_root").write_text("/ancienne/version\n", encoding="utf-8")
            self._run_hook(home, cwd)
            self.assertEqual(Path(home, "plugin_root").read_text(encoding="utf-8").strip(), str(PLUGIN))


class TestLanceursShell(unittest.TestCase):
    def test_read_odf_via_runpy(self):
        text = (PLUGIN / "skills" / "read-odf" / "SKILL.md").read_text(encoding="utf-8")
        block = BLOCK_RE.search(text).group(1).replace("<chemin_du_fichier>", "--help")
        with tempfile.TemporaryDirectory() as home:
            Path(home, "plugin_root").write_text(str(PLUGIN), encoding="utf-8")
            r = subprocess.run(["bash", "-c", block], env=_clean_env(home),
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("usage", r.stdout.lower())

    def test_lancement_serveur_dashboard_repli_pointeur(self):
        text = (PLUGIN / "commands" / "dashboard.md").read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.startswith("PLUGIN_ROOT=") or ln.startswith('[ -f "$PLUGIN_ROOT')]
        self.assertEqual(len(lines), 2, lines)
        script = "\n".join(lines) + '\necho "$PLUGIN_ROOT"\n'
        with tempfile.TemporaryDirectory() as home:
            Path(home, "plugin_root").write_text(str(PLUGIN), encoding="utf-8")
            r = subprocess.run(["bash", "-c", script], env=_clean_env(home),
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(r.stdout.strip(), str(PLUGIN), r.stderr)


if __name__ == "__main__":
    unittest.main()
