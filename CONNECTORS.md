# Connectors

## How tool references work

Plugin files use `~~category` as a placeholder for whatever tool the user
connects in that category. Plugins are tool-agnostic — they describe
workflows in terms of categories rather than specific products.

## Connectors for this plugin

| Category | Placeholder | Options | Obligatoire |
|----------|-------------|---------|-------------|
| Gestion emails et RAG | `~~todomail-mcp` | Serveur MCP unique fournissant à la fois la gestion IMAP et la recherche RAG sur les documents et emails | Oui |
| Automatisation navigateur | Claude in Chrome | Extension Chrome + connecteur Cowork pour piloter le navigateur de l'utilisateur | Recommandé |

## Tools fournis par le connecteur

Le plugin s'appuie sur un connecteur MCP  (`~~todomail-mcp`) qui fournit les tools suivants :

### Gestion de la boîte de réception

- `check_inbox` — Télécharge les nouveaux mails depuis un serveur IMAP, enregistre les pièces jointes, et supprime les messages du serveur

### Recherche documentaire (RAG)

- `update_index` — Met à jour l'index RAG avec les fichiers modifiés (documents et/ou mails)
- `status` — Retourne l'état actuel de l'index (compteurs, configuration, dernière indexation)
- `search_mail` — Recherche hybride (vectorielle + BM25) dans les archives emails indexés
- `search_doc` — Recherche hybride dans la base documentaire (Word, Excel, PDF, etc.)
- `search_all` — Recherche combinée dans les documents ET les emails

### Gestion des calendriers iCalendar

- `list_calendars` — Liste des agendas configurés (identifiant, nom, catégorie, dernière synchro)
- `fetch_calendar_events` — Lecture des événements sur une plage de dates avec filtres optionnels (agendas, texte, événements annulés)
- `get_availability` — Calcul des créneaux libres (fusion d'intervalles, heures ouvrables configurables)
- `sync_calendars` — Rafraîchissement des flux ICS (tâche de fond)

Ces tools sont utilisés par les skills `agenda`, `disponibilites`, `detection-conflits`, par les agents `mail-analyzer` et `todo-processor`, et par les commandes `/briefing` et `/check-agenda`.

**Note :** Le plugin est en **lecture seule** sur les agendas. Aucune modification, création ou suppression d'événement n'est effectuée.

### Utilisation des tools par composant

Les tools sont utilisés directement ou indirectement (via des skills ou des agents) par les composants suivants. Les appels indirects sont marqués par `(i)`.

| Tool | sort-mails | mail-analyzer | todo-processor | process-todo | agenda | disponibilites | detection-conflits | /check-inbox | /briefing | /check-agenda | /start |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `check_inbox` | | | | | | | | ✓ | | | |
| `update_index` | | | | | | | | ✓ | | | |
| `search_mail` | (i) | ✓ | ✓ | (i) | ✓ | | | (i) | ✓ | | ✓ |
| `search_doc` | (i) | ✓ | ✓ | (i) | ✓ | | | (i) | ✓ | | ✓ |
| `search_all` | (i) | ✓ | ✓ | (i) | ✓ | | | (i) | ✓ | | ✓ |
| `list_calendars` | | | | | ✓ | | | | | | ✓ |
| `fetch_calendar_events` | (i) | ✓ | | | ✓ | ✓ | | | (i) | (i) | ✓ |
| `get_availability` | (i) | ✓ | | | | ✓ | | | (i) | (i) | |
| `sync_calendars` | | | | | ✓ | | | | | | ✓ |

**Légende :** ✓ = appel direct du tool MCP | (i) = appel indirect via un agent ou un skill intermédiaire (sort-mails délègue à l'agent `mail-analyzer` via `Task` ; process-todo délègue à l'agent `todo-processor` via `Task` ; /briefing et /check-agenda appellent les skills `agenda`, `disponibilites`, `detection-conflits`)

Le connecteur RAG permet notamment de :

- Inférer l'organigramme de la structure pour mieux comprendre les relations entre les différentes personnes
- Connaître le rôle de l'utilisateur et ses responsabilités
- Déterminer quels services sont compétents selon les sujets abordés dans les mails
- Accéder aux connaissances disponibles sur les différents dossiers en cours

## Claude in Chrome

Le connecteur Claude in Chrome permet à Claude de piloter le navigateur de l'utilisateur. Dans le contexte de ce plugin, il est actuellement inutilisé.

### Installation

1. Installer l'extension « Claude in Chrome » dans le navigateur Chrome de l'utilisateur
2. Dans Cowork, activer le connecteur Claude in Chrome dans les paramètres

## Configuration

La configuration IMAP (serveur, identifiants) et les paramètres d'indexation sont gérés par le connecteur MCP via son fichier `.env`.
