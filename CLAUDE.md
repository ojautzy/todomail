# CLAUDE.md — Instructions pour le développement du plugin TodoMail

## Structure du projet

Plugin Claude Code : skills, agents et commandes pour le traitement des emails et la gestion d'agenda.

```
todomail/
├── .claude-plugin/plugin.json   ← manifeste du plugin (source de vérité pour la version)
├── commands/*.md                ← commandes utilisateur (/start, /dashboard, /check-inbox, /process-todo, /briefing, /check-agenda)
├── agents/*.md                  ← agents autonomes (mail-prefilter)
├── bin/                         ← exécutables sur le PATH du tool Bash (todomail-plugin-root, v2.3.1)
├── skills/*/SKILL.md            ← skills (sort-mails, agenda, disponibilites, detection-conflits, briefing, check-agenda, memory-management, classify-attachment, read-odf)
├── skills/dashboard.html        ← dashboard interactif (copie unique, servie exclusivement par lib/serve_dashboard.py depuis v2.3.0)
├── hooks/                       ← 5 hooks Claude Code + hooks.json (session_start, enforce_classify, invalidate_dashboard_cache, inject_context, pre_compact)
├── lib/                         ← helpers Python (state, fs_utils, rag_cache, error_modes, config) + serve_dashboard.py (serveur HTTP du dashboard, v2.2.0)
├── CHANGELOG.md                 ← historique des versions
├── CONNECTORS.md                ← documentation des connecteurs MCP
├── CLOUDFLARE-DASHBOARD.md      ← mise en service du dashboard sur Internet (tunnel + Cloudflare Access, v2.2.0)
├── README.md                    ← documentation principale
└── README.dashboard.md          ← documentation technique du dashboard
```

## Runtime du plugin : partagé (workspace) et machine-local

Depuis la v2.3.0 (Phase 8, usage multi-Mac avec workspace synchronisé iCloud), le runtime est séparé en deux niveaux :

**Partagé** — suit les mails, synchronisé iCloud avec le workspace :
- `$CLAUDE_PROJECT_DIR/.todomail/` : state.json, invalidate.txt, retry_request.txt, errors_dismiss.txt, precompact_snapshot_*.json
- `.todomail-config.json` (racine du workspace, schéma **v4**, **aucun secret**) : `schema_version`, `expected_rag_name`, `configured_at`. Sert aussi de **marqueur de détection du workspace** pour `lib/state.py` (`workspace_dir()`, fallback cwd) — ne jamais le supprimer ni le déplacer. `expected_rag_name` désambigue quand plusieurs serveurs MCP archiva sont connectés dans Claude Desktop ; vérifié en début de toutes les commandes MCP-sensibles (`/check-inbox`, `/process-todo`, `/briefing`, `/check-agenda`).
- les répertoires métier (`inbox/`, `todo/`, `mails/`, `docs/`, `memory/`, `to-send/`, `to-work/`, `CLAUDE.md`)

**Machine-local** — propre à chaque mac, hors iCloud, dans `~/.config/todomail/<slug>/` où `<slug> = <basename du workspace>-<sha256(realpath)[:8]>` (ex. `DIRMC-3fa2b91c` ; racine surchargeable via `$TODOMAIL_CONFIG_HOME`, répertoire en mode 700) :
- `config.json` (chmod 600) : bloc `imap` (le mot de passe Proton Bridge est différent sur chaque mac) et bloc `dashboard` (`port`, `hostname`, `team_domain`, `access_aud` — seul le mac serveur du tunnel l'a)
- `memory_cache.json` (cache régénérable, écrit par `hooks/session_start.py`)
- `logs/` : serve_dashboard.log, check_inbox.log, hooks.log

**Règle** : tout nouveau fichier runtime doit être classé **partagé** (il suit les mails, les deux macs doivent le voir) ou **local** (il est propre à la machine : secret, log, cache régénérable). Accès via `lib/config.py` (`get_imap_config`, `get_dashboard_config`, `local_config_dir`) et `lib/state.py` (`runtime_dir()` partagé, `local_runtime_dir()` local). La migration v3 → v4 (`migrate_legacy_config`) est automatique via `/start` ; en lecture, les getters retombent sur le bloc legacy du fichier partagé tant que la migration n'a pas eu lieu (précédence local > legacy).

**Ne jamais recréer `.mcp.json`** : retiré en alpha.2 car inadapté à Claude Desktop (connexions dupliquées, proxy stdio inopérant).

## Gestion des versions

### Source de vérité

La version du plugin est définie dans `.claude-plugin/plugin.json`, champ `version`.
C'est le **seul endroit** où la version doit être modifiée.

### Convention : Semantic Versioning (SemVer)

- **MAJOR** : changements incompatibles (structure des JSON, changement d'API MCP requise)
- **MINOR** : nouvelles fonctionnalités rétrocompatibles (nouveau skill, nouvelle commande, nouveau champ)
- **PATCH** : corrections de bugs, améliorations mineures

### Processus de release

Lors de la publication d'une nouvelle version, effectuer **TOUTES** ces actions :

1. **Mettre à jour la version** dans `.claude-plugin/plugin.json`
2. **Ajouter l'entrée** dans `CHANGELOG.md` avec la date du jour et les changements
3. **Commit** avec le message : `Release vX.Y.Z — description courte`
4. **Créer le tag annoté** : `git tag -a vX.Y.Z -m "vX.Y.Z — description courte"`
5. **Pousser le commit et le tag** : `git push && git push origin vX.Y.Z`
6. **Créer la release GitHub** : `gh release create vX.Y.Z --title "vX.Y.Z — description courte" --notes-file -` avec les notes du CHANGELOG

### Format du CHANGELOG

Suivre le format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) :
- **Ajouté** : nouvelles fonctionnalités
- **Modifié** : changements dans les fonctionnalités existantes
- **Corrigé** : corrections de bugs
- **Optimisé** : améliorations de performance
- **Supprimé** : fonctionnalités retirées

## Conventions de développement

- Les noms de fichiers et répertoires sont en **kebab-case**
- Les skills externes (plateforme Claude Code) sont préfixés « skill plateforme » dans la documentation
- Les skills internes (ce plugin) sont préfixés « skill plugin » si distinction nécessaire
- Les références internes utilisent `${CLAUDE_PLUGIN_ROOT}/` comme racine dans la prose ; dans un bloc Bash exécutable, la racine se résout via `$(todomail-plugin-root)` (voir « Import Python depuis les skills/commandes »)

## Utilitaires partages (lib/)

Le repertoire `lib/` contient des helpers Python partages par les skills et commandes :

- `lib/state.py` — gestion du `state.json` persistant (checkpoints, erreurs, verrous)
- `lib/fs_utils.py` — operations fichiers idempotentes (`safe_mv`, `safe_rm`, `atomic_write_json`) et helpers JSON v2
- `lib/rag_cache.py` — cache RAG en memoire de session
- `lib/error_modes.py` — strategie d'erreur (`lenient`/`strict`/`resume`)
- `lib/config.py` — lecture/ecriture du `.todomail-config.json` (config workspace, desambiguation serveur MCP)

Ces helpers sont exploités par toutes les commandes et tous les skills du plugin depuis les Phases 2 à 6.
Voir `lib/README.md` pour la documentation complete.

### Verrou obligatoire pour toute commande qui modifie le state

Toute commande ou skill qui modifie le filesystem ou `state.json` (`sort-mails`, `/process-todo`, `/briefing`, `/check-agenda`) DOIT appeler `acquire_lock(name)` au début et `release_lock()` à la fin (via `try/finally`). Sans lock, le dashboard n'affiche pas la bannière bleue « Claude travaille… » et `state.json.checkpoints` reste vide. Pattern canonique : blocs Python concrets en étape 0 et étape de finalisation (voir `commands/process-todo.md` pour le modèle de référence).

### Import Python depuis les skills/commandes (regle imperative)

Les helpers `lib/` vivent a la racine du plugin. Le LLM qui execute un skill ne doit JAMAIS chercher `skills/<skill>/lib/` ni `lib/` relatif au cwd — ce chemin est inexistant.

**Contexte technique** (corrige en v2.3.1) : d'apres la doc officielle des plugins (section *Environment variables*), `${CLAUDE_PLUGIN_ROOT}` est substitue inline dans le contenu des skills/agents/hooks/configs MCP-LSP, et exporte comme variable d'environnement **uniquement aux processus hooks et serveurs MCP/LSP** — **jamais aux sous-processus Bash** lances par le LLM. Un bloc qui lit `os.environ.get("CLAUDE_PLUGIN_ROOT")` sans repli echoue donc systematiquement. La resolution fiable passe par le mecanisme officiel `bin/` : les executables du repertoire `bin/` du plugin sont sur le PATH du tool Bash tant que le plugin est actif, et `bin/todomail-plugin-root` affiche la racine du plugin.

**Pattern canonique** pour tout bloc Bash qui importe un module `lib.*` (resolution cote Python : le bloc commence par `python3`, ce qui le maintient dans l'allowlist `Bash(python3:*)` des frontmatters) :

```bash
python3 - <<'PY'
import sys, os
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    import shutil
    exe = shutil.which("todomail-plugin-root")
    if exe:
        plugin_root = os.path.dirname(os.path.dirname(os.path.realpath(exe)))
if not plugin_root:
    raise RuntimeError("racine du plugin todomail introuvable (ni CLAUDE_PLUGIN_ROOT ni todomail-plugin-root sur le PATH)")
sys.path.insert(0, plugin_root)
from lib.state import load_state, save_state, acquire_lock, release_lock
# ...
PY
```

Pour un chemin en shell pur (scripts de skills, lancement du serveur dashboard), utiliser `"$(todomail-plugin-root)/..."` — jamais `"${CLAUDE_PLUGIN_ROOT}/..."` seul (variable vide dans un sous-processus Bash).

**Anti-pattern a ne jamais reproduire** : si un `import lib.X` renvoie `ModuleNotFoundError`, **ne pas** conclure « pas de lib externe, analyse directe en flux ». C'est un bug d'import, pas une caracteristique du skill. Verifier que `todomail-plugin-root` est disponible (`which todomail-plugin-root` — sinon le plugin n'est pas actif), fixer le `sys.path` et retenter. Les helpers sont indispensables — sans `acquire_lock`/`save_state`, le dashboard ne voit pas le cycle et l'idempotence (`safe_mv`) n'est pas garantie.

Tout nouveau SKILL.md ou command.md qui touche `lib/` doit embarquer ce pattern en preambule explicite (voir `skills/sort-mails/SKILL.md`, `commands/check-inbox.md`, `commands/process-todo.md`, `commands/briefing.md`, `commands/check-agenda.md`).
