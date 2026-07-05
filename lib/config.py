"""Gestion de la configuration TodoMail : partagée (workspace) et machine-locale.

Depuis la v2.3.0, la configuration est séparée en deux niveaux pour
supporter un workspace synchronisé entre plusieurs macs (iCloud Drive) :

**Fichier partagé** `.todomail-config.json` (racine du workspace, schéma v4) —
synchronisé iCloud, ne contient AUCUN secret. Il sert aussi de marqueur de
détection du workspace pour `lib.state.workspace_dir()` : ne jamais le
supprimer ni le déplacer.

```json
{
  "schema_version": 4,
  "expected_rag_name": "Archiva-Pro",
  "configured_at": "2026-07-05T12:34:56+00:00"
}
```

**Fichier local** `~/.config/todomail/<slug>/config.json` (schéma local v1,
indépendant du schéma partagé) — propre à chaque machine, hors iCloud.
`<slug> = <basename du workspace>-<sha256(realpath)[:8]>` (ex. `DIRMC-3fa2b91c`).
Racine surchargeable via `$TODOMAIL_CONFIG_HOME` (indispensable pour les
tests). Répertoire en mode 0o700, fichier en 0o600.

```json
{
  "schema_version": 1,
  "workspace_path": "/Users/olivier/Documents/CLAUDE-COWORK/DIRMC",
  "imap": { "hostname": "127.0.0.1", "port": 1143, "username": "...",
            "password": "...", "use_starttls": true },
  "dashboard": { "port": 8770, "hostname": "todomail.jautzy.com",
                 "team_domain": "...", "access_aud": "..." }
}
```

`workspace_path` est purement informatif (debug humain). Les blocs `imap`
et `dashboard` sont chacun optionnels (le mac non-serveur du dashboard n'a
pas de bloc `dashboard`).

Pourquoi ce split : le mot de passe IMAP est généré par le Proton Bridge de
CHAQUE mac (valeurs différentes par machine) — le stocker dans le fichier
partagé faisait transiter un secret par iCloud et écraser le mot de passe
d'un mac par celui de l'autre. Le bloc `dashboard` ne concerne que le mac
qui héberge le tunnel cloudflared.

Migration v3 → v4 : `migrate_legacy_config()` déplace les blocs `imap` /
`dashboard` du fichier partagé vers le fichier local (idempotent, le local
existant gagne en cas de conflit), puis purge le partagé. Un bloc `imap`
migré est tagué `migrated_from_legacy: true` : le mot de passe legacy
provient du mac qui l'avait configuré à l'origine, pas forcément de la
machine courante — `/todomail:start` demande confirmation avant d'effacer
le flag. Tant que la migration n'a pas eu lieu, `get_imap_config()` et
`get_dashboard_config()` retombent sur le bloc legacy du fichier partagé
(précédence : local > legacy partagé) avec un avertissement sur stderr.
"""

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.fs_utils import atomic_read_json, atomic_write_json, chmod_600


CONFIG_FILENAME = ".todomail-config.json"
SCHEMA_VERSION = 4
LOCAL_SCHEMA_VERSION = 1
LOCAL_CONFIG_FILENAME = "config.json"


# ---------------------------------------------------------------------------
# Fichier partagé (workspace, sync iCloud)
# ---------------------------------------------------------------------------

def config_path(workspace: Path) -> Path:
    """Return the path to the shared config file in a workspace directory."""
    return Path(workspace) / CONFIG_FILENAME


def load_config(workspace: Path) -> dict | None:
    """Load the workspace config as a merged view (shared + local blocks).

    Returns None if the shared file is absent (unchanged semantics : the
    shared file is the workspace marker). When present, the `imap` and
    `dashboard` blocks of the LOCAL machine config are overlaid on top of
    any legacy blocks still in the shared file (precedence: local > legacy).
    Existing callers keep working without change.
    """
    shared = atomic_read_json(config_path(workspace))
    if shared is None:
        return None
    local = load_local_config(workspace) or {}
    merged = dict(shared)
    for key in ("imap", "dashboard"):
        if key in local:
            merged[key] = local[key]
    return merged


def _write_config(workspace: Path, data: dict) -> dict:
    """Internal: write the full shared config dict atomically and chmod 600."""
    path = config_path(workspace)
    atomic_write_json(path, data)
    chmod_600(path)
    return data


def save_config(workspace: Path, expected_rag_name: str) -> dict:
    """Create or update the shared workspace config (schema v4, no secrets).

    If legacy `imap`/`dashboard` blocks are still present in the shared
    file, `migrate_legacy_config()` is called first (they move to the
    local machine config and are purged from the shared file).

    Returns the saved shared config dict.
    """
    migrate_legacy_config(workspace)
    existing = atomic_read_json(config_path(workspace)) or {}
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "expected_rag_name": expected_rag_name,
        "configured_at": datetime.now(timezone.utc).isoformat(),
    }
    # Préserve d'éventuels champs partagés additionnels (hors secrets)
    for key, value in existing.items():
        if key not in data and key not in ("imap", "dashboard"):
            data[key] = value
    return _write_config(workspace, data)


def check_rag_name(workspace: Path, actual_rag_name: str) -> tuple[bool, str | None]:
    """Verify that actual_rag_name matches the expected one (shared file).

    Returns (ok, expected):
    - ok = True and expected = None if the config is missing (caller should handle)
    - ok = True and expected = <name> if the actual matches the expected
    - ok = False and expected = <name> if there is a mismatch
    """
    cfg = atomic_read_json(config_path(workspace))
    if cfg is None:
        return True, None
    expected = cfg.get("expected_rag_name")
    if expected is None:
        return True, None
    return actual_rag_name == expected, expected


# ---------------------------------------------------------------------------
# Fichier local (machine, hors iCloud)
# ---------------------------------------------------------------------------

def local_config_home() -> Path:
    """Racine des configs machine-locales.

    `$TODOMAIL_CONFIG_HOME` si défini (tests), sinon `~/.config/todomail`.
    """
    env = os.environ.get("TODOMAIL_CONFIG_HOME")
    if env:
        return Path(env)
    return Path.home() / ".config" / "todomail"


def workspace_slug(workspace: Path) -> str:
    """Slug stable et unique par workspace : `<basename>-<sha256(realpath)[:8]>`.

    Le hash du realpath distingue deux workspaces de même basename ; le
    basename garde le répertoire lisible pour un humain (ex. `DIRMC-3fa2b91c`).
    """
    real = Path(workspace).resolve()
    digest = hashlib.sha256(str(real).encode("utf-8")).hexdigest()[:8]
    return f"{real.name}-{digest}"


def local_config_dir(workspace: Path) -> Path:
    """Répertoire local de la machine pour ce workspace (créé, mode 0o700)."""
    d = local_config_home() / workspace_slug(workspace)
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except (OSError, NotImplementedError):
        pass
    return d


def local_config_path(workspace: Path) -> Path:
    """Chemin du `config.json` local de la machine pour ce workspace."""
    return local_config_dir(workspace) / LOCAL_CONFIG_FILENAME


def load_local_config(workspace: Path) -> dict | None:
    """Charge le config.json local de la machine, None si absent."""
    return atomic_read_json(local_config_path(workspace))


def _write_local_config(workspace: Path, data: dict) -> dict:
    """Internal: write the local machine config atomically and chmod 600."""
    path = local_config_path(workspace)
    atomic_write_json(path, data)
    chmod_600(path)
    return data


def _local_base(workspace: Path) -> dict:
    """Socle d'un config.json local neuf (schéma + chemin informatif)."""
    return {
        "schema_version": LOCAL_SCHEMA_VERSION,
        "workspace_path": str(Path(workspace).resolve()),
    }


def save_imap_config(
    workspace: Path,
    hostname: str,
    port: int,
    username: str,
    password: str,
    use_starttls: bool = True,
) -> dict:
    """Create or update the `imap` block in the LOCAL machine config.

    N'écrit plus rien dans le fichier partagé (le mot de passe IMAP est
    propre au Proton Bridge de chaque mac). Préserve le bloc `dashboard`
    local existant. Réécrit le bloc `imap` à neuf : un éventuel flag
    `migrated_from_legacy` est donc effacé. Fichier en 0o600.

    Returns the saved local config dict.
    """
    existing = load_local_config(workspace) or _local_base(workspace)
    existing["schema_version"] = LOCAL_SCHEMA_VERSION
    existing["imap"] = {
        "hostname": hostname,
        "port": int(port),
        "username": username,
        "password": password,
        "use_starttls": bool(use_starttls),
    }
    return _write_local_config(workspace, existing)


def save_dashboard_config(
    workspace: Path,
    port: int,
    hostname: str,
    team_domain: str | None = None,
    access_aud: str | None = None,
) -> dict:
    """Create or update the `dashboard` block in the LOCAL machine config.

    Cette config est propre au mac qui héberge le serveur du dashboard et
    le tunnel cloudflared — elle ne transite plus par le workspace iCloud.
    Préserve le bloc `imap` local existant. Fichier en 0o600.

    Returns the saved local config dict.
    """
    existing = load_local_config(workspace) or _local_base(workspace)
    existing["schema_version"] = LOCAL_SCHEMA_VERSION
    existing["dashboard"] = {
        "port": int(port),
        "hostname": hostname,
        "team_domain": team_domain,
        "access_aud": access_aud,
    }
    return _write_local_config(workspace, existing)


def _warn_legacy(block: str) -> None:
    print(
        f"[todomail] AVERTISSEMENT : bloc {block} legacy détecté dans "
        f"{CONFIG_FILENAME} — lance /todomail:start pour migrer vers la "
        "config machine-locale.",
        file=sys.stderr,
    )


def get_imap_config(workspace: Path) -> dict | None:
    """Bloc `imap` : config locale d'abord, fallback legacy partagé.

    Le fallback (fichier partagé v3 non migré) émet un avertissement sur
    stderr invitant à lancer /todomail:start. Retourne None si aucun bloc.
    """
    local = load_local_config(workspace)
    if local and local.get("imap"):
        return local["imap"]
    shared = atomic_read_json(config_path(workspace))
    if shared and shared.get("imap"):
        _warn_legacy("imap")
        return shared["imap"]
    return None


def get_dashboard_config(workspace: Path) -> dict | None:
    """Bloc `dashboard` : config locale d'abord, fallback legacy partagé.

    Utilisé par `lib.serve_dashboard` et `/todomail:dashboard`. Même
    avertissement stderr que `get_imap_config` en cas de fallback legacy.
    """
    local = load_local_config(workspace)
    if local and local.get("dashboard"):
        return local["dashboard"]
    shared = atomic_read_json(config_path(workspace))
    if shared and shared.get("dashboard"):
        _warn_legacy("dashboard")
        return shared["dashboard"]
    return None


# ---------------------------------------------------------------------------
# Migration v3 -> v4
# ---------------------------------------------------------------------------

def migrate_legacy_config(workspace: Path) -> dict:
    """Migre les blocs `imap`/`dashboard` du fichier partagé vers le local.

    Idempotente. Ordre atomique impératif : le fichier LOCAL est écrit et
    relu avec succès AVANT la purge du partagé (jamais de perte de secret
    en cas d'interruption). En cas de conflit, le bloc LOCAL existant gagne
    (le mot de passe Proton Bridge de CETTE machine est le bon) — le bloc
    legacy est alors simplement purgé du partagé.

    Un bloc `imap` copié depuis le legacy est tagué
    `migrated_from_legacy: true` : le mot de passe provient du mac qui
    l'avait configuré à l'origine, pas forcément de la machine qui exécute
    la migration. `/todomail:start` (étape 0c bis) demande confirmation
    puis efface le flag (ou force la ressaisie via `save_imap_config`).

    Retourne un rapport `{"migrated": [...], "already_clean": bool}` où
    `migrated` liste les blocs effectivement copiés dans le fichier local.
    """
    shared = atomic_read_json(config_path(workspace))
    if not shared:
        return {"migrated": [], "already_clean": True}
    legacy_keys = [k for k in ("imap", "dashboard") if k in shared]
    if not legacy_keys:
        return {"migrated": [], "already_clean": True}

    local = load_local_config(workspace) or _local_base(workspace)
    local["schema_version"] = LOCAL_SCHEMA_VERSION
    migrated: list[str] = []
    for key in legacy_keys:
        if key in local:
            continue  # le local existant gagne
        block = dict(shared[key])
        if key == "imap":
            block["migrated_from_legacy"] = True
        local[key] = block
        migrated.append(key)

    # 1) Écriture locale + relecture de contrôle AVANT toute purge
    _write_local_config(workspace, local)
    reread = load_local_config(workspace)
    if reread is None or any(k not in reread for k in legacy_keys):
        raise RuntimeError(
            "migration interrompue : relecture du fichier local échouée, "
            "le fichier partagé n'a PAS été purgé"
        )

    # 2) Purge du partagé (bump v4)
    purged = {k: v for k, v in shared.items() if k not in ("imap", "dashboard")}
    purged["schema_version"] = SCHEMA_VERSION
    _write_config(workspace, purged)
    return {"migrated": migrated, "already_clean": False}
