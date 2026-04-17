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

Ces tools sont utilisés par les skills `sort-mails`, `agenda`, `disponibilites`, `detection-conflits`, par la commande `/process-todo`, et par les commandes `/briefing` et `/check-agenda`. L'agent `mail-prefilter` n'accède pas au MCP (il opère sur les seules métadonnées).

**Note :** Le plugin est en **lecture seule** sur les agendas. Aucune modification, création ou suppression d'événement n'est effectuée.

### Utilisation des tools par composant

Les tools sont utilisés directement ou indirectement (via des skills ou des agents) par les composants suivants. Les appels indirects sont marqués par `(i)`.

| Tool | sort-mails | process-todo | agenda | disponibilites | detection-conflits | /check-inbox | /briefing | /check-agenda | /start |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `check_inbox` | | | | | | ✓ | | | |
| `update_index` | | | | | | ✓ | | | |
| `search_mail` | ✓ | ✓ | ✓ | | | (i) | ✓ | | ✓ |
| `search_doc` | ✓ | ✓ | ✓ | | | (i) | ✓ | | ✓ |
| `search_all` | ✓ | ✓ | ✓ | | | (i) | ✓ | | ✓ |
| `list_calendars` | | | ✓ | | | | | | ✓ |
| `fetch_calendar_events` | ✓ | ✓ | ✓ | ✓ | | | (i) | (i) | ✓ |
| `get_availability` | ✓ | ✓ | | ✓ | | | (i) | (i) | |
| `sync_calendars` | | | ✓ | | | | | | ✓ |

**Légende :** ✓ = appel direct du tool MCP | (i) = appel indirect via un skill intermédiaire (`/check-inbox` délègue à `sort-mails` ; `/briefing` et `/check-agenda` appellent les skills `agenda`, `disponibilites`, `detection-conflits`).

**Nouveauté v2.0.0-alpha.4 :** Depuis la refonte de `process-todo` (Phase 3), l'agent `todo-processor` est supprimé et les appels MCP sont directs depuis la commande (contexte principal Opus 4.6 1M). Les résultats sont mémoïsés via `lib/rag_cache.py` (obligatoire sur tous les appels `search_*`, `get_availability`, `fetch_calendar_events`). L'agent `mail-prefilter` n'apparaît pas car il n'accède pas au MCP.

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

La configuration IMAP (serveur, identifiants) et les paramètres d'indexation sont gérés par le connecteur MCP via son fichier `.env`.

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
