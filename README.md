# TodoMail

Plugin de traitement intelligent des emails reçus et de gestion d'agenda pour Claude Desktop (Cowork).

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
| `/check-inbox` | Télécharge les mails et les trie dans les catégories d'action |
| `/process-todo` | Exécution des instructions du dashboard : archivage, classement des pièces jointes, rédaction de projets d'arbitrage, transmission, préparation de livrables |
| `/briefing` | Génère des dossiers de préparation pour les réunions (déposés dans `to-brief/`) |
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

## Agents

| Agent | Description |
|-------|-------------|
| `mail-analyzer` | Analyse exhaustive d'un mail unique dans un contexte isolé : lecture du mail et des PJ, contextualisation RAG, classification, détection agenda avec vérification de disponibilité, production de synthèses multi-niveaux. Produit un `_analysis.json` exploité par `sort-mails`. |

## Dashboard interactif

Le fichier `dashboard.html` (copié à la racine du répertoire de travail par `/start`) est une interface web locale permettant à l'utilisateur de naviguer entre les catégories de mails triés, consulter les synthèses, et valider ses décisions. Il fonctionne sans serveur backend via l'API File System Access (navigateurs Chromium). Voir `README.dashboard.md` pour la documentation technique complète.

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
│   └── mail-analyzer.md
├── skills/
│   ├── sort-mails/
│   │   └── SKILL.md
│   ├── read-odf/
│   │   ├── SKILL.md
│   │   ├── requirements.txt
│   │   └── scripts/
│   │       └── read_odf.py
│   ├── memory-management/
│   │   └── SKILL.md
│   ├── agenda/
│   │   └── SKILL.md
│   ├── disponibilites/
│   │   └── SKILL.md
│   ├── detection-conflits/
│   │   └── SKILL.md
│   └── dashboard.html
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
├── to-send/                    ← projets de mails à envoyer
├── to-work/                    ← dossiers à travailler
├── to-brief/                   ← dossiers de préparation des réunions
├── docs/                       ← base documentaire (indexée par le connecteur MCP/RAG)
├── consult.md                  ← registre des consultations en cours
├── dashboard.html              ← interface interactive de gestion des mails
├── CLAUDE.md                   ← mémoire courante (~250 lignes max)
└── memory/
    ├── people/                 ← profils des collaborateurs
    ├── projects/               ← synthèses des dossiers/sujets
    └── context/                ← structure, équipes, process, réunions récurrentes, lieux, préférences agenda
```

## Configuration

Le plugin travaille directement dans le répertoire sélectionné par l'utilisateur pour la tâche Cowork. Aucune configuration de chemin n'est nécessaire : tout est créé automatiquement par la commande `/start`, y compris le fichier `dashboard.html` placé à la racine du répertoire de travail.

La configuration IMAP (serveur, identifiants), les paramètres d'indexation et la configuration des calendriers iCalendar sont gérés par le connecteur MCP `~~todomail-mcp` via son fichier `.env`.

## Connecteurs

Ce plugin s'appuie sur le connecteur suivant :

| Connecteur | Rôle | Obligatoire |
|------------|------|-------------|
| `~~todomail-mcp` | Gestion IMAP, recherche RAG (base documentaire, organigramme, contextualisation) et calendriers iCalendar | Oui |

### Connecteur MCP (`~~todomail-mcp`)

Fournit la gestion IMAP (téléchargement, indexation des mails), l'indexation et la recherche RAG, et la consultation des calendriers iCalendar. Voir `CONNECTORS.md` pour les détails.

## Cycle de vie des pending_emails.json

Les fichiers `pending_emails.json` servent d'interface entre Claude et le dashboard. Leur cycle de vie suit des règles strictes pour éviter la persistance de données périmées :

1. **Génération (`sort-mails` v1.0.0+)** — L'agent `mail-analyzer` est lancé en parallèle sur chaque mail et produit un `_analysis.json` par mail. Le skill `sort-mails` exploite ensuite ces fichiers pour trier les mails et générer les `pending_emails.json`. Avant de générer les nouveaux fichiers, le skill écrase systématiquement les 7 fichiers `pending_emails.json` avec un tableau vide `[]`. Ensuite, seuls les sous-répertoires contenant effectivement des mails sont peuplés. Si aucun nouveau mail n'a été trié (inbox vide), la purge et la régénération sont ignorées pour préserver les synthèses existantes. Les mails liés à l'agenda sont enrichis d'un champ optionnel `agenda-info` contenant les informations de disponibilité et de conflits.

2. **Mise à jour incrémentale (`process-todo` v0.27.0+)** — Chaque action exécutée (suppression, déplacement, archivage, traitement complexe) retire immédiatement l'entrée correspondante du `pending_emails.json` de la catégorie source. Lors d'un déplacement inter-catégories, une nouvelle entrée est ajoutée dans le `pending_emails.json` de la catégorie destination (y compris le champ `agenda-info` s'il était présent dans l'entrée source). Depuis la v0.30.0, les mails déplacés sont ensuite automatiquement traités comme une action `other` dans leur catégorie de destination, ce qui retire l'entrée ajoutée lors de la finalisation du traitement. Un tableau vide `[]` est fonctionnellement équivalent à l'absence de fichier pour le dashboard.

3. **Vérification de cohérence (`process-todo` v0.27.0+, Étape 4)** — En fin de traitement, une vérification structurelle s'assure que chaque entrée `id` dans les `pending_emails.json` correspond à un sous-répertoire de mail réellement présent. Les entrées orphelines sont retirées. Les fichiers `instructions.json` et `_deferred.json` traités sont écrasés avec `[]`.

## Dépendances

- `odfpy` (Python) — pour la lecture directe des fichiers OpenDocument par Claude (`pip install odfpy`)

## Changelog

### v0.31.0

- **Refonte majeure : architecture parallèle pour le tri des mails**
  - **Nouvel agent `mail-analyzer`** — Agent autonome qui analyse un mail unique dans un contexte isolé : lecture du mail et de toutes les pièces jointes, contextualisation RAG, classification, détection agenda avec vérification de disponibilité et de conflits, production de synthèses multi-niveaux. Produit un fichier `_analysis.json` dans le répertoire du mail.
  - **sort-mails v1.0.0** — Refonte complète du flux de tri. Les mails sont désormais analysés en parallèle par des agents `mail-analyzer` indépendants (un par mail), puis triés et les `pending_emails.json` générés exclusivement à partir des `_analysis.json`. Suppression de la triple lecture des mails (classification, synthèse anti-hallucination, vérification par sondage). Suppression de la vérification par sondage (rendue inutile par l'isolation des contextes). Ajout de `Task` dans les `allowed-tools`.
- **Gains de performance :**
  - Réduction drastique de la consommation de contexte (les mails ne s'accumulent plus dans le contexte principal)
  - Exécution parallèle des analyses (temps dominé par le mail le plus lent, pas la somme)
  - Élimination des compressions de contexte en cours d'exécution
- **Documentation :**
  - **README.md** — Ajout de la section Agents dans l'architecture, mise à jour de l'arborescence, cycle de vie des `pending_emails.json`, changelog

### v0.30.0

- **Améliorations fonctionnelles :**
  - **process-todo** — Traitement automatique après déplacement inter-catégories : lorsqu'un mail est reclassé via le dashboard vers une autre catégorie, il est désormais automatiquement traité comme une action `other` dans la catégorie de destination, évitant un aller-retour avec le dashboard. Les déplacements vers `do-read-quick` sont traités immédiatement (archivage). Les déplacements vers les autres catégories (`do-read-long`, `do-decide`, `do-consult-and-decide`, `do-other`, `do-self`) sont mis en file d'attente via `todo/_deferred.json` et traités en Étape 3 avec les handlers appropriés (y compris les ARRÊTS OBLIGATOIRES pour les catégories interactives). Le champ `agenda-info` est explicitement recopié lors des déplacements inter-catégories.
- **Documentation :**
  - **README.md** — Mise à jour du cycle de vie des `pending_emails.json` (traitement automatique post-déplacement, nettoyage de `_deferred.json`)

### v0.29.0

- **Corrections de bugs :**
  - Correction du nommage `/check_agenda` → `/check-agenda` dans tous les fichiers (cohérence kebab-case)
  - Ajout de `AskUserQuestion` dans les `allowed-tools` du skill `agenda` (fallback lieux inconnus)
  - Correction du skill `disponibilites` : ajout d'un appel `fetch_calendar_events` (étape 1b) pour pouvoir calculer les buffers de déplacement à partir des événements adjacents
  - Harmonisation de la taille cible de CLAUDE.md à ~250 lignes dans le skill `memory-management`
- **Améliorations fonctionnelles :**
  - **dashboard.html** — Affichage des informations `agenda-info` : badge compact (type + disponibilité) dans la carte principale et panneau détaillé (dates, conflits, créneaux alternatifs) dans la section dépliable
  - **process-todo** — Exploitation du champ `agenda-info` dans les 4 handlers d'actions complexes (`do-decide`, `do-consult-and-decide`, `do-other`, `do-self`) : intégration des conflits, disponibilités et créneaux alternatifs dans les arbitrages et transmissions
  - **start** — Ajout de la création de `memory/context/preferences-agenda.md` lors du bootstrap calendrier (point 2b)
  - **/briefing** — Ajout d'une étape de mise à jour de la mémoire (nouveaux participants, sujets, lieux). Ajout de `Task` dans les `allowed-tools` pour parallélisation des recherches
  - **/check-agenda** — Ajout d'une étape de mise à jour de la mémoire (nouveaux lieux, réunions récurrentes, préférences agenda)
  - **CONNECTORS.md** — Refonte du tableau d'utilisation des tools : ajout de la colonne `/check-inbox`, distinction appels directs (✓) / indirects via skills (i), ajout des tools `update_index`, `fetch_calendar_events` et `get_availability` manquants
- **Optimisations :**
  - **sort-mails** — Pré-chargement calendrier unique : un seul appel `fetch_calendar_events` + `get_availability` sur 14 jours quand des mails liés à l'agenda sont détectés, au lieu d'appels redondants par mail
  - **Externalisation de la géographie** — Remplacement des données géographiques codées en dur (Clermont-Ferrand, Saulzet-le-Froid, Puy-de-Dôme) par des références à `memory/context/lieux.md` et CLAUDE.md dans les skills `disponibilites`, `detection-conflits`, `agenda` et la commande `/check-agenda`
- **Documentation :**
  - **README.dashboard.md** — Ajout de la documentation du champ optionnel `agenda-info` (structure, affichage dashboard)

### v0.28.0

- **Nouveaux skills :**
  - `agenda` v1.0.0 — Connaissance du programme de l'utilisateur (consultation calendrier, enrichissement contextuel, détection conflits, signalement déplacements)
  - `disponibilites` v1.0.0 — Connaissance des créneaux libres avec filtres contextuels (buffer déplacement, habitudes, préférences, niveaux de confiance)
  - `detection-conflits` v1.0.0 — Détection des conflits, superpositions, temps de déplacement insuffisant et surcharge dans l'agenda
- **Nouvelles commandes :**
  - `/briefing` — Génération de dossiers de préparation pour les réunions (déposés dans `to-brief/`)
  - `/check-agenda` — Audit de cohérence et faisabilité de l'agenda avec rapport structuré et propositions correctives
- **sort-mails v0.15.0** — Détection des mails liés à l'agenda (demandes de RDV, invitations, changements, annulations, propositions de créneau). Enrichissement automatique avec vérification de disponibilité et détection de conflits. Ajout du champ optionnel `agenda-info` dans les `pending_emails.json`
- **memory-management v0.3.0** — Ajout des sections mémoire calendrier : réunions récurrentes (`memory/context/reunions-recurrentes.md`), lieux fréquents (`memory/context/lieux.md`), préférences agenda (`memory/context/preferences-agenda.md`). Nouvelles sections dans CLAUDE.md : "Réunions récurrentes", "Lieux fréquents", "Préférences agenda". Objectif taille CLAUDE.md porté à ~250 lignes
- **start** — Ajout du répertoire `to-brief/`. Ajout du point 2b pour le bootstrap des calendriers (réunions récurrentes, lieux fréquents). Mise à jour du format CLAUDE.md avec les nouvelles sections agenda. Ajout des commandes `/briefing` et `/check-agenda` dans les messages d'orientation
- **CONNECTORS.md** — Ajout des tools calendrier (`list_calendars`, `fetch_calendar_events`, `get_availability`, `sync_calendars`). Ajout du tableau d'utilisation des tools par composant
- **plugin.json** — Ajout des keywords `calendar`, `agenda`, `briefing`
- **README.md** — Refonte complète pour intégrer l'architecture skills/commandes, les fonctionnalités agenda, la nouvelle arborescence et le changelog détaillé

### v0.27.0

- **sort-mails v0.14.0** — Si inbox est vide, ne plus purger ni régénérer les `pending_emails.json` existants (préservation des synthèses)
- **process-todo** — Ajout de la mise à jour du `pending_emails.json` de la catégorie destination lors des déplacements inter-catégories. Remplacement de la suppression des `instructions.json` par un écrasement avec `[]` (compatibilité Cowork). Retrait du champ `version` du frontmatter (conformité conventions commandes Anthropic)
- **memory-management v0.2.0** — Enrichissement de la description avec des phrases de déclenchement (triggering). Ajout de `process-todo` dans la section intégration
- **README.dashboard.md** — Correction du libellé de l'action `delete` (déplacement vers `to-clean-by-user/`, pas suppression définitive)
- **README.md** — Ajout de la section Dashboard interactif. Mise à jour du cycle de vie des `pending_emails.json`

### v0.26.0

- **sort-mails v0.13.0** — Ajout d'une purge préalable des `pending_emails.json` (écriture de `[]`) en début d'Étape 2, pour éliminer tout résidu d'un cycle précédent
- **process-todo** — Mise à jour incrémentale des `pending_emails.json` au fil de l'eau (après chaque action simple et chaque finalisation complexe) au lieu d'une régénération complète en Étape 4. L'Étape 4 est simplifiée en vérification de cohérence structurelle (correspondance `id` ↔ répertoires présents)
