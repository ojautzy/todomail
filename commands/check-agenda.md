---
description: Auditer la cohérence et la faisabilité de l'agenda
allowed-tools: Read, Write, Bash(mkdir:*), Bash(ls:*), Glob, Grep, mcp
---

# Commande Check Agenda

Audite la cohérence et la faisabilité de l'agenda sur une période,
avec rapport structuré et propositions d'actions correctives.

## Syntaxe

- `/check-agenda` → semaine courante (lundi à vendredi)
- `/check-agenda mois` → mois courant
- `/check-agenda 2026-03-01 2026-03-31` → plage personnalisée

## Vérification préalable

Vérifier que le répertoire de travail contient :
- `CLAUDE.md` et le répertoire `memory/`

Si `CLAUDE.md` n'existe pas :

> **ARRÊT OBLIGATOIRE — Mémoire non initialisée**
> Afficher : "La mémoire n'est pas initialisée. Exécutez d'abord
> `/todomail:start` pour initialiser le système."
> **Ne pas poursuivre. Attendre.**

## Étape 1 — Chargement des événements

Résolution de la période :
- **Pas d'argument** : semaine courante (lundi au vendredi)
- **"mois"** : premier au dernier jour du mois courant
- **Deux dates ISO** : plage personnalisée

Utiliser le skill `agenda` pour charger tous les événements de la
période demandée, tous agendas confondus.

Afficher un résumé initial :
```
Audit de l'agenda du [date début] au [date fin]
[N] événements trouvés sur [N] agendas

Analyse en cours...
```

## Étape 2 — Détection des problèmes

Utiliser le skill `detection-conflits` pour identifier tous les
problèmes sur la période.

## Étape 3 — Analyse contextuelle approfondie

Pour chaque conflit détecté, enrichir avec une analyse contextuelle
utilisant le skill `memory-management` et les informations de
l'agenda :

### 3a. Estimation des temps de déplacement

Consulter `CLAUDE.md` (section "Lieux fréquents") et
`memory/context/lieux.md` pour résoudre les temps de trajet connus
entre les lieux fréquents (bureau principal, domicile, sites
habituels). Pour les lieux inconnus, appliquer les heuristiques
génériques :
- **Même bâtiment / même ville** : 15 min
- **Villes différentes dans le département** : 30 à 60 min
- **Départements différents ou villes éloignées** : 1 à 2h+

Si un nouveau lieu est rencontré, utiliser le skill
`memory-management` pour l'ajouter dans `memory/context/lieux.md`
et éventuellement dans CLAUDE.md (section "Lieux fréquents").

### 3b. Nécessité de nuitées

Signaler la recommandation d'une nuitée quand :
- Déplacement lointain (>2h) + réunion tôt le lendemain (avant 10h)
- Plusieurs jours consécutifs de réunions sur un même site distant
- Réunion se terminant tard (>18h) sur un site à plus de 1h30 du
  domicile ou du bureau

### 3c. Propositions de créneaux de repli

Pour chaque conflit ou problème de déplacement, utiliser le skill
`disponibilites` pour identifier des créneaux alternatifs :
- Chercher dans la même semaine en priorité
- Proposer 2-3 alternatives par conflit
- Indiquer le niveau de confiance de chaque créneau

## Étape 4 — Génération du rapport

Produire un rapport structuré dans la conversation, organisé par
jour puis par niveau de sévérité.

### Format du rapport

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUDIT AGENDA — [date début] au [date fin]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Résumé : [N] problèmes détectés
  🔴 [N] critiques | 🟡 [N] attention | 🟢 [N] informations
```

Pour chaque jour contenant des problèmes :

```
──── [Jour, date] ────

Programme du jour :
  [HH:MM - HH:MM] [Titre] @ [Lieu]
  [HH:MM - HH:MM] [Titre] @ [Lieu]
  ...
```

Pour chaque problème détecté (par sévérité décroissante) :

```
🔴 CRITIQUE — [Type de problème]
  Événements concernés :
    • [HH:MM - HH:MM] [Titre 1] @ [Lieu 1]
    • [HH:MM - HH:MM] [Titre 2] @ [Lieu 2]
  Problème : [Description précise]
  ▸ Proposition : [Action corrective suggérée]
    Créneaux alternatifs :
    - [Date HH:MM - HH:MM] (libre confirmé)
    - [Date HH:MM - HH:MM] (possiblement libre)

🟡 ATTENTION — [Type de problème]
  Événements concernés :
    • [HH:MM - HH:MM] [Titre] @ [Lieu]
  Problème : [Description]
  ▸ Proposition : [Action suggérée]

🟢 INFORMATION — [Type de problème]
  [Description et recommandation]
```

### Niveaux de sévérité

- 🔴 **Critique** : conflit certain entre deux événements confirmés,
  impossibilité logistique de déplacement (temps insuffisant entre
  deux lieux éloignés)
- 🟡 **Attention** : conflit potentiel (un confirmé + un provisoire),
  timing serré mais pas impossible, nécessité de nuitée probable
- 🟢 **Information** : surcharge (>6h de réunions), recommandation
  de nuitée, suggestion de visioconférence pour simplifier la
  logistique, long trajet détecté

### Types d'actions correctives

Selon la nature du problème, proposer :
- **Déplacer une réunion** : avec créneaux alternatifs (priorité aux
  réunions internes, plus faciles à déplacer)
- **Proposer une visioconférence** : quand un déplacement physique
  crée un problème logistique et que la visio est une option
  raisonnable
- **Recommander une nuitée** : quand le déplacement est inévitable
  et qu'une nuitée évite un trajet nocturne ou une contrainte
  horaire forte
- **Suggérer un réaménagement** : quand la surcharge peut être
  allégée en redistribuant des réunions sur d'autres créneaux
- **Annuler un doublon** : si deux événements semblent être le
  même rendez-vous

## Étape 5 — Mise à jour de la mémoire

Si de nouvelles connaissances ont été identifiées pendant l'audit,
utiliser le skill `memory-management` pour les enregistrer :

- **Nouveaux lieux** rencontrés dans l'agenda → créer ou mettre à
  jour `memory/context/lieux.md` avec les temps de trajet estimés
- **Nouvelles réunions récurrentes** détectées (mêmes participants,
  même titre, fréquence régulière) → créer ou mettre à jour
  `memory/context/reunions-recurrentes.md`
- **Préférences agenda** observées (plages systématiquement libres,
  habitudes de planification) → créer ou mettre à jour
  `memory/context/preferences-agenda.md`
- Mettre à jour `CLAUDE.md` si les informations découvertes sont
  d'usage fréquent

## Étape 6 — Synthèse finale

Terminer le rapport par une synthèse :

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SYNTHÈSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Période analysée : [date début] — [date fin]
Événements analysés : [N]
Problèmes détectés : [N] (🔴 [N] | 🟡 [N] | 🟢 [N])

Journées les plus chargées :
  [Date] : [N] réunions, [Xh] cumulées
  [Date] : [N] réunions, [Xh] cumulées

Déplacements identifiés : [N]
Nuitées recommandées : [N]

Actions prioritaires :
1. [Action la plus urgente]
2. [Deuxième action]
3. ...
```

## Notes

- Ce rapport est présenté directement dans la conversation, pas
  sous forme de fichier. L'utilisateur peut demander un export si
  nécessaire.
- Les propositions sont toujours soumises à l'utilisateur, jamais
  exécutées automatiquement (le plugin est en lecture seule sur
  les calendriers).
- Les événements personnels/familiaux sont pris en compte pour la
  détection de conflits mais affichés comme "engagement personnel"
  dans le rapport (confidentialité).
- Pour les lieux inconnus, l'estimation de temps de trajet se fait
  par heuristique. Le skill `memory-management` est mis à jour si
  un nouveau lieu est rencontré fréquemment.
