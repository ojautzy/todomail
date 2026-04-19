"""Operations fichiers idempotentes et helpers JSON v2 pour TodoMail.

Toutes les operations sont safe-to-replay : elles ne font rien si l'etat
cible est deja atteint, et ne lancent pas d'exception dans ce cas.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Idempotent file operations
# ---------------------------------------------------------------------------

def safe_mv(src: Path, dst: Path) -> bool:
    """Move src to dst idempotently.

    Returns True if move was performed, False if nothing to do
    (src absent or dst already exists).
    """
    src, dst = Path(src), Path(dst)
    if not src.exists():
        return False
    # If dst is a directory that already contains the source name, skip
    target = dst / src.name if dst.is_dir() else dst
    if target.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return True


def safe_rm(path: Path) -> bool:
    """Remove file or directory idempotently.

    Returns True if removal was performed, False if path was already absent.
    """
    path = Path(path)
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def mkdir_p(path: Path) -> None:
    """Create directory and parents, no error if exists."""
    Path(path).mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically via .tmp + os.replace().

    Ensures no partial writes are visible. Creates parent dirs if needed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp), str(path))


def atomic_read_json(path: Path) -> Any | None:
    """Read JSON file, returning None if absent or empty."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return None
            return json.loads(content)
    except (json.JSONDecodeError, OSError):
        return None


def chmod_600(path: Path) -> bool:
    """Set file permissions to 0o600 (owner read/write only).

    Best-effort : returns False silently if the filesystem does not support
    POSIX permissions (Windows, some network mounts). Idempotent.
    """
    try:
        os.chmod(path, 0o600)
        return True
    except (OSError, NotImplementedError):
        return False


def is_already_in_destination(mail_id: str, dest_dir: Path) -> bool:
    """Check if a mail subdirectory already exists in destination."""
    return (Path(dest_dir) / mail_id).exists()


# ---------------------------------------------------------------------------
# JSON v2 schema helpers
# ---------------------------------------------------------------------------

def make_meta(session_id: str, consumes_session_id: str | None = None) -> dict:
    """Build a _meta wrapper for v2 JSON files."""
    meta = {
        "schema_version": 2,
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if consumes_session_id is not None:
        meta["consumes_session_id"] = consumes_session_id
    return meta


def read_v2_json(path: Path, data_key: str = "emails") -> tuple[dict | None, list]:
    """Read a v2 JSON file, returning (_meta, data_list).

    Supports both v1 (bare array) and v2 (object with _meta) formats.
    v1 bare array -> returns (None, array).
    v2 object     -> returns (_meta, obj[data_key]).
    Absent file   -> returns (None, []).
    """
    raw = atomic_read_json(path)
    if raw is None:
        return None, []
    if isinstance(raw, list):
        return None, raw
    if isinstance(raw, dict):
        meta = raw.get("_meta")
        data = raw.get(data_key, [])
        return meta, data
    return None, []


def write_v2_json(
    path: Path,
    data_key: str,
    data_list: list,
    session_id: str,
    consumes_session_id: str | None = None,
) -> None:
    """Write a v2 JSON file with _meta wrapper, atomically."""
    doc = {
        "_meta": make_meta(session_id, consumes_session_id),
        data_key: data_list,
    }
    atomic_write_json(path, doc)


# ---------------------------------------------------------------------------
# Convenience wrappers for pending_emails.json and instructions.json
# ---------------------------------------------------------------------------

def read_pending_emails(category_dir: Path) -> tuple[dict | None, list]:
    """Read pending_emails.json from a category directory."""
    return read_v2_json(Path(category_dir) / "pending_emails.json", "emails")


def write_pending_emails(category_dir: Path, emails: list, session_id: str) -> None:
    """Write pending_emails.json in v2 format."""
    write_v2_json(Path(category_dir) / "pending_emails.json", "emails", emails, session_id)


def read_instructions(category_dir: Path) -> tuple[dict | None, list]:
    """Read instructions.json from a category directory."""
    return read_v2_json(Path(category_dir) / "instructions.json", "instructions")


def write_instructions(
    category_dir: Path,
    instructions: list,
    session_id: str,
    consumes_session_id: str | None = None,
) -> None:
    """Write instructions.json in v2 format."""
    write_v2_json(
        Path(category_dir) / "instructions.json",
        "instructions",
        instructions,
        session_id,
        consumes_session_id,
    )
