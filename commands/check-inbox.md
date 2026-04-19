---
description: Télécharger et trier les mails de la boîte de réception
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(python3:*), Bash(pip:*), Glob, Grep, Task, mcp
argument-hint: "[--strict] [--retry]"
---

## Accès aux helpers Python du plugin (à lire en premier)

Les modules `lib.state`, `lib.fs_utils`, `lib.rag_cache` référencés ci-dessous vivent à la racine du plugin, résolue via la variable d'environnement `CLAUDE_PLUGIN_ROOT`. La variable est récupérée **côté Python** (la substitution shell `${CLAUDE_PLUGIN_ROOT}` n'est pas fiable dans tous les contextes d'exécution) :

```bash
python3 - <<'PY'
import sys, os
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    raise RuntimeError("CLAUDE_PLUGIN_ROOT non defini")
sys.path.insert(0, plugin_root)
from lib.state import load_state, save_state, acquire_lock, release_lock, get_pending_errors, clear_error
# ...
PY
```

Si `ModuleNotFoundError: lib`, ne **jamais** conclure « pas de lib externe » — vérifier que `CLAUDE_PLUGIN_ROOT` est bien défini et retenter. Les helpers sont indispensables : sans eux, le dashboard n'est pas notifié du cycle.

## Parsing des arguments

Les arguments passés à la commande sont disponibles dans la variable `$ARGUMENTS`.
Le parsing est effectué en lisant sémantiquement cette variable (pas de parseur
externe).

Flags supportés :
- `--strict` : active le mode strict (`ErrorHandler(mode="strict")`) — arrêt
  immédiat à la première erreur avec demande utilisateur.
- `--retry` : **saute le téléchargement IMAP**, lit `lib.state.get_pending_errors()`
  et retraite uniquement les mails inscrits dans `state.errors[]`. Le mode reste
  `lenient` quelle que soit la combinaison de flags.

Règle de priorité :
1. Si `$ARGUMENTS` contient `--retry` → mode retry (Étape 1 sautée, analyse ciblée
   sur les mails en échec, chaque retry réussi retire l'entrée via
   `lib.state.clear_error(mail_id)`).
2. Sinon si `$ARGUMENTS` contient `--strict` → `ErrorHandler(mode="strict")`,
   cycle complet.
3. Sinon → mode par défaut (`lenient`, cycle complet).

## Vérification préalable

### 1. Répertoires

Vérifier que le répertoire de travail contient `inbox/`. Absence → **ARRÊT
OBLIGATOIRE — Répertoire inadéquat** (message clair, attendre).

### 2. Serveur MCP (désambiguation alpha.2 — **ne jamais supprimer**)

Lire `.todomail-config.json` à la racine du répertoire de travail. Appeler le
tool MCP `status` et comparer `status.rag_name` avec `expected_rag_name` du
fichier de config.

- Si `.todomail-config.json` n'existe pas : demander à l'utilisateur de lancer
  `/todomail:start` pour configurer le workspace, puis arrêter.
- Si `status.rag_name != expected_rag_name` :

> **ARRÊT OBLIGATOIRE — Mauvais serveur MCP**
> Afficher : « Le serveur MCP connecté (`<status.rag_name>`) ne correspond pas
> au serveur attendu pour ce workspace (`<expected_rag_name>`). Vérifier les
> connexions MCP dans Claude Desktop ou relancer `/todomail:start` pour
> reconfigurer. »

Cette vérification est **obligatoire** et s'exécute **avant** toute autre étape.
Elle couvre tous les composants en aval (sort-mails, analyse, etc.), qui n'ont
donc pas à la refaire.

## Étape 1 — Téléchargement des mails (sautée si `--retry`)

Depuis la v2.1.0, le téléchargement IMAP est pris en charge par le skill
interne `fetch-imap` (plugin-local, aucune dépendance au serveur MCP). La
configuration IMAP est lue dans le bloc `imap` de `.todomail-config.json`.
Chaque mail est placé dans un sous-répertoire de `inbox/` dont le nom est
l'horodate du mail. Le sous-répertoire contient :
- le mail au format EML (`message.eml`)
- un `message.json` (métadonnées + corps, produit par `eml_parser`)
- chaque pièce jointe (nommage MIME-décodé)

### 1a. Vérification de la configuration IMAP

Lire le bloc `imap` de `.todomail-config.json`. S'il est absent ou incomplet :

> **ARRÊT OBLIGATOIRE — Configuration IMAP manquante**
> « Le bloc `imap` est absent de `.todomail-config.json`. Lancer
> `/todomail:start` pour configurer les identifiants IMAP (hostname, port,
> username, password), puis relancer `/todomail:check-inbox`. »

### 1b. Exécution du téléchargement

Bloc Python canonique (verrou + checkpoint + appel `fetch_inbox` + libération
du verrou en `finally`) :

```bash
python3 - <<'PY'
import os, sys
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    raise RuntimeError("CLAUDE_PLUGIN_ROOT non defini")
sys.path.insert(0, plugin_root)
sys.path.insert(0, os.path.join(plugin_root, "skills", "fetch-imap", "scripts"))

from lib.state import (
    acquire_lock, release_lock, update_checkpoint, record_error, workspace_dir,
)
from lib.config import load_config
from imap_fetch import fetch_inbox, ImapConfig

ws = workspace_dir()
cfg = load_config(ws)
imap_block = (cfg or {}).get("imap") or {}
required = {"hostname", "port", "username", "password"}
missing = required - set(imap_block)
if missing:
    print(f"ERROR: bloc imap incomplet (manquants: {sorted(missing)}) — "
          f"relance /todomail:start")
    sys.exit(2)

if not acquire_lock("check-inbox:fetch"):
    print("ERROR: verrou deja pris, un autre cycle est en cours")
    sys.exit(3)

try:
    update_checkpoint("check-inbox:fetch", "start")
    imap_cfg = ImapConfig(
        hostname=imap_block["hostname"],
        port=int(imap_block["port"]),
        username=imap_block["username"],
        password=imap_block["password"],
        use_starttls=bool(imap_block.get("use_starttls", True)),
    )
    report = fetch_inbox(ws / "inbox", imap_cfg)
    if report.success:
        update_checkpoint(
            "check-inbox:fetch", "ok",
            {"processed": report.processed, "errors": report.errors,
             "delete_failed": report.delete_failed},
        )
    else:
        update_checkpoint(
            "check-inbox:fetch", "error",
            {"error": report.error},
        )
        record_error(
            mail_id="__fetch__", phase="check-inbox:fetch",
            error_type="imap", message=report.error or "unknown",
        )
    print(report.as_json())
finally:
    release_lock()
PY
```

Lire le JSON produit sur stdout (`FetchReport`) :

- `success: true` avec `processed: 0` → aucun nouveau mail, continuer vers l'Étape 2 (pour nettoyer d'éventuels artefacts restants dans `inbox/`).
- `success: true` avec `processed > 0` → continuer vers l'Étape 2.
- `success: false` → afficher `error` à l'utilisateur et **arrêter** (ne pas lancer sort-mails). Typiquement : proton-bridge hors ligne, credentials invalides. L'erreur est déjà consignée dans `state.errors[]` pour inspection ultérieure.

**Note :** aucun appel `update_index` n'est fait à cette étape. Le serveur MCP
indexe uniquement `docs/` et `mails/` (les mails archivés post-traitement),
pas `inbox/`. L'indexation RAG a lieu en fin de `/todomail:process-todo`.

## Étape 2 — Tri des mails (skill sort-mails)

Lire `@${CLAUDE_PLUGIN_ROOT}/skills/sort-mails/SKILL.md` et suivre ses étapes.

**Transmission des flags** : transmettre le mode d'erreur (`lenient` / `strict`)
au skill via l'`ErrorHandler` déjà instancié dans l'environnement de session.

**Mode `--retry`** : au lieu de lister `inbox/`, lister les `mail_id` retournés
par `lib.state.get_pending_errors()`. Pour chaque `mail_id`, localiser son
répertoire source (dans `inbox/` ou déjà dans `todo/<catégorie>/` selon où il
est resté) et relancer uniquement l'Étape 2 de sort-mails sur ce mail. À chaque
retry réussi : `lib.state.clear_error(mail_id)`. Les `pending_emails.json` sont
re-fusionnés en conséquence.

## Étape 3 — Compte-rendu

### Statistiques

- Nombre total de mails téléchargés (cycle complet) **ou** nombre de mails
  retraités (`--retry`).
- Stats pré-filtrage Haiku et cache RAG (héritées du skill sort-mails).
- Répartition par catégorie.

### Erreurs éventuelles

Lister les erreurs persistantes de `state.errors[]` avec, pour chacune :
`mail_id`, `phase`, `error_type`, `retry_count`, `permanent_failure`.

Si au moins une erreur est non résolue :

> Relancer `/todomail:check-inbox --retry` pour retraiter uniquement les mails
> en échec.

### Accès au dashboard

Indiquer à l'utilisateur qu'il peut ouvrir le dashboard interactif dans son
navigateur :

```
file://<chemin_absolu_du_répertoire_de_travail>/dashboard.html
```
