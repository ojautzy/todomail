"""Cache de resultats RAG pour la session courante.

Evite les appels MCP redondants quand plusieurs mails concernent
le meme expediteur ou le meme sujet. Duree de vie = session courante,
vide en fin de cycle sort-mails / process-todo.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RagCache:
    """In-memory cache for RAG query results, scoped to one session."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(tool: str, query: str, **filters: Any) -> str:
        """Deterministic key from tool name, query and optional filters."""
        raw = f"{tool}|{query}|{json.dumps(filters, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, tool: str, query: str, **filters: Any) -> Any | None:
        """Return cached result or None on miss."""
        key = self._make_key(tool, query, **filters)
        result = self._store.get(key)
        if result is not None:
            self._hits += 1
        else:
            self._misses += 1
        return result

    def put(self, tool: str, query: str, result: Any, **filters: Any) -> None:
        """Store result in cache."""
        key = self._make_key(tool, query, **filters)
        self._store[key] = result

    def clear(self) -> None:
        """Clear the cache (call at end of cycle)."""
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict:
        """Return hit/miss statistics."""
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}

    def dump_for_observability(self, path: Path | None = None) -> None:
        """Serialize cache to JSON for debugging (read-only observability).

        Writes to `$CLAUDE_PROJECT_DIR/.todomail/rag_cache.json` if path is None.
        This snapshot is never read back; the cache lives only in memory.
        Aligne avec le refactor alpha.8 (tout le runtime dans .todomail/).
        """
        if path is None:
            env = os.environ.get("CLAUDE_PROJECT_DIR")
            if not env:
                return
            project = Path(env)
            if not project.is_dir():
                return
            path = project / ".todomail" / "rag_cache.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "dumped_at": datetime.now(timezone.utc).isoformat(),
            "stats": self.stats(),
            "keys": list(self._store.keys()),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
