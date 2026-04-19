# TodoMail

Plugin de traitement intelligent des emails reçus et de gestion d'agenda pour Claude Code.

## Présentation

TodoMail transforme Claude en assistant professionnel pour la gestion du courrier entrant et de l'agenda. Il télécharge les mails via un connecteur MCP `~~todomail-mcp` IMAP, les trie automatiquement par catégorie d'action, et offre une interface interactive (dashboard) pour gérer l'ensemble des catégories de mails triés. Il intègre également des fonctionnalités de gestion d'agenda : consultation du programme, vérification des disponibilités, détection de conflits, préparation de réunions et audit de cohérence.

Le plugin intègre un système de mémoire à deux niveaux (mémoire courante + mémoire spécifique) qui permet à Claude de comprendre le contexte professionnel de l'utilisateur : collaborateurs, acronymes, dossiers en cours, préférences de rédaction, réunions récurrentes, lieux fréquents et préférences agenda.

## Architecture : skills, agents et commandes

Le plugin distingue trois types de composants :

- **Skills** : capacités que Claude mobilise de façon autonome selon le contexte, sans commande explicite. Les skills sont des briques réutilisables, appelables par d'autres skills, par des commandes, ou directement par Claude lorsque le prompt utilisateur le justifie.
- **Agents** : sous-tâches autonomes exécutées dans un contexte isolé via `Task`. Chaque agent a son propre contexte, ce qui évite l'accumulation de tokens dans le contexte principal. Les agents sont orchestrés par les skills ou les commandes.
- **Commandes** (préfixées par `/`) : points d'entrée explicites déclenchés uniquement par l'utilisateur. Elles orchestrent un ou plusieurs skills pour produire un résultat structuré.

Principe : si Claude doit pouvoir utiliser une capacité de sa propre initiative, c'est un skill. Si c'est un acte délibéré de l'utilisateur avec production d'un livrable, c'est une commande. Si c'est une sous-tâche isolée lancée en parallèle avec son propre contexte, c'est un agent.

## Commandes

| Commande | Description |
|----------|-------------|
| `/start` | Initialise le système todomail, crée les répertoires, place le dashboard et bootstrap la mémoire de travail |
| `/check-inbox` | Télécharge les mails et les trie dans les catégories d'action (flags `--strict`, `--retry`) |
| `/process-todo` | Exécution des instructions du dashboard : archivage, classement des pièces jointes, rédaction de projets d'arbitrage, transmission, préparation de livrables (flags `--strict`, `--retry`, `--batch-validate`) |
| `/briefing` | Génère des dossiers de préparation pour les réunions (déposés dans `to-brief/`). Flag `--parallel` pour fan-out Task au-delà de 5 réunions. |
| `/check-agenda` | Audite la cohérence et la faisabilité de l'agenda sur une période |

## Skills

| Skill | Description |
|-------|-------------|
| `sort-mails` | Logique de tri des mails par catégorie, avec détection et enrichissement des mails liés à l'agenda |
| `memory-management` | Système de mémoire à deux niveaux incluant la connaissance calendrier (réunions récurrentes, lieux, préférences agenda) |
| `read-odf` | Extraction de texte depuis les fichiers OpenDocument (.odt, .ods, .odp) via un script Python |
| `agenda` | Connaissance du programme de l'utilisateur sur une période (brique fondamentale calendrier) |
| `disponibilites` | Connaissance des créneaux libres avec filtres contextuels (déplacements, habitudes, préférences) |
| `detection-conflits` | Détection des conflits, superpositions et incohérences dans l'agenda |
| `briefing` | Wrapper auto-déclenchable par langage naturel (« prépare la réunion COPIL de mercredi »). Délègue à la commande `/briefing`. |
| `check-agenda` | Wrapper auto-déclenchable par langage naturel (« audite mon agenda »). Délègue à la commande `/check-agenda`. |
| `classify-attachment` | Classement des pièces jointes dans `docs/` selon la structure canonique AURA/MIN avec garde-fou structurel |

## Agents

| Agent | Description |
|-------|-------------|
| `mail-prefilter` | Pré-filtrage batch des mails évidents (newsletters, accusés de réception) à partir des seules métadonnées. Un unique appel Haiku 4.5 retourne un classement `trash` / `do-read-quick` / `unsure` pour chaque mail du batch. Utilisé par `sort-mails` avant l'analyse principale Opus 1M. |

Depuis la v2.0.0, les commandes `check-inbox`, `process-todo`, `briefing`
et `check-agenda` n'utilisent plus d'agents dédiés : la logique d'analyse,
de validation et de finalisation est intégrée dans le contexte principal
(Opus 4.6 1M). L'idempotence des opérations fichiers (via `lib/fs_utils.py`),
le cache RAG partagé (via `lib/rag_cache.py`) et l'écriture d'un
`_treatment.json` par mail permettent la reprise sur erreur via `--retry`.

## Dashboard interactif

Le fichier `dashboard.html` (copié à la racine du répertoire de travail par `/start`) est une interface web locale avec deux vues principales :

- **Catégorisation** : navigation entre les catégories de mails triés, consultation des synthèses et ajustement des actions. Les fichiers `instructions.json` sont générés et mis à jour automatiquement (valeurs par défaut : SUPPRIMER pour la Corbeille, TRAITER pour les autres catégories).
- **Tâches** : gestionnaire de tâches en 3 sections — suivi des consultations en cours (`consult.md`), mails à envoyer (`to-send/`), et travail à faire (`to-work/`). Chaque section offre aperçu, édition, copie presse-papier et suppression avec confirmation inline.

Le dashboard dispose d'un menu de navigation extensible (Catégorisation, Mémoire, Tâches). Il fonctionne sans serveur backend via l'API File System Access. Voir `README.dashboard.md` pour la documentation technique complète.

### Navigateurs supportés

Le dashboard **nécessite un navigateur basé sur Chromium** (Chrome, Edge, Arc, DIA, Brave, Opera, Vivaldi). L'API File System Access, indispensable pour lire et écrire les fichiers du workspace sans backend, n'est pas disponible dans Safari, Orion (WebKit) ni Firefox.

Si vous ouvrez `dashboard.html` dans un navigateur non supporté, un écran d'avertissement plein page s'affiche avec la liste des navigateurs compatibles.

Un mode serveur HTTP local compatible avec tous les navigateurs modernes (Safari, Orion, Firefox inclus) est planifié en Phase 7 du refactoring (v2.1.x). Voir `REFACTOR_PLAN.md` section Phase 7 pour le détail.

## Catégories de tri

| Catégorie | Description |
|-----------|-------------|
| `trash` | Spam, mails sans intérêt |
| `do-read-quick` | Information rapide, pas de pièce jointe |
| `do-read-long` | Documents à lire, pas d'action requise |
| `do-decide` | Arbitrage et Demande de validation simple |
| `do-consult-and-decide` | Arbitrage nécessitant consultation |
| `do-other` | Production à confier aux services |
| `do-self` | Production personnelle demandée |

## Fonctionnalités agenda

Le plugin intègre des fonctionnalités de gestion d'agenda en lecture seule, basées sur les flux iCalendar configurés dans le connecteur MCP :

- **Consultation du programme** (skill `agenda`) : Claude connaît le programme de l'utilisateur et l'utilise proactivement pour contextualiser les réponses
- **Vérification des disponibilités** (skill `disponibilites`) : avec prise en compte des déplacements, habitudes et préférences
- **Détection de conflits** (skill `detection-conflits`) : superpositions, temps de déplacement insuffisant, surcharge
- **Préparation de réunions** (commande `/briefing`) : dossiers de briefing avec contexte, documents de référence et échanges récents
- **Audit d'agenda** (commande `/check-agenda`) : rapport structuré avec propositions d'actions correctives
- **Enrichissement du tri mail** (skill `sort-mails`) : les mails liés à l'agenda sont détectés et enrichis avec les informations de disponibilité et de conflits

Les agendas sont consultés en lecture seule : aucune modification n'est effectuée sur les calendriers.

## Arborescence

```
todomail/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── start.md
│   ├── check-inbox.md
│   ├── process-todo.md
│   ├── briefing.md
│   └── check-agenda.md
├── agents/
│   └── mail-prefilter.md
├── skills/
│   ├── sort-mails/SKILL.md
│   ├── read-odf/
│   │   ├── SKILL.md
│   │   ├── requirements.txt
│   │   └── scripts/read_odf.py
│   ├── memory-management/SKILL.md
│   ├── agenda/SKILL.md
│   ├── disponibilites/SKILL.md
│   ├── detection-conflits/SKILL.md
│   ├── briefing/SKILL.md        ← wrapper auto-déclenchable (Phase 6)
│   ├── check-agenda/SKILL.md    ← wrapper auto-déclenchable (Phase 6)
│   ├── classify-attachment/SKILL.md
│   └── dashboard.html
├── hooks/                       ← 5 hooks Claude Code (Phase 4)
│   ├── hooks.json
│   ├── session_start.py
│   ├── enforce_classify.py
│   ├── invalidate_dashboard_cache.py
│   ├── inject_context.py
│   ├── pre_compact.py
│   └── README.md
├── lib/                         ← 5 helpers Python (Phases 1–5)
│   ├── state.py                 ← state.json persistant + verrous + erreurs
│   ├── fs_utils.py              ← operations fichiers idempotentes + JSON v2
│   ├── rag_cache.py             ← cache RAG en memoire de session
│   ├── error_modes.py           ← strategie d'erreur (lenient/strict/resume)
│   ├── config.py                ← .todomail-config.json (desambiguation MCP alpha.2)
│   └── README.md
├── CONNECTORS.md
├── README.md
└── README.dashboard.md
```

Après initialisation (`/start`), le répertoire de travail de l'utilisateur contient :

```
répertoire de travail/
├── inbox/                      ← mails téléchargés en attente de tri (peuplée par le connecteur MCP/RAG)
├── todo/
│   ├── trash/                  ← mails à supprimer
│   ├── do-read-quick/          ← lecture rapide
│   ├── do-read-long/           ← documents à lire
│   ├── do-decide/              ← arbitrage simple
│   ├── do-consult-and-decide/  ← arbitrage après consultation
│   ├── do-other/               ← production à confier
│   └── do-self/                ← production personnelle
├── mails/                      ← archive des mails traités (AAAA/MM/) (indexée par le connecteur MCP/RAG)
├── to-clean-by-user/           ← fichiers à supprimer manuellement
├── to-send/                    ← projets de mails à envoyer (frontmatter YAML : to, cc, subject, date, ref_mail_id)
├── to-work/                    ← dossiers à travailler
├── to-brief/                   ← dossiers de préparation des réunions
├── docs/                       ← base documentaire (indexée par le connecteur MCP/RAG)
├── consult.md                  ← registre des consultations en cours
├── dashboard.html              ← interface interactive de gestion des mails
├── .todomail-config.json       ← config MCP locale (expected_rag_name, géré par /start)
├── .todomail/                  ← runtime du plugin (alpha.8+) : state.json, memory_cache.json,
│                                  invalidate.txt, hooks.log, retry_request.txt, errors_dismiss.txt,
│                                  precompact_snapshot_*.json — géré automatiquement, gitignoré
├── CLAUDE.md                   ← mémoire courante (~250 lignes max)
└── memory/
    ├── people/                 ← profils des collaborateurs
    ├── projects/               ← synthèses des dossiers/sujets
    └── context/                ← structure, équipes, process, réunions récurrentes, lieux, préférences agenda
```

## Configuration

Le plugin travaille directement dans le répertoire de travail de l'utilisateur. Aucune configuration de chemin n'est nécessaire : tout est créé automatiquement par la commande `/start`, y compris le fichier `dashboard.html` placé à la racine du répertoire de travail.

La configuration IMAP (serveur, identifiants), les paramètres d'indexation et la configuration des calendriers iCalendar sont gérés par le connecteur MCP `~~todomail-mcp` via son fichier `.env`.

### Désambiguation multi-serveurs MCP

Si plusieurs serveurs MCP `~~todomail-mcp` sont connectés dans Claude Desktop (par exemple un serveur professionnel et un serveur personnel), le plugin désambigue via le fichier `.todomail-config.json` (à la racine du workspace, géré par `/start`, gitignoré). Ce fichier contient `expected_rag_name` et est vérifié en début de toutes les commandes MCP-sensibles (`/check-inbox`, `/process-todo`, `/briefing`, `/check-agenda`) par appel au tool `status` du MCP. Voir `CONNECTORS.md` section « Désambiguation multi-serveurs » pour le détail du mécanisme.

## Connecteurs

Ce plugin s'appuie sur le connecteur suivant :

| Connecteur | Rôle | Obligatoire |
|------------|------|-------------|
| `~~todomail-mcp` | Gestion IMAP, recherche RAG (base documentaire, organigramme, contextualisation) et calendriers iCalendar | Oui |

### Connecteur MCP (`~~todomail-mcp`)

Fournit la gestion IMAP (téléchargement, indexation des mails), l'indexation et la recherche RAG, et la consultation des calendriers iCalendar. Voir `CONNECTORS.md` pour les détails.

## Cycle de vie des pending_emails.json

Les fichiers `pending_emails.json` servent d'interface entre Claude et le dashboard. Leur cycle de vie suit des règles strictes pour éviter la persistance de données périmées :

1. **Génération (`sort-mails` v2.0.0+)** — Le skill `sort-mails` traite les mails en flux dans le contexte principal Opus 1M, avec un pré-filtrage préalable par l'agent `mail-prefilter` (Haiku 4.5, batch unique sur les métadonnées) pour écarter rapidement les évidences (newsletters, accusés). Les mails restants sont analysés par Claude lui-même (lecture du corps et des PJ, classification, détection agenda, contextualisation RAG mémoïsée via `lib/rag_cache.py`). Un `_analysis.json` est écrit par mail dans son répertoire (artefact de reprise en cas d'interruption). Les `pending_emails.json` v2 (wrapper `_meta` + `emails`) sont ensuite générés par fusion : les entrées existantes sont conservées et dédoublonnées par `id`, pas de purge inconditionnelle. Les mails liés à l'agenda sont enrichis d'un champ optionnel `agenda-info` contenant les informations de disponibilité et de conflits.

2. **Mise à jour incrémentale (`process-todo` v0.27.0+)** — Chaque action exécutée (suppression, déplacement, archivage, traitement complexe) retire immédiatement l'entrée correspondante du `pending_emails.json` de la catégorie source. Lors d'un déplacement inter-catégories, une nouvelle entrée est ajoutée dans le `pending_emails.json` de la catégorie destination (y compris le champ `agenda-info` s'il était présent dans l'entrée source). Depuis la v0.30.0, les mails déplacés sont ensuite automatiquement traités comme une action `other` dans leur catégorie de destination, ce qui retire l'entrée ajoutée lors de la finalisation du traitement. Un tableau vide `[]` est fonctionnellement équivalent à l'absence de fichier pour le dashboard.

3. **Vérification de cohérence (`process-todo` v0.27.0+, Étape 4)** — En fin de traitement, une vérification structurelle s'assure que chaque entrée `id` dans les `pending_emails.json` correspond à un sous-répertoire de mail réellement présent. Les entrées orphelines sont retirées. Les fichiers `instructions.json` et `_deferred.json` traités sont écrasés avec `[]`.

## Dépendances

- `markitdown` (Python, Microsoft) — conversion unifiée des pièces jointes bureautiques (`.docx`, `.xlsx`, `.pptx`, `.rtf`, `.epub`) en Markdown (`pip install markitdown --break-system-packages`)
- `odfpy` (Python) — pour la lecture directe des fichiers OpenDocument par Claude (`pip install odfpy --break-system-packages`)

## Compatibilité

À partir de la version 2.0, le plugin TodoMail est exclusivement compatible avec **Claude Code** (dans Claude Desktop ou en CLI). Il n'est plus compatible avec Claude Cowork. Pour la dernière version compatible Cowork, voir le tag `v1.4.1`.

## Migration depuis v1.x

La v2.0.0 apporte des ruptures importantes par rapport à la v1.x. Les utilisateurs d'une v1.x qui veulent passer à la v2 doivent suivre cette procédure :

### Breaking changes

- **Plus de compatibilité Cowork** : tout le code `allow_cowork_file_delete` a été supprimé (Phase 1). Les workflows Cowork restent sur le tag `v1.4.1`.
- **Agents supprimés** : `mail-analyzer` (Phase 2) et `todo-processor` (Phase 3) ont été supprimés. La logique est intégrée dans le contexte principal Opus 4.6 1M. L'agent `mail-prefilter` (Haiku 4.5) est conservé pour le pré-filtrage.
- **Nouveau schéma JSON v2** : `pending_emails.json` et `instructions.json` sont désormais des objets wrappés `{_meta, emails}` / `{_meta, instructions}`. La rétrocompatibilité en lecture (v1 = tableau brut, v2 = wrapper) est assurée par `lib/fs_utils.read_v2_json` côté Python et par `extractEmails(data)` / `extractInstructionsAndMeta(data)` côté dashboard.
- **Runtime du plugin dans `.todomail/`** : tout l'état runtime pour un workspace vit dans `$CLAUDE_PROJECT_DIR/.todomail/` (state.json, memory_cache.json, invalidate.txt, hooks.log…). Plus de mirror à la racine du workspace.
- **Dashboard Chromium only** : le dashboard v3 nécessite un navigateur basé sur Chromium (Chrome, Edge, Arc, DIA, Brave, Opera, Vivaldi). Safari, Orion, Firefox affichent un écran d'avertissement. Le mode serveur HTTP local (Phase 7) résoudra cette limite en v2.1.x.
- **Désambiguation MCP via `.todomail-config.json`** : le fichier `.mcp.json` initialement prévu en Phase 1 a été abandonné en alpha.2 (inadapté à Claude Desktop). La désambiguation passe désormais par `.todomail-config.json` + vérification `status.rag_name` runtime.

### Étapes de migration

1. **Installer la v2.0.0** dans Claude Desktop via *Customize → Plugins → todomail → Update* (ou télécharger `todomail-v2.0.0.zip` depuis la release GitHub).
2. **Repartir d'un `/start` propre** dans votre workspace v1 :
   - Le fichier `.todomail-config.json` sera créé automatiquement par `/start` (choix du serveur MCP).
   - Le dossier `.todomail/` sera créé automatiquement au premier `acquire_lock` (généralement via `/check-inbox`).
   - Les anciens fichiers à la racine du workspace (`.todomail-state.json`, `dashboard_invalidate.txt`) deviennent du bruit inoffensif et peuvent être supprimés manuellement.
3. **Vérifier les permissions navigateur** : rouvrir `dashboard.html` dans un navigateur Chromium. Le dashboard vous demandera de sélectionner le workspace au premier lancement (API File System Access).

### Pour rester en v1.x

Si vous préférez ne pas migrer, le tag `v1.4.1` reste disponible et conserve la compatibilité Cowork intégrale.

## Changelog

Voir [CHANGELOG.md](CHANGELOG.md) pour l'historique détaillé des versions.
