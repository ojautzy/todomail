# CLAUDE.md — Instructions pour le développement du plugin TodoMail

## Structure du projet

Plugin Claude Code : skills, agents et commandes pour le traitement des emails et la gestion d'agenda.

```
todomail/
├── .claude-plugin/plugin.json   ← manifeste du plugin (source de vérité pour la version)
├── commands/*.md                ← commandes utilisateur (/start, /check-inbox, etc.)
├── agents/*.md                  ← agents autonomes (mail-prefilter, todo-processor)
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
