"""Gestion du fichier .todomail-config.json (config au niveau du workspace).

Ce fichier, situe a la racine du repertoire de travail de l'utilisateur
(et non du plugin), stocke :
- l'identite du serveur MCP attendu pour ce workspace (champ
  `expected_rag_name`), pour desambiguer quand plusieurs serveurs archiva
  MCP sont connectes simultanement dans Claude Desktop ;
- depuis la v2.1.0, la configuration IMAP du plugin (bloc `imap`), qui
  remplace la dependance au tool MCP `check_inbox` pour le telechargement
  des mails.

Schema v2 (v2.1.0+) :

```json
{
  "schema_version": 2,
  "expected_rag_name": "Archiva-Pro",
  "configured_at": "2026-04-XX",
  "imap": {
    "hostname": "127.0.0.1",
    "port": 1143,
    "username": "user@example.com",
    "password": "...",
    "use_starttls": true
  }
}
```

Le fichier contient un mot de passe en clair ; les ecritures appliquent
`chmod 600` (best-effort). Il est gitignore dans le workspace utilisateur
(voir /todomail:start).

Migration transparente v1 -> v2 : un fichier `schema_version == 1` est
accepte en lecture (retourne tel quel sans bloc `imap`). L'ecriture
suivante (via /todomail:start etape 0c) bumpe la version en v2.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.fs_utils import atomic_read_json, atomic_write_json, chmod_600


CONFIG_FILENAME = ".todomail-config.json"
SCHEMA_VERSION = 2


def config_path(workspace: Path) -> Path:
    """Return the path to the config file in a workspace directory."""
    return Path(workspace) / CONFIG_FILENAME


def load_config(workspace: Path) -> dict | None:
    """Load the workspace config, returning None if absent.

    Accepts both schema v1 (no `imap` block) and v2 (with `imap` block).
    Callers that need the IMAP config must check `cfg.get("imap")`.
    """
    return atomic_read_json(config_path(workspace))


def _write_config(workspace: Path, data: dict) -> dict:
    """Internal: write the full config dict atomically and chmod 600."""
    path = config_path(workspace)
    atomic_write_json(path, data)
    chmod_600(path)
    return data


def save_config(workspace: Path, expected_rag_name: str) -> dict:
    """Create or update the workspace config with the expected rag_name.

    Preserves existing fields (notably `imap`) if the file already exists.
    Writes in schema v2 and sets 0o600 permissions on the file.

    Returns the saved config dict.
    """
    existing = load_config(workspace) or {}
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "expected_rag_name": expected_rag_name,
        "configured_at": datetime.now(timezone.utc).isoformat(),
    }
    if "imap" in existing:
        data["imap"] = existing["imap"]
    return _write_config(workspace, data)


def save_imap_config(
    workspace: Path,
    hostname: str,
    port: int,
    username: str,
    password: str,
    use_starttls: bool = True,
) -> dict:
    """Create or update the IMAP block in the workspace config.

    Preserves `expected_rag_name` and `configured_at` if present. Bumps
    the schema to v2 and sets 0o600 permissions on the file.

    Returns the saved config dict.
    """
    existing = load_config(workspace) or {}
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "expected_rag_name": existing.get("expected_rag_name"),
        "configured_at": existing.get(
            "configured_at",
            datetime.now(timezone.utc).isoformat(),
        ),
        "imap": {
            "hostname": hostname,
            "port": int(port),
            "username": username,
            "password": password,
            "use_starttls": bool(use_starttls),
        },
    }
    # Drop a None expected_rag_name to keep JSON tidy if never configured
    if data["expected_rag_name"] is None:
        del data["expected_rag_name"]
    return _write_config(workspace, data)


def check_rag_name(workspace: Path, actual_rag_name: str) -> tuple[bool, str | None]:
    """Verify that actual_rag_name matches the expected one.

    Returns (ok, expected):
    - ok = True and expected = None if the config is missing (caller should handle)
    - ok = True and expected = <name> if the actual matches the expected
    - ok = False and expected = <name> if there is a mismatch
    """
    cfg = load_config(workspace)
    if cfg is None:
        return True, None
    expected = cfg.get("expected_rag_name")
    if expected is None:
        return True, None
    return actual_rag_name == expected, expected
