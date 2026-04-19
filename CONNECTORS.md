# Connectors

## How tool references work

Plugin files use `~~category` as a placeholder for whatever tool the user
connects in that category. Plugins are tool-agnostic — they describe
workflows in terms of categories rather than specific products.

## Connectors for this plugin

| Category | Placeholder | Options | Obligatoire |
|----------|-------------|---------|-------------|
| Gestion emails et RAG | `~~todomail-mcp` | Serveur MCP unique fournissant à la fois la gestion IMAP et la recherche RAG sur les documents et emails | Oui |
| Automatisation navigateur | Claude in Chrome | Extension Chrome pour piloter le navigateur de l'utilisateur | Recommandé |

## Tools fournis par le connecteur

Le plugin s'appuie sur un connecteur MCP  (`~~todomail-mcp`) qui fournit les tools suivants :

**Note v2.1.0 :** le téléchargement des mails IMAP n'est plus de la responsabilité du connecteur MCP. Il est pris en charge par le skill interne `fetch-imap` du plugin, qui lit la configuration IMAP depuis `.todomail-config.json` (bloc `imap`). Le connecteur ne gère désormais que le RAG et les calendriers.

### Indexation et recherche documentaire (RAG)

- `update_index` — Met à jour l'index RAG avec les fichiers modifiés (documents et/ou mails). Appelé **directement par l'utilisateur** depuis Claude Desktop (pas de commande plugin dédiée) quand il souhaite rafraîchir l'index, typiquement après `/process-todo`. Tool MCP `task=True` (peut durer plusieurs minutes) — ne pas l'appeler en flux depuis une commande plugin pour éviter les timeouts côté client.
- `status` — Retourne l'état actuel de l'index (compteurs, configuration, dernière indexation)
- `search_mail` — Recherche hybride (vectorielle + BM25) dans les archives emails indexés
- `search_doc` — Recherche hybride dans la base documentaire (Word, Excel, PDF, etc.)
- `search_all` — Recherche combinée dans les documents ET les emails

### Gestion des calendriers iCalendar

- `list_calendars` — Liste des agendas configurés (identifiant, nom, catégorie, dernière synchro)
- `fetch_calendar_events` — Lecture des événements sur une plage de dates avec filtres optionnels (agendas, texte, événements annulés)
- `get_availability` — Calcul des créneaux libres (fusion d'intervalles, heures ouvrables configurables)
- `sync_calendars` — Rafraîchissement des flux ICS (tâche de fond)

Ces tools sont utilisés par les skills `sort-mails`, `agenda`, `disponibilites`, `detection-conflits`, par les commandes `/process-todo`, `/briefing`, `/check-agenda`, et par les wrappers skills auto-déclenchables `briefing` et `check-agenda`. L'agent `mail-prefilter` n'accède pas au MCP (il opère sur les seules métadonnées).

**Note :** Le plugin est en **lecture seule** sur les agendas. Aucune modification, création ou suppression d'événement n'est effectuée.

### Utilisation des tools par composant

Les tools sont utilisés directement ou indirectement (via des skills ou des agents) par les composants suivants. Les appels indirects sont marqués par `(i)`.

| Tool | sort-mails | process-todo | agenda | disponibilites | detection-conflits | /check-inbox | /briefing | /check-agenda | briefing (skill) | check-agenda (skill) | /start |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `search_mail` | ✓ | ✓ | ✓ | | | (i) | ✓ | | (i) | | ✓ |
| `search_doc` | ✓ | ✓ | ✓ | | | (i) | ✓ | | (i) | | ✓ |
| `search_all` | ✓ | ✓ | ✓ | | | (i) | ✓ | | (i) | | ✓ |
| `list_calendars` | | | ✓ | | | | | | | | ✓ |
| `fetch_calendar_events` | ✓ | ✓ | ✓ | ✓ | | | (i) | ✓ | (i) | (i) | ✓ |
| `get_availability` | ✓ | ✓ | | ✓ | | | | ✓ | | (i) | |
| `sync_calendars` | | | ✓ | | | | | | | | ✓ |
| `status` | | | | | | ✓ | ✓ | ✓ | | | ✓ |

> `update_index` n'apparaît pas dans ce tableau : aucune commande ni skill du plugin ne l'appelle. L'utilisateur le déclenche directement depuis Claude Desktop quand il souhaite rafraîchir le RAG (typiquement après `/process-todo`).

**Légende :** ✓ = appel direct du tool MCP | (i) = appel indirect via un skill intermédiaire (`/check-inbox` délègue à `sort-mails` ; `/briefing` et `/check-agenda` appellent les skills `agenda`, `disponibilites`, `detection-conflits` ; les wrappers skills `briefing` et `check-agenda` délèguent aux commandes homonymes).

**Refonte v2.0.0 (Phases 2/3/6) :** Les agents `mail-analyzer` (Phase 2) et `todo-processor` (Phase 3) ont été supprimés. La logique est intégrée directement dans les commandes/skills, en exploitant le contexte 1M d'Opus 4.6. Les résultats MCP sont mémoïsés via `lib/rag_cache.py` (obligatoire sur tous les appels `search_*`, `get_availability`, `fetch_calendar_events`). L'agent `mail-prefilter` n'apparaît pas car il n'accède pas au MCP (métadonnées seulement). Le tool `status` est appelé par toutes les commandes MCP-sensibles pour la désambiguation multi-serveurs (voir section plus bas).

**Refonte v2.1.0 :** le téléchargement des mails IMAP est désormais pris en charge par le skill interne `fetch-imap` du plugin (plus de dépendance au tool MCP `check_inbox`, retiré du tableau). Corollaire : `update_index` n'est appelé par aucune commande plugin (tool `task=True` côté serveur qui provoque des timeouts client s'il est appelé en flux) — l'utilisateur le déclenche directement dans Claude Desktop après `/process-todo` quand il le souhaite.

**Wrappers skills (Phase 6) :** Les skills auto-déclenchables `briefing` et `check-agenda` ne portent aucune logique propre : ils délèguent aux commandes `/briefing` et `/check-agenda`. Les appels MCP listés avec `(i)` le sont indirectement via cette délégation.

Le connecteur RAG permet notamment de :

- Inférer l'organigramme de la structure pour mieux comprendre les relations entre les différentes personnes
- Connaître le rôle de l'utilisateur et ses responsabilités
- Déterminer quels services sont compétents selon les sujets abordés dans les mails
- Accéder aux connaissances disponibles sur les différents dossiers en cours

## Claude in Chrome

Le connecteur Claude in Chrome permet à Claude de piloter le navigateur de l'utilisateur. Dans le contexte de ce plugin, il est actuellement inutilisé.

### Installation

1. Installer l'extension « Claude in Chrome » dans le navigateur Chrome de l'utilisateur
2. Activer l'extension Claude in Chrome dans les paramètres du navigateur

## Configuration

**Configuration IMAP (plugin, depuis v2.1.0)** — La configuration IMAP (`hostname`, `port`, `username`, `password`, `use_starttls`) est gérée par le plugin lui-même dans le fichier `.todomail-config.json` du workspace, bloc `imap`. Voir la section 0c de `/todomail:start` pour la procédure de configuration interactive. Le fichier est écrit avec `chmod 600` et doit être gitignoré dans le workspace utilisateur (un mot de passe en clair y figure).

**Configuration RAG et indexation (MCP)** — Les paramètres d'indexation (chemins `DOCUMENTS_PATH`, `MAILS_PATH`, modèle d'embeddings, etc.) restent gérés par le connecteur MCP via son fichier `.env`.

## Désambiguation multi-serveurs

Lorsque plusieurs serveurs MCP `~~todomail-mcp` sont connectés simultanément dans Claude Desktop (par exemple un serveur professionnel et un serveur personnel), Claude doit savoir lequel utiliser pour ce workspace. Le plugin utilise un mécanisme de configuration locale :

- Fichier `.todomail-config.json` à la racine du répertoire de travail (géré automatiquement par `/start`, gitignoré)
- Champ `expected_rag_name` qui contient le nom du serveur à utiliser
- Vérification automatique en début de `/check-inbox` et `/process-todo` via le tool MCP `status` (qui retourne le `rag_name` du serveur connecté)

### Configuration initiale

Au premier lancement de `/start`, si aucun fichier `.todomail-config.json` n'existe :

1. Le plugin détecte le(s) serveur(s) archiva connecté(s)
2. Si plusieurs serveurs sont détectés, l'utilisateur choisit lequel utiliser pour ce workspace
3. Le choix est enregistré dans `.todomail-config.json`

### Reconfiguration

Pour changer de serveur pour un workspace donné :
1. Supprimer `.todomail-config.json`
2. Relancer `/start`

### Setup côté serveur

Pour que le mécanisme fonctionne, chaque instance du serveur MCP archiva doit avoir un `RAG_NAME` unique dans son fichier `.env`. Par exemple :
- `RAG_NAME=Archiva-Pro` pour l'instance professionnelle
- `RAG_NAME=Archiva-PERSO` pour l'instance personnelle

Le `rag_name` est alors retourné par le tool `status` et utilisé pour la vérification.
