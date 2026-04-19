"""imap_fetch.py — Téléchargement IMAP4 (STARTTLS) des nouveaux mails.

Module du skill fetch-imap. Porté depuis archiva-dev/scripts/check-inbox.py
avec les adaptations suivantes :

- Pas de `python-dotenv` : la configuration IMAP est injectée via `ImapConfig`
  (chargée par l'appelant depuis `.todomail-config.json` via `lib/config.py`).
- Pas de `subprocess` : appel direct à `eml_parser.write_json_alongside`.
- Logging optionnel vers `$WORKSPACE/.todomail/check_inbox.log` (best-effort).
- `fetch_inbox(inbox_dir, config) -> FetchReport` comme fonction publique ;
  le CLI `main()` est destiné aux tests manuels.

Pour chaque nouveau message :
  - Crée un sous-répertoire `inbox/<YYYY-MM-DD_HHhMMmSS>/`
  - Écrit `message.eml` + `message.json` + pièces jointes
  - Supprime le message côté serveur (UID MOVE Trash ou fallback)

Optimisations :
  - Utilise les UIDs (stables) + `.inbox_state.json` (uidvalidity + last_uid)
  - Supporte UID MOVE (RFC 6851) avec fallback COPY + STORE \\Deleted + EXPUNGE
"""

from __future__ import annotations

import argparse
import email
import email.policy
import email.utils
import imaplib
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from typing import Any

# Import local au skill (même répertoire)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eml_parser import write_json_alongside  # noqa: E402


STATE_FILE_NAME = ".inbox_state.json"

logger = logging.getLogger("fetch-imap")


# ── Dataclasses publiques ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ImapConfig:
    hostname: str
    port: int
    username: str
    password: str
    use_starttls: bool = True


@dataclass
class FetchedMessage:
    uid: str
    subject: str
    sender: str
    date: str
    attachments_count: int
    directory: str


@dataclass
class FetchReport:
    success: bool
    processed: int = 0
    errors: int = 0
    delete_failed: int = 0
    messages: list[FetchedMessage] = field(default_factory=list)
    inbox_path: str | None = None
    error: str | None = None

    def as_json(self) -> str:
        payload: dict[str, Any] = asdict(self)
        return json.dumps(payload, ensure_ascii=False, indent=2)


# ── Logging vers le workspace (best-effort) ──────────────────────────────────


def _install_workspace_logging() -> None:
    """Attache un FileHandler vers `$WORKSPACE/.todomail/check_inbox.log`.

    Silencieux si `lib.state.runtime_dir()` indisponible (ex : CLI standalone
    sans workspace).
    """
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    logger.addHandler(stream)
    try:
        from lib.state import runtime_dir  # lazy import (plugin-only)
        log_path = runtime_dir() / "check_inbox.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(fh)
    except Exception:
        pass


# ── UID state ────────────────────────────────────────────────────────────────


def _load_uid_state(directory: Path) -> dict | None:
    state_file = directory / STATE_FILE_NAME
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return {
            "uidvalidity": int(data.get("uidvalidity", 0)),
            "last_uid": int(data.get("last_uid", 0)),
        }
    except Exception as e:
        logger.warning("Fichier etat corrompu, reset : %s", e)
        return None


def _save_uid_state(directory: Path, uidvalidity: int, last_uid: int) -> None:
    state_file = directory / STATE_FILE_NAME
    state_file.write_text(
        json.dumps({
            "uidvalidity": uidvalidity,
            "last_uid": last_uid,
            "updated_at": datetime.now().isoformat(),
        }, indent=2),
        encoding="utf-8",
    )
    logger.info("Etat sauvegarde : uidvalidity=%d, last_uid=%d", uidvalidity, last_uid)


# ── Helpers filesystem ───────────────────────────────────────────────────────


def _make_timestamp_dirname(msg) -> str:
    date_str = msg.get("Date", "")
    if date_str:
        try:
            parsed_date = email.utils.parsedate_to_datetime(date_str)
            return parsed_date.strftime("%Y-%m-%d_%Hh%Mm%S")
        except Exception:
            pass
    return datetime.now().strftime("%Y-%m-%d_%Hh%Mm%S")


def _ensure_unique_dir(base_path: Path) -> Path:
    candidate = base_path
    counter = 1
    while candidate.exists():
        candidate = Path(f"{base_path}_{counter}")
        counter += 1
    return candidate


def _save_attachments(msg, dest_dir: Path) -> int:
    count = 0
    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        if "attachment" not in content_disposition:
            continue

        filename = part.get_filename()
        if not filename:
            continue

        decoded_parts = decode_header(filename)
        decoded_name = ""
        for data, charset in decoded_parts:
            if isinstance(data, bytes):
                decoded_name += data.decode(charset or "utf-8", errors="replace")
            else:
                decoded_name += data
        filename = decoded_name

        filename = filename.replace("/", "_").replace("\0", "")
        if not filename:
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        filepath = dest_dir / filename
        filepath.write_bytes(payload)
        logger.info("   Piece jointe : %s (%d octets)", filename, len(payload))
        count += 1
    return count


# ── IMAP ─────────────────────────────────────────────────────────────────────


def _connect_imap(config: ImapConfig) -> imaplib.IMAP4:
    imap = imaplib.IMAP4(config.hostname, config.port)
    if config.use_starttls:
        imap.starttls()
    imap.login(config.username, config.password)
    return imap


def _detect_capabilities(imap: imaplib.IMAP4) -> set[str]:
    try:
        status, data = imap.capability()
        if status == "OK" and data:
            caps = data[0].decode().upper().split()
            logger.info("Capacites IMAP : %s", " ".join(sorted(caps)))
            return set(caps)
    except Exception as e:
        logger.warning("Impossible de lire les capacites IMAP : %s", e)
    return set()


def _delete_message(imap: imaplib.IMAP4, uid: bytes, has_move: bool) -> bool:
    """Supprime un message via UID MOVE ou fallback COPY + STORE \\Deleted."""
    if has_move:
        try:
            status, _ = imap.uid("MOVE", uid, "Trash")
            if status == "OK":
                logger.info("   Message UID %s deplace vers Trash (MOVE)", uid.decode())
                return True
            logger.warning("   UID MOVE echec (status=%s), fallback", status)
        except imaplib.IMAP4.error as e:
            logger.warning("   UID MOVE erreur : %s, fallback", e)

    try:
        status, _ = imap.uid("COPY", uid, "Trash")
        if status != "OK":
            logger.warning(
                "   UID COPY vers Trash echec (status=%s), suppression directe",
                status,
            )
            status, _ = imap.uid("STORE", uid, "+FLAGS", "\\Deleted")
            if status != "OK":
                logger.error("   UID STORE \\Deleted echec (status=%s)", status)
                return False
            logger.info(
                "   Message UID %s marque pour suppression (sans Trash)",
                uid.decode(),
            )
            return True

        status, _ = imap.uid("STORE", uid, "+FLAGS", "\\Deleted")
        if status != "OK":
            logger.warning(
                "   UID STORE \\Deleted echec apres COPY (status=%s)", status,
            )
        logger.info(
            "   Message UID %s copie vers Trash et marque pour suppression",
            uid.decode(),
        )
        return True
    except imaplib.IMAP4.error as e:
        logger.error("   Erreur suppression message UID %s : %s", uid.decode(), e)
        return False


def _process_inbox(
    imap: imaplib.IMAP4,
    inbox_dir: Path,
    capabilities: set[str],
) -> tuple[int, int, int, list[FetchedMessage]]:
    """Boucle de téléchargement. Retourne (processed, errors, delete_failed, messages)."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    has_move = "MOVE" in capabilities

    status, data = imap.select("INBOX")
    if status != "OK":
        raise RuntimeError(f"Impossible d'ouvrir la boite de reception : {data}")

    uidvalidity = 0
    try:
        status_resp, status_data = imap.status("INBOX", "(UIDVALIDITY)")
        if status_resp == "OK" and status_data:
            resp_text = status_data[0].decode()
            match = re.search(r"UIDVALIDITY\s+(\d+)", resp_text)
            if match:
                uidvalidity = int(match.group(1))
                logger.info("UIDVALIDITY = %d", uidvalidity)
    except Exception as e:
        logger.warning("Impossible de lire UIDVALIDITY : %s", e)

    state = _load_uid_state(inbox_dir)
    last_uid = 0
    if state and uidvalidity > 0:
        if state["uidvalidity"] == uidvalidity:
            last_uid = state["last_uid"]
            logger.info("Reprise depuis UID %d (uidvalidity inchangee)", last_uid)
        else:
            logger.warning(
                "UIDVALIDITY a change (%d -> %d), full scan",
                state["uidvalidity"], uidvalidity,
            )

    if last_uid > 0:
        status, data = imap.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    else:
        status, data = imap.uid("SEARCH", None, "ALL")

    if status != "OK":
        raise RuntimeError("Erreur lors de la recherche des messages.")

    uids = data[0].split() if data[0] else []
    if last_uid > 0:
        uids = [u for u in uids if int(u) > last_uid]

    if not uids:
        logger.info("Aucun nouveau message dans la boite de reception.")
        if uidvalidity > 0 and last_uid > 0:
            _save_uid_state(inbox_dir, uidvalidity, last_uid)
        return 0, 0, 0, []

    logger.info("%d nouveau(x) message(s) trouve(s).", len(uids))

    processed = 0
    errors = 0
    delete_failed = 0
    messages: list[FetchedMessage] = []
    max_uid = last_uid

    for uid in uids:
        try:
            status, msg_data = imap.uid("FETCH", uid, "(RFC822)")
            if status != "OK":
                logger.error("Erreur telechargement UID %s", uid.decode())
                errors += 1
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email, policy=email.policy.default)

            subject = msg.get("Subject", "(sans sujet)")
            from_addr = msg.get("From", "(expediteur inconnu)")
            logger.info("Message UID %s : %s (de : %s)", uid.decode(), subject, from_addr)

            dirname = _make_timestamp_dirname(msg)
            msg_dir = _ensure_unique_dir(inbox_dir / dirname)
            msg_dir.mkdir(parents=True)

            eml_path = msg_dir / "message.eml"
            eml_path.write_bytes(raw_email)
            logger.info("   Enregistre : %s", eml_path)

            try:
                write_json_alongside(eml_path)
            except Exception as e:
                logger.warning("   Erreur eml_parser : %s", e)

            att_count = _save_attachments(msg, msg_dir)

            if not _delete_message(imap, uid, has_move):
                delete_failed += 1

            messages.append(FetchedMessage(
                uid=uid.decode(),
                subject=str(subject),
                sender=str(from_addr),
                date=msg.get("Date", ""),
                attachments_count=att_count,
                directory=str(msg_dir),
            ))

            uid_int = int(uid)
            if uid_int > max_uid:
                max_uid = uid_int
            processed += 1

        except Exception as e:
            logger.error("Erreur inattendue UID %s : %s", uid.decode(), e)
            errors += 1

    if not has_move or delete_failed > 0:
        try:
            status, _ = imap.expunge()
            if status == "OK":
                logger.info("EXPUNGE execute avec succes")
            else:
                logger.warning("EXPUNGE retourne status=%s", status)
        except Exception as e:
            logger.warning("Erreur EXPUNGE : %s", e)

    try:
        status, data = imap.uid("SEARCH", None, "ALL")
        if status == "OK" and data[0]:
            remaining = len(data[0].split())
            if remaining > 0:
                logger.warning(
                    "Post-verification : %d message(s) encore present(s) sur le serveur",
                    remaining,
                )
            else:
                logger.info("Post-verification : boite de reception vide, OK")
        else:
            logger.info("Post-verification : boite de reception vide, OK")
    except Exception as e:
        logger.warning("Erreur post-verification : %s", e)

    if uidvalidity > 0 and max_uid > 0:
        _save_uid_state(inbox_dir, uidvalidity, max_uid)

    logger.info(
        "Operation terminee : %d traite(s), %d erreur(s), %d suppression(s) echouee(s)",
        processed, errors, delete_failed,
    )
    return processed, errors, delete_failed, messages


# ── API publique ─────────────────────────────────────────────────────────────


def fetch_inbox(inbox_dir: Path, config: ImapConfig) -> FetchReport:
    """Point d'entrée principal. Ne lève jamais.

    Idempotent via `inbox_dir/.inbox_state.json` (uidvalidity + last_uid).
    """
    _install_workspace_logging()
    inbox_dir = Path(inbox_dir).resolve()
    logger.info(
        "Connexion a %s:%d en tant que %s...",
        config.hostname, config.port, config.username,
    )

    try:
        imap = _connect_imap(config)
    except Exception as e:
        logger.error("Connexion IMAP echouee : %s", e)
        return FetchReport(
            success=False,
            inbox_path=str(inbox_dir),
            error=f"Connexion IMAP echouee : {e}",
        )

    logger.info("Connecte.")
    capabilities = _detect_capabilities(imap)

    try:
        processed, errors, delete_failed, messages = _process_inbox(
            imap, inbox_dir, capabilities,
        )
        return FetchReport(
            success=True,
            processed=processed,
            errors=errors,
            delete_failed=delete_failed,
            messages=messages,
            inbox_path=str(inbox_dir),
        )
    except Exception as e:
        logger.error("Erreur traitement boite : %s", e)
        return FetchReport(
            success=False,
            inbox_path=str(inbox_dir),
            error=str(e),
        )
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ── CLI (tests manuels) ──────────────────────────────────────────────────────


def main() -> int:
    """CLI pour tests manuels : lit .todomail-config.json, appelle fetch_inbox."""
    parser = argparse.ArgumentParser(
        description="Telecharge les mails depuis un serveur IMAP4 (STARTTLS).",
    )
    parser.add_argument(
        "--workspace", default=None,
        help="Chemin du workspace (defaut : $CLAUDE_PROJECT_DIR ou cwd).",
    )
    args = parser.parse_args()

    # Import tardif : la CLI n'est appelée que depuis le plugin avec CLAUDE_PLUGIN_ROOT défini
    import os
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root and plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)

    try:
        from lib.state import workspace_dir
        from lib.config import load_config
    except ImportError as e:
        print(f"ERROR: impossible d'importer lib.* — CLAUDE_PLUGIN_ROOT non défini ? {e}",
              file=sys.stderr)
        return 1

    ws = Path(args.workspace) if args.workspace else workspace_dir()
    cfg = load_config(ws)
    if not cfg or not cfg.get("imap"):
        print("ERROR: IMAP non configuré dans .todomail-config.json — lance /todomail:start",
              file=sys.stderr)
        return 2

    imap_cfg = ImapConfig(**cfg["imap"])
    report = fetch_inbox(ws / "inbox", imap_cfg)
    print(report.as_json())
    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())
