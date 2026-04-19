# lib/ — Utilitaires partages TodoMail

Helpers Python partages par les skills et commandes du plugin TodoMail.
Introduits en Phase 1 du refactoring v2.0, exploites a partir de la Phase 2.
Etat final v2.0.0 : 5 modules.

## Import

Depuis la racine du plugin :

```bash
python3 -c "from lib import state, fs_utils, rag_cache, error_modes, config; print('OK')"
```

Depuis un skill ou une commande (preambule PYTHONPATH obligatoire — la
substitution shell de `${CLAUDE_PLUGIN_ROOT}` n'est pas fiable dans tous
les contextes d'execution) :

```bash
python3 - <<'PY'
import sys, os
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    raise RuntimeError("CLAUDE_PLUGIN_ROOT non defini")
sys.path.insert(0, plugin_root)
from lib.state import load_state, acquire_lock, release_lock, update_checkpoint
from lib.rag_cache import RagCache
PY
```

## Modules

### `state.py` — Gestion du state.json persistant

Fichier : `$CLAUDE_PROJECT_DIR/.todomail/state.json` (depuis alpha.8 — tout
le runtime du plugin pour un workspace vit dans `.todomail/`, plus de
`CLAUDE_PLUGIN_DATA`, plus de mirror).

| Fonction | Description |
|----------|-------------|
| `workspace_dir()` | Resout `$CLAUDE_PROJECT_DIR` ou cwd contenant `.todomail-config.json` |
| `runtime_dir()` | Dossier `.todomail/` (cree a la volee) |
| `load_state()` | Charge ou cree le state avec schema par defaut |
| `save_state(state)` | Ecriture atomique + touche `invalidate.txt` (notif dashboard) |
| `update_checkpoint(phase, status, payload)` | Ajoute un point de controle |
| `record_error(mail_id, phase, error_type, message)` | Enregistre ou incremente une erreur |
| `clear_error(mail_id)` | Retire une erreur apres retry reussi |
| `get_pending_errors()` | Erreurs retryables (retry_count < 3, pas permanent) |
| `acquire_lock(name)` | Pose un verrou consultatif (retourne False si deja actif) |
| `release_lock()` | Libere le verrou (a appeler meme en cas d'erreur, via try/finally) |

**Important** : tout skill ou commande qui modifie le filesystem ou le
state DOIT acquire/release le verrou. Sans lock, le dashboard n'affiche
pas la banniere bleue « Claude travaille… » et `state.json.checkpoints`
reste vide.

### `fs_utils.py` — Operations fichiers idempotentes + JSON v2

| Fonction | Description |
|----------|-------------|
| `safe_mv(src, dst)` | Deplacement idempotent (False si deja fait) |
| `safe_rm(path)` | Suppression idempotente (False si absent) |
| `mkdir_p(path)` | Creation recursive sans erreur |
| `atomic_write_json(path, data)` | Ecriture atomique JSON |
| `atomic_read_json(path)` | Lecture JSON (None si absent) |
| `is_already_in_destination(mail_id, dest_dir)` | Verification de presence |
| `make_meta(session_id, ...)` | Construit un wrapper `_meta` v2 |
| `read_v2_json(path, data_key)` | Lecture compatible v1 et v2 |
| `write_v2_json(path, data_key, data_list, session_id, ...)` | Ecriture v2 |
| `read_pending_emails(category_dir)` | Raccourci pending_emails.json |
| `write_pending_emails(category_dir, emails, session_id)` | Raccourci ecriture |
| `read_instructions(category_dir)` | Raccourci instructions.json |
| `write_instructions(category_dir, instructions, session_id, ...)` | Raccourci ecriture |

### `rag_cache.py` — Cache RAG en memoire de session

Classe `RagCache` : cache cle-valeur en memoire pour eviter les appels MCP
redondants. Utilise par `sort-mails`, `/process-todo`, `/briefing`,
`/check-agenda` et les skills agenda.

```python
cache = RagCache()
result = cache.get("search_mail", "expediteur:durand")
if result is None:
    result = mcp_search_mail("expediteur:durand")
    cache.put("search_mail", "expediteur:durand", result)
# En fin de cycle :
print(cache.stats())  # {hits, misses, size}
cache.clear()
```

La methode `dump_for_observability()` serialise le cache vers
`$CLAUDE_PROJECT_DIR/.todomail/rag_cache.json` pour debug (non relu).

### `error_modes.py` — Strategie d'erreur

Enum `ErrorAction` : `CONTINUE`, `STOP_AND_ASK`, `RETRY_LATER`

Classe `ErrorHandler(mode)` : gere les erreurs selon le mode configure.

### `config.py` — Config workspace `.todomail-config.json`

Helpers pour gerer la config locale du workspace (fichier `.todomail-config.json` a la racine du repertoire de travail). Permet de desambiguer quand plusieurs serveurs MCP archiva sont connectes dans Claude Desktop.

| Fonction | Description |
|----------|-------------|
| `config_path(workspace)` | Retourne le chemin du fichier de config |
| `load_config(workspace)` | Charge la config (None si absente) |
| `save_config(workspace, expected_rag_name)` | Cree/met a jour la config avec le nom du serveur attendu |
| `check_rag_name(workspace, actual_rag_name)` | Verifie que le rag_name actuel correspond a l'attendu. Retourne `(ok, expected)` |

Schema de `.todomail-config.json` :

```json
{
  "schema_version": 1,
  "expected_rag_name": "Archiva-Pro",
  "configured_at": "2026-04-17T12:34:56+00:00"
}
```

Ce fichier est cree automatiquement par `/start` et verifie par `/check-inbox` et `/process-todo`. Il est gitignore (ne doit pas etre committe).

## Schema JSON v2

### Principe

Le schema v2 ajoute un wrapper `_meta` a tous les fichiers JSON d'echange (pending_emails.json, instructions.json). Cela permet le versioning, le suivi de session et la detection de donnees perimes.

### `pending_emails.json` v2

```json
{
  "_meta": {
    "schema_version": 2,
    "session_id": "20260415-093021-ab12cd",
    "generated_at": "2026-04-15T09:34:12Z"
  },
  "emails": [
    {
      "id": "2026-04-15_09h15m00_1",
      "sender": "jean.dupont@example.com",
      "date": "2026-04-15",
      "synth": "Demande de validation du budget Q2",
      "agenda-info": null
    }
  ]
}
```

Retrocompatibilite : `read_v2_json` accepte aussi un tableau brut (format v1) et renvoie `(None, array)`.

### `instructions.json` v2

```json
{
  "_meta": {
    "schema_version": 2,
    "session_id": "20260415-093021-ab12cd",
    "consumes_session_id": "20260415-093021-ab12cd",
    "generated_at": "2026-04-15T09:36:00Z"
  },
  "instructions": [
    {
      "id": "2026-04-15_09h15m00_1",
      "action": "other"
    }
  ]
}
```

Le champ `consumes_session_id` indique sur quelle session sort-mails le dashboard a genere ses instructions. Cela permet a process-todo de verifier la coherence.

### `state.json`

```json
{
  "schema_version": 2,
  "session_id": "20260415-093021-ab12cd",
  "current_phase": null,
  "started_at": "2026-04-15T09:30:21Z",
  "last_update_at": "2026-04-15T09:34:12Z",
  "active_lock": null,
  "counters": {},
  "checkpoints": [
    {
      "phase": "sort-mails:prefilter",
      "status": "ok",
      "at": "2026-04-15T09:31:00Z"
    }
  ],
  "errors": [
    {
      "mail_id": "2026-04-15_09h20m00_3",
      "phase": "sort-mails:analyze",
      "error_type": "TimeoutError",
      "message": "MCP search_mail timeout",
      "timestamp": "2026-04-15T09:32:00Z",
      "last_at": "2026-04-15T09:32:00Z",
      "retry_count": 0,
      "permanent_failure": false
    }
  ],
  "error_mode": "lenient"
}
```

## Strategie d'erreur

### Mode `lenient` (defaut)

Une erreur sur un mail n'interrompt pas le cycle. Le mail est laisse en place, l'erreur est enregistree dans `state.json.errors[]`. Le compte-rendu final liste les echecs avec invitation a relancer via `--retry`.

### Mode `strict` (opt-in via `--strict`)

Premiere erreur → STOP immediat. Affichage du contexte complet (mail, etape, stack). Demande a l'utilisateur : reprise / abandon / passer au suivant.

### Mode `resume` (toujours actif)

Chaque erreur est enregistree dans `state.json.errors[]` avec un compteur `retry_count`. Le flag `--retry` ne traite que les entrees non resolues. A chaque retry reussi, l'entree est retiree. Si une entree echoue 3 fois (`retry_count >= 3`), elle est marquee `permanent_failure` et necessite une intervention manuelle.

## Garanties d'idempotence

| Operation | Comportement si deja fait |
|-----------|--------------------------|
| `safe_mv(src, dst)` | Retourne False, aucune action |
| `safe_rm(path)` | Retourne False, aucune action |
| `mkdir_p(path)` | Aucune erreur |
| `atomic_write_json(path, data)` | Ecrase le contenu (write-through) |
| `is_already_in_destination(mail_id, dest)` | Retourne True |
