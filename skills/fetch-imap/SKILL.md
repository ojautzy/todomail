---
name: fetch-imap
description: >
  Skill interne (non auto-déclenchable) : téléchargement des mails depuis un
  serveur IMAP4 (STARTTLS). Fournit deux modules Python autonomes qui
  se connectent au serveur, récupèrent les nouveaux messages par UID, les
  écrivent dans inbox/<timestamp>/ (message.eml + message.json + pièces
  jointes), puis les suppriment côté serveur. Invoqué exclusivement par la
  commande /todomail:check-inbox.
version: 1.0.0
---

# fetch-imap — Téléchargement IMAP4 autonome

Ce skill n'a pas de commande dédiée ni de trigger naturel. Il est invoqué **uniquement** par `/todomail:check-inbox` (Étape 1). La description ci-dessus n'est pas rédigée pour l'auto-déclenchement ; elle documente le contrat technique du module.

## Responsabilité

Le skill prend en charge **l'intégralité du téléchargement IMAP** :

1. Connexion au serveur IMAP4 (STARTTLS, login username/password)
2. Détection des capacités (`MOVE`, etc.)
3. Gestion de l'état UID : `inbox/.inbox_state.json` avec `uidvalidity` et `last_uid` pour ne télécharger que les nouveaux messages
4. Pour chaque nouveau message :
   - Création d'un sous-répertoire horodaté `inbox/<YYYY-MM-DD_HHhMMmSS>/`
   - Écriture du fichier `message.eml` (RFC 822 brut)
   - Extraction des pièces jointes dans le même sous-répertoire (noms MIME-décodés)
   - Génération de `message.json` (métadonnées + corps texte, via `eml_parser`)
   - Suppression du message côté serveur (UID MOVE Trash ou fallback COPY + STORE `\Deleted` + EXPUNGE)
5. Sauvegarde du nouveau `last_uid` dans `.inbox_state.json`
6. Retour d'un rapport structuré `FetchReport` consommable par l'appelant

Le skill **ne gère pas** : le verrou du plugin, le checkpoint `state.json`, la lecture de la config IMAP, le tri des mails (responsabilité de `/check-inbox` et de `sort-mails`).

## Où est lue la configuration IMAP

La configuration IMAP vit dans `$WORKSPACE/.todomail-config.json`, bloc `imap` (schéma v2 géré par `lib/config.py`) :

```json
{
  "schema_version": 2,
  "expected_rag_name": "...",
  "imap": {
    "hostname": "127.0.0.1",
    "port": 1143,
    "username": "user@example.com",
    "password": "...",
    "use_starttls": true
  }
}
```

Le skill **ne lit pas le fichier directement** : l'appelant (`/check-inbox`) charge la config via `lib.config.load_config()`, construit un `ImapConfig` et l'injecte en paramètre de `fetch_inbox()`.

## API publique

### `imap_fetch.py`

```python
from dataclasses import dataclass, field
from pathlib import Path

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
    directory: str   # chemin absolu du sous-répertoire créé

@dataclass
class FetchReport:
    success: bool
    processed: int = 0
    errors: int = 0
    delete_failed: int = 0
    messages: list[FetchedMessage] = field(default_factory=list)
    inbox_path: str | None = None
    error: str | None = None

    def as_json(self) -> str: ...

def fetch_inbox(inbox_dir: Path, config: ImapConfig) -> FetchReport:
    """Point d'entrée principal.

    - Idempotent via `inbox_dir/.inbox_state.json` (uidvalidity + last_uid).
    - Capture toutes les exceptions et les reflète dans `FetchReport`
      (ne lève jamais côté appelant).
    - Logging best-effort vers `$WORKSPACE/.todomail/check_inbox.log` (via
      `lib.state.runtime_dir()`).
    """

def main() -> int:
    """CLI pour tests manuels : python3 imap_fetch.py [--workspace DIR].
    Lit `.todomail-config.json` du workspace et appelle `fetch_inbox`.
    Retourne 0 si succès, 1 sinon."""
```

### `eml_parser.py`

```python
def parse_eml(filepath: Path, max_body_length: int | None = None) -> dict:
    """Parse un fichier EML → dict contenant les métadonnées et le corps texte.
    Schéma identique à celui consommé par le skill sort-mails."""

def write_json_alongside(eml_path: Path, max_body_length: int | None = None) -> Path:
    """Parse eml_path, écrit le résultat JSON à côté (même nom, suffixe .json).
    Retourne le chemin du JSON écrit. Ne lève jamais : en cas d'erreur,
    le dict produit contient `parse_status: "NOK-ERREUR"`."""
```

## Schéma `message.json` produit (consommé par sort-mails)

```json
{
  "file": "/abs/path/to/message.eml",
  "filename": "message.eml",
  "from": "Jane Doe <jane@example.com>",
  "to": "me@example.com",
  "cc": "",
  "date": "Thu, 19 Apr 2026 09:15:00 +0200",
  "date_iso": "2026-04-19T09:15:00+02:00",
  "subject": "Sujet du mail",
  "body_text": "Corps complet en texte brut (HTML converti si nécessaire).",
  "body_length": 1234,
  "body_truncated": false,
  "attachments": [
    {"filename": "rapport.pdf", "size_bytes": 52341, "content_type": "application/pdf"}
  ],
  "parse_status": "OK",
  "parse_error": null
}
```

## Dépendances

**Aucune dépendance pip.** Le skill utilise exclusivement la bibliothèque standard Python (`imaplib`, `email`, `email.policy`, `html.parser`, `json`, `pathlib`, `re`, `dataclasses`).

## Contrat d'invocation depuis /check-inbox

```python
import sys, os
plugin_root = os.environ["CLAUDE_PLUGIN_ROOT"]
sys.path.insert(0, plugin_root)
sys.path.insert(0, os.path.join(plugin_root, "skills", "fetch-imap", "scripts"))

from lib.state import acquire_lock, release_lock, update_checkpoint, workspace_dir
from lib.config import load_config
from imap_fetch import fetch_inbox, ImapConfig

ws = workspace_dir()
cfg = load_config(ws)
if not cfg or not cfg.get("imap"):
    raise RuntimeError("IMAP non configuré — lance /todomail:start")

acquire_lock("check-inbox:fetch")
try:
    update_checkpoint("check-inbox:fetch", "start")
    report = fetch_inbox(ws / "inbox", ImapConfig(**cfg["imap"]))
    update_checkpoint(
        "check-inbox:fetch",
        "ok" if report.success else "error",
        {"processed": report.processed, "errors": report.errors},
    )
finally:
    release_lock()
```

## Points d'attention

- **Perte de mail sur crash entre FETCH et MOVE** : si le process meurt entre `eml_path.write_bytes(raw_email)` et `delete_message(...)`, le mail peut être dupliqué au prochain run. Comportement préexistant mitigé par `ensure_unique_dir` qui suffixe le nom du répertoire.
- **UIDVALIDITY change** : full scan automatique si la valeur change côté serveur.
- **Blocage proton-bridge** : connexion refusée → message clair dans `FetchReport.error`.
- **Noms de pièces jointes** : décodés via `email.header.decode_header()` (MIME encodings supportés), nettoyés de `/` et `\0`.
