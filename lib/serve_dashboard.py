#!/usr/bin/env python3
"""Serveur HTTP du dashboard TodoMail (v2.2.0 — Phase 7).

Sert `dashboard.html` et expose une API JSON qui reproduit 1:1 les
operations que la version « File System Access » du dashboard faisait
directement dans le navigateur. Le filesystem reste le bus de messages
entre le dashboard et Claude : ce serveur ne fait que lire/ecrire les
memes fichiers (`instructions.json`, `.todomail/state.json`,
`invalidate.txt`, fichiers-marqueurs), en reutilisant `lib.fs_utils` et
`lib.state`. Il n'acquiert JAMAIS le verrou (seules les commandes Claude
le font) — il refuse simplement les ecritures (`409`) pendant qu'un cycle
Claude tourne.

Securite (mono-utilisateur, expose via Cloudflare Access) :
- bind `127.0.0.1` uniquement (cloudflared s'y connecte en loopback) ;
- validation du JWT Cloudflare Access (`Cf-Access-Jwt-Assertion`,
  RS256 + audience + emetteur) sur chaque requete `/api/*` ;
- garde anti-traversee de chemin (realpath confine au workspace) sur
  tout parametre de chemin.

Un acces direct a `http://127.0.0.1:<port>/api/...` (sans passer par
Cloudflare) renvoie donc `403` faute du header injecte par Access : il
n'existe qu'un seul point d'entree authentifie, le hostname public.

Usage :
    python3 -m lib.serve_dashboard --port 8770

Le mode `--no-auth` desactive la validation JWT : RESERVE aux tests
locaux en loopback, ne JAMAIS router une instance `--no-auth` dans le
tunnel Cloudflare.
"""

import argparse
import importlib
import json
import mimetypes
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Acces aux helpers lib/ (resolution cote Python, cf. CLAUDE.md)
_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _PLUGIN_ROOT and _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from lib.config import get_dashboard_config  # noqa: E402
from lib.fs_utils import (  # noqa: E402
    atomic_read_json,
    read_instructions,
    read_pending_emails,
    read_v2_json,
    safe_rm,
    write_instructions,
)
from lib.state import load_state, runtime_dir, workspace_dir  # noqa: E402


# ---------------------------------------------------------------------------
# Constantes domaine (miroir des SUBDIRS / sections du dashboard)
# ---------------------------------------------------------------------------

CATEGORIES = {
    "trash",
    "do-read-quick",
    "do-read-long",
    "do-decide",
    "do-consult-and-decide",
    "do-other",
    "do-self",
}
MEMORY_SECTIONS = {"people", "projects", "context"}
_SEGMENT_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


# ---------------------------------------------------------------------------
# Configuration serveur (resolue une fois au demarrage)
# ---------------------------------------------------------------------------

class ServerConfig:
    def __init__(self, workspace: Path, require_auth: bool, dashboard_cfg: dict | None):
        self.workspace = workspace.resolve()
        self.require_auth = require_auth
        cfg = dashboard_cfg or {}
        self.team_domain = cfg.get("team_domain")
        self.access_aud = cfg.get("access_aud")
        self._jwks_client = None  # PyJWKClient, lazy

    @property
    def issuer(self) -> str | None:
        if not self.team_domain:
            return None
        return f"https://{self.team_domain}.cloudflareaccess.com"

    @property
    def jwks_url(self) -> str | None:
        iss = self.issuer
        return f"{iss}/cdn-cgi/access/certs" if iss else None

    def jwks_client(self):
        """PyJWKClient paresseux (fetch + cache du JWKS de l'equipe)."""
        if self._jwks_client is None:
            from jwt import PyJWKClient

            self._jwks_client = PyJWKClient(self.jwks_url)
        return self._jwks_client


def _segment_ok(seg: str) -> bool:
    """Un segment de chemin sain : non vide, pas '..', allowlist stricte."""
    if not seg or seg == "." or seg == "..":
        return False
    return all(c in _SEGMENT_OK for c in seg)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class TodoMailHandler(BaseHTTPRequestHandler):
    server_version = "TodoMailDashboard/2.2"
    config: ServerConfig = None  # injecte par run()

    # --- garde anti-traversee -------------------------------------------------

    def safe_resolve(self, *parts: str) -> Path:
        """Resout un chemin sous le workspace, en rejetant toute evasion.

        - chaque segment passe l'allowlist (`_segment_ok`) ;
        - le chemin final est resolu via realpath (suit `..`/symlinks) puis
          verifie comme strictement contenu dans le workspace.
        """
        for p in parts:
            if not _segment_ok(p):
                raise PermissionError(f"segment invalide: {p!r}")
        root = self.config.workspace
        cand = root.joinpath(*parts).resolve()
        if cand != root and root not in cand.parents:
            raise PermissionError("chemin hors workspace")
        return cand

    # --- helpers reponse ------------------------------------------------------

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, msg: str, **extra) -> None:
        payload = {"ok": False, "error": msg}
        payload.update(extra)
        self._send_json(payload, status)

    def _send_bytes(self, data: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    # --- authentification (Cloudflare Access JWT) -----------------------------

    def _authorized(self) -> bool:
        """Valide le JWT Access ; renvoie False (et a deja repondu 403) sinon."""
        if not self.config.require_auth:
            return True
        token = self.headers.get("Cf-Access-Jwt-Assertion")
        if not token:
            self._send_error_json(403, "acces refuse: header Access manquant")
            return False
        try:
            import jwt

            signing_key = self.config.jwks_client().get_signing_key_from_jwt(token)
            jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.config.access_aud,
                issuer=self.config.issuer,
            )
            return True
        except Exception as exc:  # signature, audience, issuer, expiration…
            self._send_error_json(403, f"acces refuse: JWT invalide ({type(exc).__name__})")
            return False

    def _check_unlocked(self) -> bool:
        """Refuse (409) si un cycle Claude tient le verrou."""
        try:
            lock = load_state().get("active_lock")
        except Exception:
            lock = None
        if lock:
            self._send_error_json(409, "locked", lock=lock)
            return False
        return True

    # --- logging ------------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        try:
            line = "%s - - [%s] %s\n" % (
                self.address_string(),
                self.log_date_time_string(),
                fmt % args,
            )
            with open(runtime_dir() / "serve_dashboard.log", "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    # --- dispatch -----------------------------------------------------------

    def _segments(self):
        path = urlsplit(self.path).path
        return [unquote(s) for s in path.strip("/").split("/") if s != ""]

    def do_GET(self) -> None:  # noqa: N802
        segs = self._segments()
        try:
            if not segs:
                return self._serve_dashboard_html()
            if segs[0] != "api":
                # Tout chemin non-API non racine : 404 (pas de fichiers statiques).
                return self._send_error_json(404, "not found")
            if not self._authorized():
                return
            return self._route_api_get(segs[1:])
        except PermissionError as exc:
            self._send_error_json(403, str(exc))
        except FileNotFoundError:
            self._send_error_json(404, "not found")
        except Exception as exc:  # pragma: no cover - garde-fou
            self._send_error_json(500, f"{type(exc).__name__}: {exc}")

    def do_PUT(self) -> None:  # noqa: N802
        self._do_mutation("PUT")

    def do_POST(self) -> None:  # noqa: N802
        self._do_mutation("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._do_mutation("DELETE")

    def _do_mutation(self, method: str) -> None:
        segs = self._segments()
        try:
            if not segs or segs[0] != "api":
                return self._send_error_json(404, "not found")
            if not self._authorized():
                return
            if not self._check_unlocked():
                return
            return self._route_api_mutation(method, segs[1:])
        except PermissionError as exc:
            self._send_error_json(403, str(exc))
        except FileNotFoundError:
            self._send_error_json(404, "not found")
        except json.JSONDecodeError:
            self._send_error_json(400, "corps JSON invalide")
        except Exception as exc:  # pragma: no cover - garde-fou
            self._send_error_json(500, f"{type(exc).__name__}: {exc}")

    # --- routes GET ---------------------------------------------------------

    def _route_api_get(self, segs: list[str]) -> None:
        # /api/poll
        if segs == ["poll"]:
            return self._api_poll()
        # /api/categories
        if segs == ["categories"]:
            return self._api_categories()
        # /api/category/{cat}/emails
        if len(segs) == 3 and segs[0] == "category" and segs[2] == "emails":
            return self._api_category_emails(segs[1])
        # /api/category/{cat}/mail/{id}
        if len(segs) == 4 and segs[0] == "category" and segs[2] == "mail":
            return self._api_mail(segs[1], segs[3])
        # /api/category/{cat}/mail/{id}/file/{name}
        if len(segs) == 6 and segs[0] == "category" and segs[2] == "mail" and segs[4] == "file":
            return self._api_mail_file(segs[1], segs[3], segs[5])
        # /api/tasks/...
        if segs and segs[0] == "tasks":
            return self._route_tasks_get(segs[1:])
        # /api/memory/...
        if segs and segs[0] == "memory":
            return self._route_memory_get(segs[1:])
        return self._send_error_json(404, "route inconnue")

    def _route_tasks_get(self, segs: list[str]) -> None:
        if segs == ["counts"]:
            return self._api_tasks_counts()
        if segs == ["consult"]:
            return self._api_tasks_consult_get()
        if segs == ["to-send"]:
            return self._api_tasks_tosend_get()
        if segs == ["to-work"]:
            return self._api_tasks_towork_get()
        # /api/tasks/to-work/{dir}/file/{name}
        if len(segs) == 4 and segs[0] == "to-work" and segs[2] == "file":
            return self._api_tasks_towork_file(segs[1], segs[3])
        return self._send_error_json(404, "route tasks inconnue")

    def _route_memory_get(self, segs: list[str]) -> None:
        if segs == ["counts"]:
            return self._api_memory_counts()
        if len(segs) == 1:
            return self._api_memory_get(segs[0])
        return self._send_error_json(404, "route memory inconnue")

    # --- routes mutation ----------------------------------------------------

    def _route_api_mutation(self, method: str, segs: list[str]) -> None:
        # PUT /api/category/{cat}/instructions
        if (method == "PUT" and len(segs) == 3
                and segs[0] == "category" and segs[2] == "instructions"):
            return self._api_put_instructions(segs[1])
        # POST /api/markers/{retry|dismiss}
        if method == "POST" and len(segs) == 2 and segs[0] == "markers":
            return self._api_marker(segs[1])
        # /api/tasks/...
        if segs and segs[0] == "tasks":
            return self._route_tasks_mutation(method, segs[1:])
        # /api/memory/{section}/{name}
        if segs and segs[0] == "memory":
            return self._route_memory_mutation(method, segs[1:])
        return self._send_error_json(404, "route inconnue")

    def _route_tasks_mutation(self, method: str, segs: list[str]) -> None:
        if method == "PUT" and segs == ["consult"]:
            return self._api_tasks_consult_put()
        if len(segs) == 2 and segs[0] == "to-send":
            if method == "PUT":
                return self._api_tasks_tosend_put(segs[1])
            if method == "DELETE":
                return self._api_tasks_tosend_delete(segs[1])
        # PUT /api/tasks/to-work/{dir}/checklist
        if (method == "PUT" and len(segs) == 3
                and segs[0] == "to-work" and segs[2] == "checklist"):
            return self._api_tasks_towork_checklist_put(segs[1])
        # DELETE /api/tasks/to-work/{dir}
        if method == "DELETE" and len(segs) == 2 and segs[0] == "to-work":
            return self._api_tasks_towork_delete(segs[1])
        return self._send_error_json(404, "route tasks inconnue")

    def _route_memory_mutation(self, method: str, segs: list[str]) -> None:
        if len(segs) == 2:
            if method == "PUT":
                return self._api_memory_put(segs[0], segs[1])
            if method == "DELETE":
                return self._api_memory_delete(segs[0], segs[1])
        return self._send_error_json(404, "route memory inconnue")

    # =======================================================================
    # Implementations API
    # =======================================================================

    def _serve_dashboard_html(self) -> None:
        path = self.safe_resolve("dashboard.html")
        if not path.is_file():
            # Fallback : copie du plugin
            if _PLUGIN_ROOT:
                fallback = Path(_PLUGIN_ROOT) / "skills" / "dashboard.html"
                if fallback.is_file():
                    data = fallback.read_bytes()
                    return self._send_bytes(data, "text/html; charset=utf-8")
            return self._send_error_json(404, "dashboard.html introuvable")
        self._send_bytes(path.read_bytes(), "text/html; charset=utf-8")

    def _api_poll(self) -> None:
        state = load_state()
        inv = runtime_dir() / "invalidate.txt"
        stamp = int(inv.stat().st_mtime * 1000) if inv.exists() else None
        self._send_json({"invalidate_stamp": stamp, "state": state})

    def _api_categories(self) -> None:
        counts = {}
        for cat in CATEGORIES:
            try:
                _meta, emails = read_pending_emails(self.safe_resolve("todo", cat))
                counts[cat] = len(emails)
            except Exception:
                counts[cat] = 0
        self._send_json({"counts": counts})

    def _validate_category(self, cat: str) -> None:
        if cat not in CATEGORIES:
            raise PermissionError(f"categorie inconnue: {cat}")

    def _api_category_emails(self, cat: str) -> None:
        self._validate_category(cat)
        cat_dir = self.safe_resolve("todo", cat)
        pending_meta, emails = read_pending_emails(cat_dir)
        instr_meta, instructions = read_instructions(cat_dir)
        self._send_json({
            "emails": emails,
            "pending_meta": pending_meta,
            "instructions": instructions,
            "instructions_meta": instr_meta,
        })

    def _api_put_instructions(self, cat: str) -> None:
        self._validate_category(cat)
        body = self._read_json_body()
        instructions = body.get("instructions")
        if not isinstance(instructions, list):
            return self._send_error_json(400, "champ 'instructions' (liste) requis")
        cat_dir = self.safe_resolve("todo", cat)
        if not cat_dir.is_dir():
            return self._send_error_json(404, "categorie absente")
        session_id = load_state().get("session_id") or "dashboard"
        write_instructions(cat_dir, instructions, session_id)
        self._send_json({"ok": True, "count": len(instructions)})

    def _api_mail(self, cat: str, mail_id: str) -> None:
        self._validate_category(cat)
        mail_dir = self.safe_resolve("todo", cat, mail_id)
        if not mail_dir.is_dir():
            return self._send_error_json(404, "mail introuvable")
        mail = atomic_read_json(mail_dir / "message.json") or {}
        attachments = sorted(
            p.name for p in mail_dir.iterdir()
            if p.is_file() and not p.name.endswith(".json") and not p.name.endswith(".eml")
        )
        self._send_json({"mail": mail, "attachments": attachments})

    def _api_mail_file(self, cat: str, mail_id: str, name: str) -> None:
        self._validate_category(cat)
        path = self.safe_resolve("todo", cat, mail_id, name)
        if not path.is_file():
            return self._send_error_json(404, "fichier introuvable")
        ctype, _ = mimetypes.guess_type(name)
        self._send_bytes(path.read_bytes(), ctype or "application/octet-stream", filename=name)

    def _api_marker(self, kind: str) -> None:
        body = self._read_json_body()
        rt = runtime_dir()
        if kind == "retry":
            ids = body.get("mail_ids") or []
            content = ("\n".join(str(i) for i in ids) + "\n") if ids else ""
            (rt / "retry_request.txt").write_text(content, encoding="utf-8")
            return self._send_json({"ok": True, "count": len(ids)})
        if kind == "dismiss":
            mail_id = body.get("mail_id")
            if not mail_id:
                return self._send_error_json(400, "champ 'mail_id' requis")
            path = rt / "errors_dismiss.txt"
            existing = []
            if path.exists():
                existing = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if mail_id not in existing:
                existing.append(mail_id)
            path.write_text("\n".join(existing) + "\n", encoding="utf-8")
            return self._send_json({"ok": True})
        self._send_error_json(404, "marqueur inconnu")

    # --- tasks --------------------------------------------------------------

    def _count_consult(self, text: str) -> int:
        rows = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
        return max(0, len(rows) - 2)

    def _api_tasks_counts(self) -> None:
        ws = self.config.workspace
        consult = 0
        consult_path = ws / "consult.md"
        if consult_path.is_file():
            consult = self._count_consult(consult_path.read_text(encoding="utf-8"))
        to_send = 0
        ts_dir = ws / "to-send"
        if ts_dir.is_dir():
            to_send = sum(1 for p in ts_dir.iterdir() if p.is_file() and p.name.endswith(".md"))
        to_work = 0
        tw_dir = ws / "to-work"
        if tw_dir.is_dir():
            to_work = sum(1 for p in tw_dir.iterdir() if p.is_dir())
        self._send_json({"counts": {"consult": consult, "to-send": to_send, "to-work": to_work}})

    def _api_tasks_consult_get(self) -> None:
        path = self.config.workspace / "consult.md"
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        self._send_json({"content": content})

    def _api_tasks_consult_put(self) -> None:
        body = self._read_json_body()
        content = body.get("content", "")
        (self.config.workspace / "consult.md").write_text(content, encoding="utf-8")
        self._send_json({"ok": True})

    def _api_tasks_tosend_get(self) -> None:
        ts_dir = self.config.workspace / "to-send"
        files = []
        if ts_dir.is_dir():
            for p in sorted(ts_dir.iterdir(), key=lambda x: x.name):
                if p.is_file() and p.name.endswith(".md"):
                    files.append({"filename": p.name, "content": p.read_text(encoding="utf-8")})
        self._send_json({"files": files})

    def _api_tasks_tosend_put(self, name: str) -> None:
        if not name.endswith(".md"):
            return self._send_error_json(400, "nom .md attendu")
        body = self._read_json_body()
        path = self.safe_resolve("to-send", name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.get("content", ""), encoding="utf-8")
        self._send_json({"ok": True})

    def _api_tasks_tosend_delete(self, name: str) -> None:
        path = self.safe_resolve("to-send", name)
        safe_rm(path)
        self._send_json({"ok": True})

    def _api_tasks_towork_get(self) -> None:
        tw_dir = self.config.workspace / "to-work"
        tasks = []
        if tw_dir.is_dir():
            for d in sorted(tw_dir.iterdir(), key=lambda x: x.name):
                if not d.is_dir():
                    continue
                checklist = ""
                documents = []
                for f in d.iterdir():
                    if not f.is_file():
                        continue
                    if f.name == "checklist.md":
                        checklist = f.read_text(encoding="utf-8")
                    else:
                        documents.append(f.name)
                tasks.append({
                    "dirName": d.name,
                    "checklist": checklist,
                    "documents": sorted(documents),
                })
        self._send_json({"tasks": tasks})

    def _api_tasks_towork_checklist_put(self, dirname: str) -> None:
        body = self._read_json_body()
        task_dir = self.safe_resolve("to-work", dirname)
        if not task_dir.is_dir():
            return self._send_error_json(404, "tache introuvable")
        (task_dir / "checklist.md").write_text(body.get("content", ""), encoding="utf-8")
        self._send_json({"ok": True})

    def _api_tasks_towork_delete(self, dirname: str) -> None:
        path = self.safe_resolve("to-work", dirname)
        safe_rm(path)
        self._send_json({"ok": True})

    def _api_tasks_towork_file(self, dirname: str, name: str) -> None:
        path = self.safe_resolve("to-work", dirname, name)
        if not path.is_file():
            return self._send_error_json(404, "fichier introuvable")
        ctype, _ = mimetypes.guess_type(name)
        self._send_bytes(path.read_bytes(), ctype or "application/octet-stream", filename=name)

    # --- memory -------------------------------------------------------------

    def _api_memory_counts(self) -> None:
        ws = self.config.workspace
        counts = {"claude": 1 if (ws / "CLAUDE.md").is_file() else 0}
        for sec in ("people", "projects", "context"):
            d = ws / "memory" / sec
            counts[sec] = (
                sum(1 for p in d.iterdir() if p.is_file() and p.name.endswith(".md"))
                if d.is_dir() else 0
            )
        self._send_json({"counts": counts})

    def _api_memory_get(self, section: str) -> None:
        if section == "claude":
            path = self.config.workspace / "CLAUDE.md"
            files = []
            if path.is_file():
                files.append({"name": "CLAUDE.md", "path": "CLAUDE.md",
                              "content": path.read_text(encoding="utf-8")})
            return self._send_json({"files": files})
        if section not in MEMORY_SECTIONS:
            raise PermissionError(f"section inconnue: {section}")
        d = self.safe_resolve("memory", section)
        files = []
        if d.is_dir():
            for p in sorted(d.iterdir(), key=lambda x: x.name):
                if p.is_file() and p.name.endswith(".md"):
                    files.append({
                        "name": p.name,
                        "path": f"memory/{section}/{p.name}",
                        "content": p.read_text(encoding="utf-8"),
                    })
        self._send_json({"files": files})

    def _api_memory_put(self, section: str, name: str) -> None:
        body = self._read_json_body()
        content = body.get("content", "")
        if section == "claude":
            (self.config.workspace / "CLAUDE.md").write_text(content, encoding="utf-8")
            return self._send_json({"ok": True})
        if section not in MEMORY_SECTIONS:
            raise PermissionError(f"section inconnue: {section}")
        if not name.endswith(".md"):
            return self._send_error_json(400, "nom .md attendu")
        path = self.safe_resolve("memory", section, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._send_json({"ok": True})

    def _api_memory_delete(self, section: str, name: str) -> None:
        if section == "claude":
            return self._send_error_json(403, "CLAUDE.md non supprimable")
        if section not in MEMORY_SECTIONS:
            raise PermissionError(f"section inconnue: {section}")
        path = self.safe_resolve("memory", section, name)
        safe_rm(path)
        self._send_json({"ok": True})


# ---------------------------------------------------------------------------
# Entree
# ---------------------------------------------------------------------------

def _ensure_pyjwt() -> bool:
    """Garantit que PyJWT est importable ; tente une auto-install sinon.

    Cas « lancement direct / LaunchAgent » (sans passer par /todomail:dashboard
    qui pre-installe la dependance) : si PyJWT manque, on tente UNE installation
    dans CE meme interpreteur (`sys.executable`, donc le bon python) avant
    d'abandonner. Best-effort, journalise. Desactivable via
    `TODOMAIL_NO_AUTOINSTALL=1` pour qui ne veut pas qu'un service touche a son
    environnement Python.
    """
    try:
        import jwt  # noqa: F401
        return True
    except ImportError:
        pass
    if os.environ.get("TODOMAIL_NO_AUTOINSTALL"):
        return False
    print(
        '[todomail] PyJWT absent — installation automatique '
        '(python3 -m pip install --break-system-packages "PyJWT[crypto]")...',
        flush=True,
    )
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--break-system-packages", "PyJWT[crypto]"],
            check=False,
        )
        importlib.invalidate_caches()
        import jwt  # noqa: F401
        return True
    except Exception:
        return False


def build_config(require_auth: bool) -> ServerConfig:
    ws = workspace_dir()
    dash = get_dashboard_config(ws)
    cfg = ServerConfig(ws, require_auth, dash)
    if require_auth:
        missing = [k for k in ("team_domain", "access_aud") if not getattr(cfg, k)]
        if missing:
            raise SystemExit(
                "ERREUR: configuration Cloudflare Access incomplete "
                f"(manquant: {', '.join(missing)}). Lance /todomail:dashboard "
                "pour la renseigner, ou utilise --no-auth pour un test local."
            )
        if not _ensure_pyjwt():
            raise SystemExit(
                'ERREUR: PyJWT requis pour la validation Access, et auto-install '
                'impossible (reseau ? droits ?). Installe-le dans CE python : '
                'python3 -m pip install --break-system-packages "PyJWT[crypto]"'
            )
    return cfg


def run(port: int = 8770, host: str = "127.0.0.1", require_auth: bool = True) -> None:
    cfg = build_config(require_auth)
    TodoMailHandler.config = cfg
    httpd = ThreadingHTTPServer((host, port), TodoMailHandler)
    httpd.daemon_threads = True
    mode = "Cloudflare Access (JWT)" if require_auth else "SANS AUTH (test local)"
    print(f"[todomail] dashboard servi sur http://{host}:{port}  | auth: {mode}", flush=True)
    print(f"[todomail] workspace: {cfg.workspace}", flush=True)
    if not require_auth:
        print("[todomail] AVERTISSEMENT: mode --no-auth — NE JAMAIS router dans le tunnel Cloudflare.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur HTTP du dashboard TodoMail")
    parser.add_argument("--port", type=int, default=8770, help="port d'ecoute (defaut 8770)")
    parser.add_argument("--host", default="127.0.0.1", help="adresse de bind (defaut 127.0.0.1)")
    parser.add_argument(
        "--no-auth", action="store_true",
        help="desactive la validation JWT (TEST LOCAL uniquement, jamais expose)",
    )
    args = parser.parse_args()
    run(port=args.port, host=args.host, require_auth=not args.no_auth)


if __name__ == "__main__":
    main()
