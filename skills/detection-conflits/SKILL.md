---
name: detection-conflits
description: >
  Détection des conflits, superpositions et incohérences dans l'agenda.
  Brique d'analyse que Claude mobilise de façon proactive ou qui est
  orchestrée par d'autres composants.
  This skill should be used when the user asks "est-ce que j'ai un
  problème dans mon planning", "y a-t-il des conflits", "mon agenda
  est cohérent ?", or when the skill agenda builds the daily schedule
  and detects simultaneous events, or when a mail confirms a meeting
  and Claude needs to check for conflicts.
allowed-tools: Read, Glob, Grep, mcp
version: 2.0.0
---

# Détection de conflits — Incohérences agenda

Ce skill détecte les conflits, superpositions et incohérences dans
l'agenda de l'utilisateur. C'est une brique d'analyse que Claude
mobilise de façon proactive ou qui est orchestrée par d'autres
composants (skill `agenda`, commande `/check-agenda`).

## Cache RAG partagé (v2.0.0)

Ce skill ne fait pas d'appel MCP direct : il analyse une liste
d'événements déjà chargée par l'appelant. En revanche, le calcul des
temps de déplacement peut nécessiter un `search_mail` ou `search_doc`
sur un lieu inconnu — ces appels doivent passer par le `RagCache`
partagé de la session (`lib/rag_cache.py`) quand le skill est appelé
depuis une commande qui l'a instancié (`/check-agenda`, `/briefing`,
`sort-mails`).

## Déclenchement

Ce skill est déclenché :

- **Par l'utilisateur** : "est-ce que j'ai un problème dans mon
  planning ?", "y a-t-il des conflits dans mon agenda ?", "mon
  agenda est cohérent ?"
- **Par le skill `agenda`** : systématiquement, lors de la
  construction du programme d'une journée ou d'une période
- **Par le skill `sort-mails`** : effectue directement les
  vérifications de conflits via les appels MCP `fetch_calendar_events`
  quand un mail confirme une réunion (sans passer par ce skill)
- **Par la commande `/check-agenda`** : pour l'audit complet de
  l'agenda sur une période

## Entrée

Ce skill reçoit une liste d'événements (typiquement produite par
le skill `agenda` ou directement par `fetch_calendar_events` MCP).

Chaque événement doit contenir au minimum :
- Titre
- Date/heure de début et de fin
- Lieu (si disponible)
- Statut (confirmé, provisoire)
- Agenda source (pro, perso, famille)

## Contrôles effectués

### 1. Superpositions d'événements

Détecter les événements dont les plages horaires se chevauchent,
en distinguant :

- **Conflit certain** : deux événements confirmés se superposent,
  quel que soit l'agenda (pro vs pro, pro vs perso, etc.)
- **Conflit potentiel** : un événement confirmé se superpose à un
  événement provisoire, ou deux événements provisoires se superposent

Pour chaque superposition détectée, identifier :
- Les deux événements concernés (titre, horaire, agenda source)
- La durée du chevauchement
- Le type de conflit (certain / potentiel)

### 2. Temps de déplacement insuffisant

Quand deux événements consécutifs se déroulent dans des lieux
différents, vérifier que le temps entre la fin du premier et le
début du second est suffisant pour le déplacement :

Résolution des temps de déplacement :
1. Consulter `CLAUDE.md` (section "Lieux fréquents") et
   `memory/context/lieux.md` pour les temps de trajet connus entre
   les lieux fréquents (bureau principal, domicile, sites habituels).
2. Pour les lieux inconnus, appliquer les heuristiques génériques :
   - **Même bâtiment ou même ville** : 15 minutes suffisent
   - **Villes différentes dans le département** :
     prévoir 30 à 60 minutes selon la distance
   - **Départements différents ou villes éloignées** :
     prévoir 1 à 2 heures ou plus
3. Si un nouveau lieu est rencontré fréquemment, signaler dans la
   sortie pour que le composant appelant puisse mettre à jour la
   mémoire via le skill `memory-management`.

Si le temps disponible entre deux événements est inférieur au
temps de déplacement estimé, signaler comme conflit logistique.

### 3. Surcharge

Détecter les journées où l'utilisateur a plus de 6 heures de
réunions cumulées sans pause d'au moins 30 minutes consécutives.

Critères de surcharge :
- Plus de 6h de réunions dans la journée
- Plus de 3h de réunions consécutives sans pause de 30 min
- Journée commençant avant 8h ET se terminant après 19h

### 4. Incohérences détectables

Signaler les situations inhabituelles :
- Réunion planifiée un week-end ou un jour férié (sauf si
  explicitement attendu)
- Réunion très tôt (avant 7h) ou très tard (après 20h)
- Doublon apparent : deux événements avec le même titre ou des
  titres très similaires à la même heure

## Sortie

Retourner une liste structurée de conflits, chacun comportant :

- **type** : "superposition" | "deplacement" | "surcharge" |
  "incoherence"
- **severite** : "critique" | "attention" | "information"
  - **critique** : conflit certain, impossibilité logistique avérée
  - **attention** : conflit potentiel, timing serré mais pas
    impossible
  - **information** : surcharge, recommandation, situation
    inhabituelle
- **evenements** : liste des événements concernés (titre, horaire,
  lieu, agenda)
- **description** : description concise du problème en français
- **chevauchement_minutes** : (pour les superpositions) durée du
  chevauchement en minutes
- **temps_disponible_minutes** : (pour les déplacements) temps
  disponible entre les deux événements
- **temps_estime_minutes** : (pour les déplacements) temps de
  déplacement estimé

Ce skill ne propose PAS d'actions correctives — c'est le rôle
de la commande `/check-agenda` ou du composant appelant.
Il se contente de détecter et qualifier les problèmes.

## Présentation directe

Quand l'utilisateur demande directement s'il y a des problèmes
dans son agenda, présenter les résultats dans la conversation
avec les indicateurs visuels :

- 🔴 pour les conflits critiques
- 🟡 pour les points d'attention
- 🟢 pour les informations

## Intégration avec les autres composants

- **skill `agenda`** : appelle systématiquement ce skill lors de
  la construction du programme. Fournit la liste d'événements en
  entrée.
- **commande `/check-agenda`** : utilise ce skill pour l'audit
  complet, puis enrichit chaque conflit avec des propositions
  d'actions correctives et des créneaux alternatifs.
- **skill `sort-mails`** : effectue directement les vérifications
  de conflits via les appels MCP `fetch_calendar_events` quand un
  mail confirme ou modifie un événement calendrier, sans passer par
  ce skill.
