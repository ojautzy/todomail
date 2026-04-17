---
name: memory-management
description: >
  Système de mémoire à deux niveaux qui fait de Claude un assistant à valeur ajoutée.
  Il permet à Claude de comprendre l'environnement de travail et les requêtes comme
  le ferait un assistant humain. CLAUDE.md correspond à la mémoire de travail,
  le répertoire memory/ est une base de connaissance plus complète.
  L'ensemble de la base documentaire et des archives mails sont dans le RAG accessible par MCP.
  This skill should be used when the user asks "who is X", "qui est X",
  "rappelle-toi de X", "mémorise X", "que sait-on sur X", "que veut dire X",
  or needs to look up a person, acronym, project, or topic from organizational memory.
  Also use when the user wants to update preferences or record new knowledge about
  collaborators, topics, or processes.
version: 0.3.0
---

# Gestion de la mémoire

Ce système de mémoire fait de Claude un véritable assistant professionnel à valeur ajoutée, c'est-à-dire quelqu'un qui comprend les relations entre les différentes personnes, les sujets, dossiers ou thématiques qu'ils traitent ainsi que les préférences de l'utilisateur.

Ce skill n'a pas de commande dédiée. Il est utilisé comme référence par les autres skills du plugin et peut être invoqué en langage naturel par l'utilisateur (par ex. "rappelle-toi de Jean", "mémorise le dossier X", "qui est Y ?").

## Objectif

Transforme les prénoms de collaborateurs, acronymes, noms de projet, de dossier, de sujet ou de thématique, etc. en connaissance exploitable.

Par exemple :
```
Utilisateur: "demande à jean de préparer la prochaine FS"
              ↓ Claude décode
"Demander à Jean Martin (Secrétaire Général) de préparer les documents
et la réunion de la prochaine Formation Spécialisée en matière de
Santé Sécurité au Travail"
```

Sans mémoire, cette requête n'a pas de sens. Avec la mémoire, Claude sait que :
- **jean** → Jean Martin, Secrétaire Général, il traite les sujets RH et est en relation avec les représentants du personnel.
- **FS** → Formation Spécialisée en matière de Santé Sécurité au Travail

## Architecture

```
CLAUDE.md          ← Hot cache (~30 personnes, synthèses, et termes les plus courants)

memory/
  people/          ← synthèse des profils des collaborateurs
  projects/        ← synthèse des dossiers, sujets ou thématiques traitées
  context/         ← équipes, outils, process

serveur MCP `~~todomail-mcp`  ← le serveur documentaire et l'archive mails
                                 qui constitue la mémoire profonde et complète
```

**CLAUDE.md (Hot Cache) :**
- les ~30 personnes avec qui l'utilisateur interagit le plus souvent
- ~30 termes ou acronymes les plus courants
- Dossiers ou sujets actifs (5-15)
- Les préférences de l'utilisateur
- **Objectif : couvrir 80% des besoins quotidiens pour le traitement todomail**

**memory/people/, projects/, context/ :**
- synthèse détaillée des profils des collaborateurs
- synthèse des dossiers, sujets ou thématiques traitées
- informations sur la structure, les équipes, les outils et les process

**serveur MCP `~~todomail-mcp` :**
- serveur MCP qui présente la base documentaire complète et l'archive email
- à utiliser pour rechercher de la connaissance sur tout ce qui ne figure pas dans CLAUDE.md
- à utiliser pour rechercher des connaissances plus précises, plus détaillées ou plus approfondies que ce qui figure dans CLAUDE.md ou dans les répertoires memory/

## Lookup Flow

1. Chercher le terme, personne, sujet, dossier, thématique dans CLAUDE.md
2. S'il n'est pas trouvé, chercher dans memory/people/, projects/, context/
3. S'il n'est pas trouvé ou si besoin de plus de détail ou d'approfondissement, utiliser le MCP `~~todomail-mcp`

Cette approche hiérarchique permet de conserver CLAUDE.md d'une taille modeste (~250 lignes max) tout en supportant une mémoire complète par les répertoires memory/ et le serveur MCP `~~todomail-mcp`.

## Emplacements des fichiers

- **Mémoire courante :** `CLAUDE.md` dans le répertoire de travail
- **Mémoire spécifique :** sous-répertoires de `memory/`
- **Mémoire profonde et complète :** serveur MCP `~~todomail-mcp`

## Format de la mémoire courante (CLAUDE.md)

Utilise des tables pour la compacité. Objectif max ~250 lignes.

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
- Durée min pause déjeuner : [durée]
```

## Mémoire spécifique (memory/)

**memory/people/{name}.md :**
```markdown
# Jean Martin

**Aussi connu comme** jean, jeannot
**Role :** Secrétaire Général
**Rends compte à :** Directeur

## Communication
- **email 1 :** jean.martin@developpement-durable.gouv.fr
- **email 2 :** jean.martin@i-carre.net

## Contexte
- gère RH
- relation avec les organisations syndicales
```

**memory/projects/{name}.md :**
```markdown
# Dossier réorganisation

## Objectif
Réorganiser le siège

## Collaborateurs Clés
- Sarah Gestin
- Jean-Paul Rouve
- Gregory Carpentier

## Synthèse
modification des missions, simplifier les organisations, plus de robustesse

## Documents importants
lettre_lancement_directeur.pdf
réponse_chefs_de_service.docx
synthèse_questionnaire.xlsx
```

## Mémoire spécifique calendrier (memory/context/)

**memory/context/reunions-recurrentes.md :**
```markdown
# Réunions récurrentes

## COPIL mensuel
- **Fréquence :** 1er mardi du mois
- **Participants :** [liste]
- **Lieu :** [lieu]
- **Contexte :** [description]
- **Préparation recommandée :** oui

## Réunion d'équipe hebdomadaire
- **Fréquence :** chaque lundi à 9h
- **Participants :** [liste]
- **Lieu :** [lieu]
- **Contexte :** [description]
```

**memory/context/lieux.md :**
```markdown
# Lieux fréquents et temps de trajet

## Bureau principal
- **Adresse :** Clermont-Ferrand
- **Depuis domicile (Saulzet-le-Froid) :** ~30 min

## [Autre lieu]
- **Adresse :** [adresse]
- **Depuis bureau :** [durée]
- **Depuis domicile :** [durée]
- **Notes :** [stationnement, accès, etc.]
```

**memory/context/preferences-agenda.md :**
```markdown
# Préférences agenda

## Horaires
- Début de journée préféré : [heure]
- Fin de journée préférée : [heure]
- Pause déjeuner : [plage]

## Jours spéciaux
- Télétravail : [jours]
- Pas de RDV externe : [plages]

## Habitudes
- [Habitude 1]
- [Habitude 2]
```

## Interactions avec la mémoire

### Décodage de la requête

**Toujours** décoder les requêtes en premier avant d'agir :

```
1. CLAUDE.md (hot cache)     → À vérifier en premier
2. memory/people/, projects/ → Détails et synthèses lorsque c'est nécessaire
3. serveur MCP `~~todomail-mcp` → Si pas trouvé dans les étapes précédentes
                                   ou besoin d'approfondissement ou de complément
```

### Ajouter une mémoire relative à une personne

Lorsqu'une requête est similaire à "rappelle-toi de la personne {name}" ou "mémorise la personne {name}",
en utilisant le tool MCP `search_mail`, analyse les mails dans lesquels M. {name} ou Mme {name} sont expéditeurs ou destinataires. Déduis-en :
- leur rôle
- leur adresse mail et leur prénom respectif ou nickname
- les principaux dossiers, sujets ou thématiques sur lesquels il ou elle travaille
- les principaux acronymes ou abréviations utilisées

Crée ou mets à jour `memory/people/{name}.md`.
Ajoute à CLAUDE.md si les échanges avec la personne sont fréquents.

### Ajouter une mémoire relative à un sujet, dossier ou thématique

Lorsqu'une requête est similaire à "rappelle-toi de {name}" ou "mémorise {name}",
en utilisant le tool MCP `search_all`, réalises-en une synthèse :
- Historique du dossier, sujet ou de la thématique
- Principales difficultés rencontrées
- Quelles ont été les solutions trouvées
- Principaux documents de référence sur le sujet ou la thématique

Crée ou mets à jour `memory/projects/{name}.md`.
Ajoute à CLAUDE.md si le sujet, dossier ou la thématique sont en cours.

### Ajouter une mémoire relative à une préférence de l'utilisateur

Lorsqu'une requête est similaire à "l'utilisateur préfère XXX" ou "l'utilisateur a l'habitude de YYY" ou "l'utilisateur souhaite ZZZ",
complète ou amende la synthèse réalisée dans la section Preferences de CLAUDE.md.

### Ajouter une mémoire relative à une réunion récurrente

Lorsqu'une réunion est identifiée comme récurrente (mêmes participants, même titre, fréquence régulière), créer ou mettre à jour `memory/context/reunions-recurrentes.md` avec :
- Nom de la réunion
- Fréquence identifiée
- Participants habituels
- Lieu habituel
- Contexte et sujets typiquement abordés
- Préparation recommandée (oui/non)

Ajouter à CLAUDE.md (section "Réunions récurrentes") si la réunion est fréquente.

### Ajouter une mémoire relative à un lieu

Lorsqu'un nouveau lieu de réunion est rencontré (dans l'agenda ou dans un mail), créer ou mettre à jour `memory/context/lieux.md` avec :
- Adresse ou localisation
- Temps de trajet estimé depuis le bureau (Clermont-Ferrand)
- Temps de trajet estimé depuis le domicile (Saulzet-le-Froid)
- Notes pratiques (stationnement, accès, etc.)

Ajouter à CLAUDE.md (section "Lieux fréquents") si le lieu est fréquenté régulièrement.

### Ajouter une mémoire relative aux préférences agenda

Lorsqu'une préférence liée à l'agenda est identifiée (par observation ou par indication de l'utilisateur), créer ou mettre à jour `memory/context/preferences-agenda.md` et la section "Préférences agenda" de CLAUDE.md :
- Plages horaires préférées pour les RDV
- Jours de télétravail
- Contraintes récurrentes (pas de RDV le vendredi après-midi, etc.)
- Habitudes (courrier le matin, etc.)

### Rechercher dans la mémoire

Lorsque la requête est similaire à "Qui est X" ou "Qu'a-t-on à propos de YYY" ou "Que veut dire ZZZ" ou "Synthétiser AAA", effectue une recherche progressive selon le niveau de détail souhaité :
1. Cherche dans CLAUDE.md en premier
2. Puis cherche dans memory/ pour plus de précision
3. Puis utilise le tool MCP `search_all` si pas trouvé dans les étapes précédentes ou si besoin d'approfondissement ou de complément

## Intégration avec les autres composants

- **check-inbox** : lors du tri des mails, si un expéditeur inconnu apparaît fréquemment ou si un nouveau sujet émerge, il est recommandé de mettre à jour la mémoire via ce skill.
- **skill `sort-mails`** : utilise le RAG MCP (`search_mail`, `search_doc`, `search_all`) pour contextualiser l'expéditeur et le sujet de chaque mail, en exploitant les mêmes sources de mémoire (CLAUDE.md, memory/). Les appels RAG sont mémoïsés via `lib/rag_cache.py` pour éviter les redondances.
- **process-todo** : le traitement des actions complexes s'effectue directement dans le contexte principal (Opus 4.6 1M) de la commande. Le lookup flow (CLAUDE.md → memory/ → MCP via `lib/rag_cache.py`) est appliqué pour chaque mail et les suggestions de mise à jour mémoire sont consignées dans `_treatment.json`. La consolidation mémoire (écriture effective dans CLAUDE.md et memory/) est effectuée en fin de cycle, après collecte de tous les résultats, en appliquant les conventions de ce skill.
- **start** : le bootstrap initial de la mémoire est réalisé par la commande `/todomail:start`. Ce skill prend le relais pour la maintenance continue.
- **agenda** : utilise ce skill pour l'enrichissement contextuel des événements (identification des participants, des sujets récurrents). Met à jour la mémoire quand de nouvelles réunions récurrentes ou de nouveaux lieux sont identifiés.
- **disponibilites** : utilise ce skill pour accéder aux préférences de l'utilisateur (plages horaires, jours de télétravail, contraintes récurrentes).
- **detection-conflits** : utilise les informations de lieux pour estimer les temps de déplacement.
- **briefing** : utilise ce skill pour identifier les participants et leur rôle, ainsi que les sujets récurrents liés aux réunions.
- **check-agenda** : utilise ce skill pour l'analyse contextuelle approfondie des conflits (temps de trajet, habitudes, préférences).


## Bootstrapping

Utilise `/todomail:start` pour initialiser si CLAUDE.md n'existe pas.

## Conventions

- Utilise les termes en **gras** dans CLAUDE.md pour scanner plus facilement
- Essaye de conserver CLAUDE.md en dessous de ~250 lignes
- Noms de fichiers en minuscule sans accents avec des tirets. Exemple : `jean-martin.md`
- Lorsque quelque chose est utilisé fréquemment ou fait partie d'un dossier actif, place-le dans CLAUDE.md
- Lorsque le dossier est terminé ou que la personne n'est plus un contact fréquent ou que le terme est rarement utilisé, supprime-le de CLAUDE.md (l'information reste accessible dans `memory/` et dans le RAG)
- **Sections manquantes dans CLAUDE.md :** si une section référencée (par ex. "Réunions récurrentes", "Lieux fréquents", "Préférences agenda") n'existe pas dans le CLAUDE.md existant, la créer en respectant le format défini dans la section "Format de la mémoire courante" ci-dessus. Cela peut arriver après une mise à jour du plugin ajoutant de nouvelles sections au format de CLAUDE.md.
- **Fichiers mémoire manquants dans memory/context/ :** si un fichier référencé (par ex. `reunions-recurrentes.md`, `lieux.md`, `preferences-agenda.md`) n'existe pas, le créer en respectant le format défini dans la section "Mémoire spécifique calendrier" ci-dessus. Créer le répertoire `memory/context/` si nécessaire.
