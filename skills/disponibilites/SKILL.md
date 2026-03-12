---
name: disponibilites
description: >
  Connaissance des créneaux libres et disponibilités de l'utilisateur.
  Deuxième brique fondamentale, utilisée intensivement par le traitement
  des mails-agenda et par la commande /check-agenda.
  This skill should be used when the user asks "je suis libre quand",
  "mes disponibilités", "quand est-ce que je pourrais", "est-ce que
  j'ai le temps", "find me a slot", "when am I free", or when a mail
  requests a meeting and Claude needs to check availability, or when
  the command /check-agenda needs to propose alternative slots.
allowed-tools: Read, Write, Glob, Grep, mcp
version: 1.0.0
---

# Disponibilités — Connaissance des créneaux libres

Ce skill fournit à Claude la connaissance des disponibilités de
l'utilisateur. C'est la deuxième brique fondamentale, utilisée
intensivement par le traitement des mails liés à l'agenda et par
la commande `/check-agenda`.

## Déclenchement

Ce skill est déclenché :

- **Par l'utilisateur** : "je suis libre quand la semaine prochaine ?",
  "quand est-ce que je pourrais caser une réunion avec X ?", "est-ce
  que j'ai le temps de faire Y aujourd'hui ?"
- **Par l'agent `mail-analyzer`** : effectue directement les appels
  MCP `get_availability` pour vérifier les disponibilités quand un
  mail demande un rendez-vous ou propose un créneau (sans passer par
  ce skill)
- **Par la commande `/check-agenda`** : pour proposer des créneaux de
  repli en cas de conflit ou de réorganisation
- **De façon proactive** : quand un mail propose un créneau spécifique,
  Claude vérifie automatiquement si l'utilisateur est libre

## Comportement

### Étape 1 — Récupération des créneaux bruts et des événements

**1a.** Appeler `get_availability` (MCP) avec :
- `start_date` et `end_date` correspondant à la période demandée
- `calendar_ids` : tous les agendas (pour avoir une vue complète des
  occupations, y compris personnelles)
- `min_slot_minutes` : 30 par défaut, ajustable selon le contexte
  (par ex. 60 pour une réunion longue)
- `working_hours` : par défaut `{"start": "08:00", "end": "19:00",
  "days": [1, 2, 3, 4, 5]}`, ajustable selon les préférences connues
  de l'utilisateur

**1b.** Appeler `fetch_calendar_events` (MCP) avec les mêmes `start_date`
et `end_date` pour récupérer les événements réels de la période.
Ces événements sont nécessaires à l'étape 2 pour connaître les lieux
des événements adjacents à chaque créneau libre et appliquer les
buffers de déplacement.

### Étape 2 — Application des filtres contextuels

Enrichir les créneaux bruts avec des filtres issus de la connaissance
du plugin. Utiliser les événements récupérés à l'étape 1b pour
identifier l'événement précédant et suivant chaque créneau libre.

1. **Buffer de déplacement** : Si l'événement précédant ou suivant un
   créneau libre se déroule dans un lieu différent du bureau principal,
   réduire le créneau libre du temps de déplacement estimé. Consulter
   `CLAUDE.md` (section "Lieux fréquents") et `memory/context/lieux.md`
   pour résoudre les temps de trajet connus. Pour les lieux inconnus,
   appliquer les heuristiques génériques :
   - Même ville : retirer 15 min
   - Ville différente dans le département : retirer 30-60 min
   - Département différent : retirer 1-2h
   Si l'événement précédent est au domicile (ex : premier rendez-vous
   de la journée après télétravail), consulter `memory/context/lieux.md`
   pour le temps de trajet domicile-bureau.

2. **Exclusion des plages récurrentes connues** : Consulter `CLAUDE.md`
   (section Préférences) et `memory/context/` pour identifier les
   habitudes de l'utilisateur :
   - Jours de télétravail éventuels
   - Plages horaires réservées à des activités récurrentes non
     calendrier (ex : "le directeur fait son courrier entre 8h et 9h")
   - Créneaux préférés pour certains types de rendez-vous

3. **Prise en compte des événements provisoires** : Les événements
   marqués comme provisoires/tentative dans l'agenda libèrent des
   créneaux mais avec un statut spécial (voir étape 3).

4. **Préférences utilisateur** : Consulter la mémoire pour appliquer
   les préférences connues :
   - Pas de RDV externe le vendredi après-midi (si identifié)
   - Créneaux préférés pour les réunions internes vs externes
   - Durée minimale de pause déjeuner préférée
   - Toute autre préférence enregistrée dans CLAUDE.md ou memory/

### Étape 3 — Classification des créneaux

Retourner les créneaux avec un niveau de confiance :

- **"libre confirmé"** : Aucun événement sur aucun agenda pendant
  ce créneau. Le créneau est pleinement disponible.

- **"possiblement libre"** : Seuls des événements provisoires
  (statut tentative) occupent ce créneau. L'utilisateur pourrait
  être libre si ces événements ne se confirment pas.

- **"libre avec réserve"** : Le créneau est libre mais se situe
  juste après un déplacement (le buffer de trajet a été retiré)
  ou juste avant un déplacement. Le créneau est exploitable mais
  l'utilisateur doit être conscient de la contrainte logistique.

### Étape 4 — Présentation

Quand l'utilisateur demande explicitement ses disponibilités,
présenter directement dans la conversation :

- Liste des créneaux libres avec leur classification (confirmé,
  possiblement libre, avec réserve)
- Pour chaque créneau avec réserve : explication de la contrainte
- Durée totale de disponibilité sur la période
- Si une durée de réunion est précisée dans la demande, ne montrer
  que les créneaux suffisamment longs

## Retour structuré (pour usage par d'autres skills/commandes)

Quand ce skill est appelé par un autre composant, il retourne :

- Liste des créneaux avec :
  - `start` : date/heure de début
  - `end` : date/heure de fin
  - `duration_minutes` : durée en minutes
  - `confidence` : "libre confirmé" | "possiblement libre" |
    "libre avec réserve"
  - `note` : explication si "avec réserve" (ex : "après déplacement
    depuis Le Puy-en-Velay")
- Nombre total de créneaux
- Durée totale disponible sur la période

## Intégration avec les autres composants

- **skill `agenda`** : fournit le contexte des événements entourant
  les créneaux libres (lieux, participants) pour le calcul des
  buffers de déplacement
- **agent `mail-analyzer`** : effectue directement les appels MCP
  `get_availability` pour vérifier les disponibilités quand un mail
  propose un créneau de rendez-vous, sans passer par ce skill
- **commande `/check-agenda`** : utilise ce skill pour proposer
  des créneaux alternatifs en cas de conflit
- **skill `memory-management`** : fournit les préférences et
  habitudes de l'utilisateur pour les filtres contextuels
