# CLAUDE.md — Instructions pour le développement du plugin TodoMail

## Structure du projet

Plugin Claude Code : skills, agents et commandes pour le traitement des emails et la gestion d'agenda.

```
todomail/
├── .claude-plugin/plugin.json   ← manifeste du plugin (source de vérité pour la version)
├── commands/*.md                ← commandes utilisateur (/start, /check-inbox, etc.)
├── agents/*.md                  ← agents autonomes (mail-prefilter)
├── skills/*/SKILL.md            ← skills (sort-mails, agenda, etc.)
├── CHANGELOG.md                 ← historique des versions
├── CONNECTORS.md                ← documentation des connecteurs MCP
├── README.md                    ← documentation principale
└── README.dashboard.md          ← documentation technique du dashboard
```

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
- Les références internes utilisent `${CLAUDE_PLUGIN_ROOT}/` comme racine

## Utilitaires partages (lib/)

Le repertoire `lib/` contient des helpers Python partages par les skills et commandes :

- `lib/state.py` — gestion du `state.json` persistant (checkpoints, erreurs, verrous)
- `lib/fs_utils.py` — operations fichiers idempotentes (`safe_mv`, `safe_rm`, `atomic_write_json`) et helpers JSON v2
- `lib/rag_cache.py` — cache RAG en memoire de session
- `lib/error_modes.py` — strategie d'erreur (`lenient`/`strict`/`resume`)
- `lib/config.py` — lecture/ecriture du `.todomail-config.json` (config workspace, desambiguation serveur MCP)

Ces helpers seront exploites par les skills et commandes a partir de la Phase 2 du refactoring.
Voir `lib/README.md` pour la documentation complete.

### Import Python depuis les skills/commandes (regle imperative)

Les helpers `lib/` vivent dans **`${CLAUDE_PLUGIN_ROOT}/lib/`**, PAS dans le repertoire du skill ni dans le workspace utilisateur. Le LLM qui execute un skill ne doit JAMAIS chercher `skills/<skill>/lib/` ni `lib/` relatif au cwd — ce chemin est inexistant.

**Pattern canonique** pour tout bloc Bash qui importe un module `lib.*` :

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 - <<'PY'
import sys, os
sys.path.insert(0, os.environ["CLAUDE_PLUGIN_ROOT"])
from lib.state import load_state, save_state, acquire_lock, release_lock
# ...
PY
```

**Anti-pattern a ne jamais reproduire** : si un `import lib.X` renvoie `ModuleNotFoundError`, **ne pas** conclure « pas de lib externe, analyse directe en flux ». C'est un bug d'import, pas une caracteristique du skill. Fixer le `sys.path` et retenter. Les helpers sont indispensables — sans `acquire_lock`/`save_state`, le dashboard ne voit pas le cycle et l'idempotence (`safe_mv`) n'est pas garantie.

Tout nouveau SKILL.md ou command.md qui touche `lib/` doit embarquer ce pattern en preambule explicite (voir `skills/sort-mails/SKILL.md`, `commands/check-inbox.md`, `commands/process-todo.md`).
