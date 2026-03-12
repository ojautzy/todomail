---
description: Générer des dossiers de préparation pour les réunions
allowed-tools: Read, Write, Bash(mkdir:*), Bash(ls:*), Glob, Grep, Task, mcp
---

# Commande Briefing

Génère des dossiers de préparation pour les réunions, déposés dans
le répertoire `to-brief/` du répertoire de travail utilisateur.

## Syntaxe

- `/briefing` → réunions d'aujourd'hui
- `/briefing 2026-03-03` → réunions d'une date spécifique
- `/briefing "Titre réunion"` → une réunion spécifique (recherche par titre)

## Vérification préalable

Vérifier que le répertoire de travail contient :
- `CLAUDE.md` et le répertoire `memory/`
- Le répertoire `to-brief/` (le créer s'il n'existe pas)

Si `CLAUDE.md` n'existe pas :

> **ARRÊT OBLIGATOIRE — Mémoire non initialisée**
> Afficher : "La mémoire n'est pas initialisée. Exécutez d'abord
> `/todomail:start` pour initialiser le système."
> **Ne pas poursuivre. Attendre.**

## Étape 1 — Identification des réunions

Utiliser le skill `agenda` pour obtenir les réunions de la période
demandée.

Résolution de l'argument :
- **Pas d'argument** : date du jour
- **Date ISO (ex: 2026-03-03)** : cette date uniquement
- **Texte entre guillemets** : rechercher parmi les événements à venir
  (7 prochains jours) celui dont le titre contient le texte

Filtrer les événements pour ne garder que les réunions pertinentes
pour un briefing :
- Réunions de plus de 15 minutes
- Réunions avec au moins un participant identifié (hors utilisateur)
- Exclure les événements personnels/familiaux
- Exclure les simples rappels ou tâches

Si aucune réunion n'est trouvée :

> Afficher : "Aucune réunion identifiée pour [date/critère]. Vérifiez
> votre agenda ou précisez la période."
> **Ne pas poursuivre.**

Afficher la liste des réunions identifiées :
```
Réunions à briefer :
1. [heure] — [titre] ([lieu], [durée], [nb participants])
2. [heure] — [titre] ([lieu], [durée], [nb participants])
...

Génération des briefings en cours...
```

## Étape 2 — Recherche documentaire par réunion

Pour chaque réunion identifiée, orchestrer les recherches :

### 2a. Documents de référence

Appeler `search_doc` (MCP) avec comme requête :
- Le titre de la réunion
- Les mots-clés extraits du titre et de la description
- Les noms des participants principaux

Retenir les 5-10 documents les plus pertinents. Pour chaque document
retenu, noter le titre, le chemin complet, et extraire les passages
les plus pertinents (2-3 paragraphes max).

### 2b. Échanges récents

Appeler `search_mail` (MCP) avec comme requête :
- Le titre de la réunion
- Les noms des participants

Retenir les 5-10 mails les plus récents et pertinents. Pour chaque
mail retenu, noter l'expéditeur, la date, l'objet, et résumer le
contenu en 2-3 phrases.

### 2c. Connaissance contextuelle

Consulter le skill `memory-management` (lookup flow complet) pour :
- Identifier le contexte de la réunion (réunion récurrente ? sujet
  en cours ?)
- Récupérer l'historique des échanges avec les participants
- Identifier les décisions antérieures liées au sujet
- Retrouver les sujets récurrents et les points en suspens

### 2d. Vérification logistique

Utiliser le skill `detection-conflits` pour signaler d'éventuels
problèmes logistiques liés à la réunion :
- Conflit avec un autre événement
- Temps de déplacement insuffisant
- Surcharge de la journée

## Étape 3 — Génération des briefings

Pour chaque réunion, produire un fichier markdown dans `to-brief/`.

### Convention de nommage

`YYYY-MM-DD_HHhMM_titre-reunion-slug.md`

Où `titre-reunion-slug` est le titre de la réunion en minuscules,
sans accents, avec des tirets à la place des espaces, tronqué à
50 caractères.

Exemple : `2026-03-03_14h30_copil-bouclier-securite-rn88.md`

### Structure du fichier

```markdown
---
date: YYYY-MM-DD
heure: HH:MM
titre: [Titre complet de la réunion]
lieu: [Lieu]
duree: [Durée]
participants: [Liste des participants]
uid: [UID calendrier de l'événement, si disponible]
---

# Briefing : [Titre de la réunion]

**Date :** [Date et heure] | **Lieu :** [Lieu] | **Durée :** [Durée]

## Contexte

[Objet de la réunion et historique du sujet. Pourquoi cette réunion
a lieu, quel est le contexte actuel du dossier, rappel des étapes
précédentes si pertinent.]

## Documents de référence

[Pour chaque document pertinent trouvé dans le RAG :]

### [Titre du document]
- **Chemin :** `[chemin complet du fichier]`
- **Extrait pertinent :** [2-3 paragraphes clés du document]

## Derniers échanges

[Résumé des mails récents liés à cette réunion ou à ce sujet :]

- **[Date] — [Expéditeur] :** [Résumé en 2-3 phrases]
- **[Date] — [Expéditeur] :** [Résumé en 2-3 phrases]

## Participants

[Pour chaque participant identifié :]

| Participant | Rôle | Dernière interaction |
|-------------|------|---------------------|
| [Nom] | [Rôle/fonction] | [Date et objet du dernier échange] |

## Points d'attention

[Sujets sensibles, décisions attendues, éléments à préparer,
points de vigilance identifiés dans les échanges précédents.]

- [Point 1]
- [Point 2]

## Questions ouvertes

[Issues identifiées dans les échanges précédents qui n'ont pas
encore de réponse, sujets en suspens, demandes sans retour.]

- [Question 1]
- [Question 2]

## Alertes logistiques

[Uniquement si des problèmes ont été détectés par le skill
detection-conflits : conflits, temps de trajet serré, etc.
Omettre cette section si aucun problème.]
```

**Règle de confidentialité** : Ne pas inclure d'informations issues
des agendas personnels ou familiaux dans les briefings. Si un conflit
avec un événement personnel est détecté, le signaler dans "Alertes
logistiques" comme "engagement personnel" sans détailler.

## Étape 4 — Mise à jour de la mémoire

Si de nouvelles connaissances ont été identifiées pendant la
recherche documentaire, utiliser le skill `memory-management` :

- **Nouveaux participants** identifiés dans les mails ou documents
  mais absents de la mémoire → créer `memory/people/{name}.md`
- **Nouveaux sujets ou dossiers** découverts en lien avec la
  réunion → créer `memory/projects/{name}.md`
- **Nouveaux lieux** de réunion rencontrés → mettre à jour
  `memory/context/lieux.md`
- Mettre à jour `CLAUDE.md` si les informations sont d'usage
  fréquent

**Note :** Si plusieurs réunions sont briefées, les agents parallèles
de l'étape 2 peuvent chacun collecter des informations mémoire.
Consolider les mises à jour mémoire dans cette étape.

## Étape 5 — Présentation des résultats

Afficher à l'utilisateur la liste des fichiers générés :

```
Briefings générés :
- to-brief/2026-03-03_14h30_copil-bouclier-securite-rn88.md
- to-brief/2026-03-03_16h00_point-bilateral-sg.md

[N] briefing(s) déposé(s) dans to-brief/.
```

Si des réunions n'ont pas pu être briefées (manque d'information,
erreur), les lister avec l'explication.

## Notes

- Les briefings sont des fichiers autonomes, consultables
  indépendamment les uns des autres.
- Le répertoire `to-brief/` suit la même logique que `to-send/` et
  `to-work/` : Claude y dépose des fichiers que l'utilisateur
  consulte à son rythme.
- Les briefings ne modifient pas l'agenda (le plugin est en lecture
  seule sur les calendriers).
- Pour les réunions récurrentes identifiées dans la mémoire, le
  briefing intègre le contexte historique (décisions précédentes,
  actions en cours).
