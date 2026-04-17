---
description: Initialise le système todomail et sa mémoire de travail
allowed-tools: Read, Write, Bash(mkdir:*), Bash(ls:*), Bash(cp:*), Glob, Grep, Task, AskUserQuestion, mcp
---

# Commande Start

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../CONNECTORS.md).

Initialise le système todomail et sa mémoire de travail. La mémoire de travail constitue une mémoire tampon entre Claude et le RAG, accessible par les outils du MCP `~~todomail-mcp`.

Le système de mémoire créé est ensuite géré de façon organique par le skill `memory-management`.

## Instructions

### Étape 0. Configuration du serveur MCP

Cette étape détermine quel serveur MCP archiva sera utilisé par le plugin dans ce workspace. Elle est indispensable quand plusieurs serveurs archiva sont connectés dans Claude Desktop (ex: un serveur professionnel et un serveur personnel).

#### 0a. Vérifie la présence d'une configuration existante

Lire le fichier `.todomail-config.json` à la racine du répertoire de travail avec le tool `Read`.

- **Si le fichier existe et contient un champ `expected_rag_name` :** appeler le tool MCP `status` et comparer `status.rag_name` avec `expected_rag_name`. 
  - S'ils correspondent : passer à l'étape 1.
  - S'ils diffèrent : afficher un message clair indiquant le serveur attendu vs détecté, proposer à l'utilisateur soit de corriger la connexion MCP dans Claude Desktop, soit de relancer la configuration via la section 0b ci-dessous. Ne pas continuer tant que le mismatch n'est pas résolu.

- **Si le fichier n'existe pas :** passer à la section 0b pour le créer.

#### 0b. Configuration initiale du serveur MCP

1. Appeler `status` (MCP) pour récupérer le `rag_name` du serveur actuellement connecté.
2. Inspecter la liste des tools MCP disponibles dans la session : si plusieurs serveurs archiva sont exposés (plusieurs UUID différents pour le même type de tool), tenter d'appeler `status` sur chacun pour collecter tous les `rag_name` disponibles.
3. Présenter à l'utilisateur le(s) `rag_name` détecté(s) via `AskUserQuestion` :
   - Si un seul serveur est détecté : demander confirmation que c'est bien celui à utiliser pour ce workspace.
   - Si plusieurs serveurs sont détectés : proposer la liste et demander lequel utiliser.
4. Écrire le fichier `.todomail-config.json` à la racine du répertoire de travail avec le contenu suivant :

```json
{
  "schema_version": 1,
  "expected_rag_name": "<nom_choisi>",
  "configured_at": "<ISO8601 UTC>"
}
```

5. Confirmer à l'utilisateur : `Serveur MCP configuré pour ce workspace : <nom_choisi>`.

**Note importante :** le fichier `.todomail-config.json` est local au workspace et ne doit pas être commité. Il est automatiquement géré par le plugin.

### Étape 1. Vérifie l'existence des répertoires

Vérifie que le répertoire de travail contient les répertoires suivants :
- `inbox/`
- `todo/`
- `to-clean-by-user/`
- `todo/trash/`
- `todo/do-read-quick/`
- `todo/do-read-long/`
- `todo/do-decide/`
- `todo/do-consult-and-decide/`
- `todo/do-other/`
- `todo/do-self/`
- `mails/`
- `to-send/`
- `to-work/`
- `to-brief/`
- `docs/`

**Si un ou plusieurs répertoires n'existent pas:** Crée tous les répertoires manquants.

### Étape 1b. Vérifie la présence du dashboard

Vérifie que le fichier `dashboard.html` existe à la racine du répertoire de travail.

**Si `dashboard.html` n'existe pas ou si la version du plugin est plus récente :** Copie le fichier `${CLAUDE_PLUGIN_ROOT}/skills/dashboard.html` vers la racine du répertoire de travail.

### Étape 2. Vérifie l'existence de la mémoire

Vérifie que le répertoire de travail contient :
- `CLAUDE.md` et le répertoire `memory/` (avec ses sous-répertoires `people/`, `projects/`, `context/`)

**Si `CLAUDE.md` et le répertoire `memory/` n'existent pas:** C'est une installation initiale — réalise le bootstrap de la mémoire de travail (voir étape 4). Place `CLAUDE.md` et `memory/` (avec ses sous-répertoires `people/`, `projects/`, `context/`) dans le répertoire de travail.

### Étape 3. Oriente l'utilisateur

Si tout existait déjà :
```
Le système est opérationnel.
- /todomail:check-inbox pour télécharger les derniers mails et les classer
- /todomail:process-todo pour exécuter les instructions du dashboard
- /todomail:briefing pour préparer les réunions du jour
- /todomail:check-agenda pour auditer la cohérence de l'agenda
```
Si le bootstrap de la mémoire n'a pas été réalisé, continue à l'étape 4.

### Étape 4. Bootstrap mémoire (première exécution uniquement)

Ne fait ceci que si `CLAUDE.md` n'existe pas encore.

#### Point 1 — Informations de base

Demande à l'utilisateur :
```
Quel est ton nom ?
```

Demande à l'utilisateur :
```
Quels sont les noms de tes principaux collaborateurs ?
```

Une fois que tu as le nom de l'utilisateur et de ses principaux collaborateurs, passe au point suivant.

#### Point 2 — Exploitation des archives mails

En utilisant le tool MCP `search_mail`, analyse au total au maximum 100 mails dans lesquels l'utilisateur et au moins l'un des principaux collaborateurs sont expéditeur ou destinataire. Tu peux utiliser plusieurs agents en parallèle pour faire cette recherche (par exemple un agent pour chaque couple utilisateur / collaborateur principal). Une fois tous les mails examinés, déduis-en :
- la liste mise à jour des collaborateurs avec qui l'utilisateur travaille fréquemment, leur rôle (le rôle dans la structure peut souvent être déduit des signatures ou dernières lignes de leurs messages)
- leur adresse mail et leur prénom respectif ou nickname
- les principaux dossiers, sujets ou thématiques sur lesquels travaille chaque collaborateur
- les principaux acronymes ou abréviations utilisées
- les préférences et le style de rédaction de l'utilisateur

En utilisant le tool MCP `search_doc`, complète cette exploitation des mails avec une analyse des comptes rendus de CODIR pour trouver de nouveaux dossiers, sujet ou thématiques.

#### Point 2b — Exploration des calendriers

Si des agendas iCalendar sont configurés dans le connecteur MCP :

1. Appeler `list_calendars` (MCP) pour découvrir les agendas disponibles
2. Appeler `sync_calendars` (MCP) pour synchroniser les flux ICS
3. Appeler `fetch_calendar_events` (MCP) sur les 30 derniers jours pour identifier :
   - Les réunions récurrentes (mêmes titres, mêmes participants, fréquence régulière)
   - Les lieux fréquents avec estimation des temps de trajet
   - Les interlocuteurs fréquents en réunion (compléter les collaborateurs identifiés au point 2)
4. Créer le fichier `memory/context/reunions-recurrentes.md` avec les réunions récurrentes identifiées
5. Créer le fichier `memory/context/lieux.md` avec les lieux fréquents et les temps de trajet estimés
6. Créer le fichier `memory/context/preferences-agenda.md` avec les préférences agenda observées (horaires habituels, jours de télétravail, plages protégées, durée de pause déjeuner, etc.)

Si aucun agenda n'est configuré, passer cette étape (les fonctionnalités agenda seront disponibles quand des agendas seront ajoutés au connecteur MCP).

#### Point 3 — Exploitation de la base documentaire

Pour chaque dossier, sujet ou thématique identifié au point 2, en utilisant le tool MCP `search_all`, réalises-en une synthèse :
- Historique du dossier, sujet ou de la thématique
- Principales difficultés rencontrées
- Quelles ont été les solutions trouvées
- Principaux documents de référence sur le sujet ou la thématique

#### Point 4 — Écriture des fichiers mémoire

À partir de tout ce qui a été rassemblé, crée :

**CLAUDE.md** (mémoire courante, objectif max ~250 lignes) :
```markdown
# Mémoire todomail

## Utilisateur
[Nom], [Role]

## Collaborateurs
| Qui | Role | Email  |
|-----|------|------|
| [prénom],[nom] | [role] | [email]

## Termes
| Terme | Signification |
|------|---------|
| [acronyme] | [expansion] |

## Dossiers, Sujets et Thématiques
| Nom | Description |
|------|------|
| [nom] | [synthèse rapide] |

## Réunions récurrentes
| Nom | Fréquence | Participants clés | Notes |
|-----|-----------|-------------------|-------|
| [nom] | [hebdo/mensuel/...] | [noms] | [contexte] |

## Lieux fréquents
| Lieu | Trajet depuis bureau | Trajet depuis domicile | Notes |
|------|---------------------|----------------------|-------|
| [lieu] | [durée] | [durée] | [contexte] |

## Preferences
[Synthèse en quelques lignes des préférences et du style de rédaction de l'utilisateur]

### Préférences agenda
- Plages préférées pour les RDV externes : [plages]
- Jours de télétravail : [jours]
- Contraintes récurrentes : [contraintes]
```

**memory/** répertoire :
- `memory/people/{name}.md` — profils individuels des collaborateurs
- `memory/projects/{name}.md` — détails des sujets, dossiers ou thématiques tels qu'identifiés au point 3
- `memory/context/company.md` — équipes, outils, process, etc.

#### Point 5 — Informer des résultats

Informe des résultats du bootstrap et des statistiques : nombre de lignes de CLAUDE.md, nombre de personnes dans le répertoire `memory/people/`, nombre de sujets ou thématiques traités dans `memory/projects/`, nombre de réunions récurrentes identifiées, nombre de lieux fréquents enregistrés. Puis affiche le texte suivant :

```
Le système est opérationnel.
- /todomail:check-inbox pour télécharger les derniers mails et les classer
- /todomail:process-todo pour exécuter les instructions du dashboard
- /todomail:briefing pour préparer les réunions du jour
- /todomail:check-agenda pour auditer la cohérence de l'agenda
```

## Notes
- La mémoire croît de façon organique après le bootstrap au travers de l'utilisation des différents skills du plugin (voir le skill `memory-management`).
- Les fonctionnalités agenda (skills `agenda`, `disponibilites`, `detection-conflits` et commandes `/briefing`, `/check-agenda`) nécessitent que des agendas iCalendar soient configurés dans le connecteur MCP `~~todomail-mcp`. Si aucun agenda n'est configuré, ces fonctionnalités ne sont pas disponibles mais le reste du plugin fonctionne normalement.
- Le point 2b (exploration des calendriers) est optionnel et dépend de la disponibilité des outils calendrier dans le connecteur MCP.
