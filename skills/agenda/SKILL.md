---
name: agenda
description: >
  Connaissance du programme de l'utilisateur sur une période donnée.
  Brique fondamentale que Claude utilise chaque fois qu'il a besoin de
  savoir ce que fait l'utilisateur à un moment donné.
  This skill should be used when the user asks "c'est quoi mon planning",
  "qu'est-ce que j'ai aujourd'hui", "montre-moi ma journée", "ma semaine",
  "mon programme", "mes réunions", "what's on my calendar", or when
  any other skill or command needs to know the user's schedule.
  Also triggered when the user mentions a date ("la semaine prochaine",
  "lundi", "demain") in a context where knowing the agenda would help,
  or when a mail references a calendar event.
allowed-tools: Read, Write, Glob, Grep, AskUserQuestion, mcp
version: 1.0.0
---

# Agenda — Connaissance du programme

Ce skill fournit à Claude la connaissance du programme de l'utilisateur
sur une période donnée. C'est la brique fondamentale utilisée chaque
fois que Claude a besoin de savoir ce que fait l'utilisateur à un
moment donné.

## Déclenchement

Ce skill est déclenché :

- **Par l'utilisateur** : "c'est quoi mon planning ?", "montre-moi ma
  journée", "qu'est-ce que j'ai demain ?", "mes réunions de la semaine"
- **Par un autre composant** : l'agent `mail-analyzer` effectue
  directement les appels MCP calendrier pour les mails liés à
  l'agenda (sans passer par ce skill), le skill `disponibilites` pour
  contextualiser les créneaux
- **Par une commande** : `/briefing` pour lister les réunions à préparer,
  `/check-agenda` pour charger les événements d'une période
- **De façon proactive** : quand l'utilisateur mentionne une date ou
  pose une question qui bénéficierait du contexte agenda ("qu'est-ce que
  tu me conseilles de préparer ce soir ?", "est-ce que j'ai le temps
  de faire X aujourd'hui ?")

## Comportement

### Étape 1 — Synchronisation conditionnelle

Appeler `list_calendars` (MCP) pour obtenir la liste des agendas et
leur date de dernière synchronisation.

Si la dernière synchronisation d'au moins un agenda date de plus de
15 minutes : appeler `sync_calendars` (MCP) pour rafraîchir les flux
ICS. Attendre la fin de la synchronisation avant de poursuivre.

### Étape 2 — Récupération des événements

Déterminer la période pertinente en fonction du contexte :
- Si une période est explicitement demandée : utiliser cette période
- Si l'utilisateur dit "aujourd'hui" ou pose une question sur "maintenant" :
  date du jour
- Si l'utilisateur dit "demain", "lundi", "la semaine prochaine" :
  résoudre la date relative
- Par défaut (pas de précision) : date du jour

Appeler `fetch_calendar_events` (MCP) avec :
- `start_date` et `end_date` correspondant à la période déterminée
- `calendar_ids` : tous les agendas sauf indication contraire
- `include_cancelled` : false

### Étape 3 — Fusion et tri chronologique

Fusionner tous les événements de tous les agendas et les trier par
date/heure de début.

Pour chaque événement, extraire et structurer :
- **Titre** de l'événement
- **Date et heure** de début et de fin
- **Lieu** (si renseigné)
- **Participants** (si renseignés)
- **Statut** : confirmé, provisoire, annulé
- **Agenda source** : pro, perso, famille (catégorie de l'agenda)
- **Durée**

### Étape 4 — Enrichissement contextuel

Pour chaque événement, enrichir avec la mémoire du plugin :

1. **Identification des participants** : Consulter `CLAUDE.md` puis
   `memory/people/` pour identifier les participants (noms, rôles,
   historique des interactions). Si un participant n'est pas trouvé
   dans la mémoire locale, tenter une recherche MCP `search_mail`
   avec son nom ou son adresse mail.

2. **Identification du sujet récurrent** : Consulter `CLAUDE.md`
   puis `memory/projects/` pour déterminer si l'événement correspond
   à une réunion récurrente identifiée (COPIL mensuel, réunion
   d'équipe hebdomadaire, point bilatéral, etc.).

3. **Indication de préparation recommandée** : Signaler qu'une
   préparation est recommandée si l'un des critères suivants est
   rempli :
   - Réunion de plus de 30 minutes avec participants externes
     (hors service de l'utilisateur)
   - Sujet identifiable dans le RAG (MCP `search_doc` ou
     `search_all`) avec des documents récents ou des échanges
     récents
   - Réunion de type COPIL, comité de direction, réunion
     stratégique, ou tout événement dont le titre contient des
     mots-clés indiquant un enjeu (arbitrage, bilan, audit,
     inspection, etc.)

### Étape 5 — Détection des conflits

Utiliser le skill `detection-conflits` pour analyser la liste
d'événements et signaler les éventuels conflits, superpositions
ou incohérences.

Intégrer les résultats dans la présentation du programme.

### Étape 6 — Signalements complémentaires

1. **Déplacements importants** : Si deux événements consécutifs se
   déroulent dans des lieux différents, signaler le déplacement et
   estimer le temps nécessaire. Consulter `CLAUDE.md` (section
   "Lieux fréquents") et `memory/context/lieux.md` pour les temps
   de trajet connus. Pour les lieux inconnus, appliquer les
   heuristiques génériques :
   - Même bâtiment/ville : ~15 min
   - Villes différentes dans le département : 30-60 min
   - Départements différents : 1-2h+
   Si la résidence personnelle ou le bureau principal ne sont pas
   renseignés dans la mémoire, poser la question à l'utilisateur
   via `AskUserQuestion` et enrichir `CLAUDE.md` (section "Lieux
   fréquents") et `memory/context/lieux.md` avec les informations
   recueillies.

2. **Créneaux libres significatifs** : Identifier les plages sans
   événement de plus d'1 heure pendant les heures ouvrables (8h-19h,
   lundi-vendredi) et les mentionner comme créneaux exploitables.

3. **Mails récents liés** : Si des mails non traités récents
   (présents dans `todo/`) font référence à des réunions du
   programme affiché, les signaler brièvement (expéditeur, objet,
   catégorie actuelle).

### Étape 7 — Présentation

Quand l'utilisateur demande explicitement son programme, présenter
directement dans la conversation un résumé structuré et lisible :

- Programme chronologique avec pour chaque événement : heure, titre,
  lieu, durée, participants clés
- Conflits détectés (avec niveau de sévérité)
- Déplacements à prévoir
- Créneaux libres significatifs
- Réunions nécessitant une préparation
- Mails en attente liés aux réunions du jour

**Règle de confidentialité** : Les événements issus des agendas
personnels ou familiaux sont utilisés pour la détection de conflits
mais ne sont jamais détaillés dans la présentation. Indiquer
simplement "engagement personnel" avec l'horaire.

## Retour structuré (pour usage par d'autres skills/commandes)

Quand ce skill est appelé par un autre composant (skill ou commande),
il retourne les informations sous forme structurée :

- Liste chronologique des événements avec tous les champs de l'étape 3
- Enrichissements de l'étape 4 (participants identifiés, sujet
  récurrent, recommandation de préparation)
- Liste des conflits détectés (étape 5)
- Liste des déplacements importants (étape 6)
- Liste des créneaux libres significatifs (étape 6)
- Liste des mails en attente liés (étape 6)

## Intégration avec les autres composants

- **skill `disponibilites`** : utilise les données de ce skill pour
  contextualiser les créneaux libres
- **skill `detection-conflits`** : appelé par ce skill pour analyser
  les événements
- **agent `mail-analyzer`** : effectue directement les appels MCP
  calendrier (`fetch_calendar_events`, `get_availability`) pour les
  mails liés à l'agenda, sans passer par ce skill
- **commande `/briefing`** : utilise ce skill pour obtenir les
  réunions à préparer
- **commande `/check-agenda`** : utilise ce skill pour charger les
  événements d'une période
- **skill `memory-management`** : utilisé par ce skill pour
  l'enrichissement contextuel des événements
