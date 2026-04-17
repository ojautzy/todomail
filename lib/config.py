"""Gestion du fichier .todomail-config.json (config au niveau du workspace).

Ce fichier, situe a la racine du repertoire de travail de l'utilisateur
(et non du plugin), stocke l'identite du serveur MCP attendu pour ce
workspace. Il permet a Claude de desambiguer quand plusieurs serveurs
archiva MCP sont connectes simultanement dans Claude Desktop.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.fs_utils import atomic_read_json, atomic_write_json


CONFIG_FILENAME = ".todomail-config.json"
SCHEMA_VERSION = 1


def config_path(workspace: Path) -> Path:
    """Return the path to the config file in a workspace directory."""
    return Path(workspace) / CONFIG_FILENAME


def load_config(workspace: Path) -> dict | None:
    """Load the workspace config, returning None if absent."""
    return atomic_read_json(config_path(workspace))


def save_config(workspace: Path, expected_rag_name: str) -> dict:
    """Create or update the workspace config with the expected rag_name.

    Returns the saved config dict.
    """
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "expected_rag_name": expected_rag_name,
        "configured_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_json(config_path(workspace), data)
    return data


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
