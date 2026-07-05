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
| `runtime_dir()` | Dossier `.todomail/` partage (cree a la volee) |
| `local_runtime_dir(workspace=None)` | Dossier de logs machine-local `~/.config/todomail/<slug>/logs/` (v2.3.0) |
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

### `config.py` — Config partagee (workspace) et machine-locale

Depuis la v2.3.0 (usage multi-Mac, workspace synchronise iCloud), la config
est separee en deux niveaux :

- **Partage** : `.todomail-config.json` a la racine du workspace (schema v4,
  AUCUN secret : `expected_rag_name`, `configured_at`). Sert aussi de
  marqueur de detection du workspace — ne jamais le supprimer.
- **Local** : `~/.config/todomail/<slug>/config.json` (schema local v1,
  chmod 600, repertoire 700, racine surchargeable via `$TODOMAIL_CONFIG_HOME`)
  avec les blocs `imap` et `dashboard`, propres a chaque machine.

| Fonction | Description |
|----------|-------------|
| `config_path(workspace)` | Chemin du fichier partage |
| `load_config(workspace)` | Vue fusionnee : partage + blocs `imap`/`dashboard` locaux superposes (None si partage absent) |
| `save_config(workspace, expected_rag_name)` | Cree/met a jour le fichier partage en v4 (migre d'abord les blocs legacy) |
| `check_rag_name(workspace, actual_rag_name)` | Verifie le rag_name attendu (fichier partage). Retourne `(ok, expected)` |
| `local_config_home()` | `$TODOMAIL_CONFIG_HOME` ou `~/.config/todomail` |
| `workspace_slug(workspace)` | `<basename>-<sha256(realpath)[:8]>` (ex. `DIRMC-3fa2b91c`) |
| `local_config_dir(workspace)` | Repertoire local de la machine (cree, mode 700) |
| `local_config_path(workspace)` | Chemin du `config.json` local |
| `load_local_config(workspace)` | Charge le config local (None si absent) |
| `save_imap_config(workspace, hostname, port, username, password, use_starttls)` | Ecrit le bloc `imap` dans le fichier LOCAL (efface un flag `migrated_from_legacy`) |
| `save_dashboard_config(workspace, port, hostname, team_domain, access_aud)` | Ecrit le bloc `dashboard` dans le fichier LOCAL |
| `get_imap_config(workspace)` | Bloc `imap` : local d'abord, fallback legacy partage (avertissement stderr) |
| `get_dashboard_config(workspace)` | Bloc `dashboard` : local d'abord, fallback legacy partage (avertissement stderr) |
| `migrate_legacy_config(workspace)` | Migration v3→v4 idempotente : deplace `imap`/`dashboard` vers le local (le local gagne en cas de conflit, ecriture locale AVANT purge du partage), tague `migrated_from_legacy` sur un bloc `imap` copie. Retourne `{"migrated": [...], "already_clean": bool}` |

Schemas :

```json
// .todomail-config.json (partage, v4)
{
  "schema_version": 4,
  "expected_rag_name": "Archiva-Pro",
  "configured_at": "2026-07-05T12:34:56+00:00"
}

// ~/.config/todomail/<slug>/config.json (local, v1)
{
  "schema_version": 1,
  "workspace_path": "/Users/.../DIRMC",
  "imap": { "hostname": "127.0.0.1", "port": 1143, "username": "...",
            "password": "...", "use_starttls": true },
  "dashboard": { "port": 8770, "hostname": "...", "team_domain": "...",
                 "access_aud": "..." }
}
```

Le fichier partage est cree automatiquement par `/start` et verifie par `/check-inbox` et `/process-todo`. Il est gitignore (ne doit pas etre committe). Tests : `python3 -m unittest lib.tests.test_config_split`.

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
