---
description: Générer des dossiers de préparation pour les réunions
allowed-tools: Read, Write, Bash(mkdir:*), Bash(ls:*), Bash(python3:*), Glob, Grep, Task, mcp
argument-hint: "[date|\"titre\"] [--parallel]"
---

# /briefing — Dossiers de préparation des réunions (Opus 1M)

Génère des dossiers de préparation pour les réunions, déposés dans le
répertoire `to-brief/` du répertoire de travail utilisateur. Exploite
le contexte 1M d'Opus 4.6 : un seul appel Claude charge la mémoire,
récupère les événements, lance les recherches documentaires contextuelles
(via `RagCache`) et produit tous les briefings en flux.

## Accès aux helpers Python du plugin (à lire en premier)

Les modules `lib.state`, `lib.rag_cache`, `lib.config` référencés
ci-dessous vivent à la racine du plugin, résolue via la variable
d'environnement `CLAUDE_PLUGIN_ROOT`. La variable est récupérée **côté
Python** (la substitution shell `${CLAUDE_PLUGIN_ROOT}` n'est pas
fiable dans tous les contextes d'exécution) :

```bash
python3 - <<'PY'
import sys, os
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    raise RuntimeError("CLAUDE_PLUGIN_ROOT non defini")
sys.path.insert(0, plugin_root)
from lib.state import load_state, save_state, acquire_lock, release_lock, update_checkpoint
from lib.rag_cache import RagCache
# ...
PY
```

Si `ModuleNotFoundError: lib`, ne **jamais** conclure « pas de lib
externe » — vérifier que `CLAUDE_PLUGIN_ROOT` est bien défini et
retenter. Les helpers sont indispensables : sans `acquire_lock`/
`save_state`, le dashboard ne voit pas le cycle.

## Syntaxe

- `/briefing` → réunions d'aujourd'hui
- `/briefing 2026-03-03` → réunions d'une date spécifique
- `/briefing "Titre réunion"` → une réunion spécifique (recherche par titre)
- `/briefing --parallel` → fan-out `Task` par réunion (utile si > 5 réunions,
  chaque Task reste en Opus par défaut, orthogonal aux autres arguments)

Arguments dans `$ARGUMENTS`, parsing sémantique.

## Vérification préalable

### 1. Mémoire et répertoires

Vérifier que le répertoire de travail contient :
- `CLAUDE.md` et le répertoire `memory/`
- Le répertoire `to-brief/` (le créer s'il n'existe pas)

Si `CLAUDE.md` n'existe pas :

> **ARRÊT OBLIGATOIRE — Mémoire non initialisée**
> Afficher : « La mémoire n'est pas initialisée. Exécutez d'abord
> `/todomail:start` pour initialiser le système. »
> **Ne pas poursuivre. Attendre.**

### 2. Serveur MCP (désambiguation alpha.2 — **ne jamais supprimer**)

Lire `.todomail-config.json` à la racine du répertoire de travail. Appeler
le tool MCP `status` et comparer `status.rag_name` avec `expected_rag_name`
du fichier de config.

- Si `.todomail-config.json` n'existe pas : demander à l'utilisateur de
  lancer `/todomail:start` pour configurer le workspace, puis arrêter.
- Si `status.rag_name != expected_rag_name` :

> **ARRÊT OBLIGATOIRE — Mauvais serveur MCP**
> Afficher : « Le serveur MCP connecté (`<status.rag_name>`) ne correspond
> pas au serveur attendu pour ce workspace (`<expected_rag_name>`).
> Vérifier les connexions MCP dans Claude Desktop ou relancer
> `/todomail:start` pour reconfigurer. »

Cette vérification est **obligatoire** et s'exécute **avant** toute autre
étape.

## Étape 0 — Warm-up (OBLIGATOIRE)

> **Aucun shortcut possible, même pour 1 seule réunion à briefer.** Sans
> `acquire_lock`, le dashboard n'affiche pas la bannière bleue pendant le
> cycle et `state.json.checkpoints` ne trace rien. L'utilisateur doit voir
> le cycle en temps réel dans son dashboard.

1. `Read` de `CLAUDE.md` et `memory/*` (utiliser en priorité le cache compilé
   par `hooks/session_start.py` dans `.todomail/memory_cache.json` quand il
   est disponible).
2. Bloc d'initialisation Python obligatoire :

```bash
python3 - <<'PY'
import sys, os
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    raise RuntimeError("CLAUDE_PLUGIN_ROOT non defini")
sys.path.insert(0, plugin_root)
from lib.state import load_state, acquire_lock, update_checkpoint
from lib.rag_cache import RagCache

state = load_state()
if not acquire_lock("briefing"):
    print(f"VERROU ACTIF : {state.get('active_lock')} — ARRET OBLIGATOIRE")
    sys.exit(2)
update_checkpoint("briefing:start", "ok")
print("LOCK ACQUIRED — cycle briefing demarre")
PY
```

3. Si sortie `VERROU ACTIF` → **ARRÊT OBLIGATOIRE**. Demander à l'utilisateur.
4. Instancier `RagCache` pour la durée du cycle ; tous les appels MCP
   `search_doc`, `search_mail`, `search_all`, `fetch_calendar_events`
   passent par ce cache (obligatoire).

## Étape 1 — Identification des réunions

Utiliser le skill `agenda` pour obtenir les réunions de la période
demandée.

Résolution de l'argument :
- **Pas d'argument** : date du jour
- **Date ISO (ex: 2026-03-03)** : cette date uniquement
- **Texte entre guillemets** : rechercher parmi les événements à venir
  (7 prochains jours) celui dont le titre contient le texte

Filtrer les événements pour ne garder que les réunions pertinentes pour
un briefing :
- Réunions de plus de 15 minutes
- Réunions avec au moins un participant identifié (hors utilisateur)
- Exclure les événements personnels/familiaux
- Exclure les simples rappels ou tâches

Si aucune réunion n'est trouvée :

> Afficher : « Aucune réunion identifiée pour [date/critère]. Vérifiez
> votre agenda ou précisez la période. »
> **Ne pas poursuivre** (passer directement à l'Étape 5 pour libérer le
> verrou).

Afficher la liste des réunions identifiées :
```
Réunions à briefer :
1. [heure] — [titre] ([lieu], [durée], [nb participants])
2. [heure] — [titre] ([lieu], [durée], [nb participants])
...

Génération des briefings en cours...
```

`update_checkpoint("briefing:reunions-listed", "ok", {"count": N})`.

## Étape 2 — Génération en flux (contexte principal 1M)

**Mode par défaut** : le contexte 1M d'Opus 4.6 tient tous les documents
pertinents d'une journée de réunions. Traiter en flux, une réunion à la
fois, dans le même contexte — plus de fan-out agent par réunion.

Pour chaque réunion identifiée, enchaîner dans un seul contexte :

### 2a. Documents de référence

Appeler `search_doc` (MCP, via `RagCache`) avec comme requête :
- Le titre de la réunion
- Les mots-clés extraits du titre et de la description
- Les noms des participants principaux

Retenir les 5-10 documents les plus pertinents. Pour chaque document
retenu, noter le titre, le chemin complet, et extraire les passages les
plus pertinents (2-3 paragraphes max).

### 2b. Échanges récents

Appeler `search_mail` (MCP, via `RagCache`) avec comme requête :
- Le titre de la réunion
- Les noms des participants

Retenir les 5-10 mails les plus récents et pertinents. Pour chaque mail
retenu, noter l'expéditeur, la date, l'objet, et résumer le contenu en
2-3 phrases.

### 2c. Connaissance contextuelle

Consulter le skill `memory-management` (lookup flow complet) pour :
- Identifier le contexte de la réunion (réunion récurrente ? sujet en
  cours ?)
- Récupérer l'historique des échanges avec les participants
- Identifier les décisions antérieures liées au sujet
- Retrouver les sujets récurrents et les points en suspens

### 2d. Vérification logistique

Utiliser le skill `detection-conflits` pour signaler d'éventuels
problèmes logistiques liés à la réunion :
- Conflit avec un autre événement
- Temps de déplacement insuffisant
- Surcharge de la journée

### 2e. Production du fichier markdown

Produire immédiatement le fichier markdown dans `to-brief/` (voir Étape 3
pour le format). Passer ensuite à la réunion suivante.

`update_checkpoint("briefing:reunion-done", "ok", {"slug": "..."})` après
chaque fichier produit.

### Mode `--parallel` (opt-in, > 5 réunions)

Si et seulement si `$ARGUMENTS` contient `--parallel` :

- Fan-out par `Task` : une Task par réunion, chacune faisant 2a/2b/2c/2d/2e
  en parallèle. Chaque Task hérite du modèle par défaut (Opus) — aucune
  personnalisation de modèle dans ce flag.
- Le `RagCache` n'est pas partagé entre Tasks (limitation Task isolée) :
  la redondance MCP peut donc réapparaître. C'est un compromis délibéré
  pour paralléliser au-delà de 5 réunions.
- La mise à jour mémoire (Étape 4) consolide à la fin les suggestions
  remontées par chaque Task.

**Ne jamais activer `--parallel` automatiquement.** C'est une option
explicite.

## Étape 3 — Format des fichiers briefing

### Convention de nommage

`YYYY-MM-DD_HHhMM_titre-reunion-slug.md`

Où `titre-reunion-slug` est le titre de la réunion en minuscules, sans
accents, avec des tirets à la place des espaces, tronqué à 50 caractères.

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

[Objet de la réunion et historique du sujet. Pourquoi cette réunion a
lieu, quel est le contexte actuel du dossier, rappel des étapes
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

[Sujets sensibles, décisions attendues, éléments à préparer, points de
vigilance identifiés dans les échanges précédents.]

- [Point 1]
- [Point 2]

## Questions ouvertes

[Issues identifiées dans les échanges précédents qui n'ont pas encore
de réponse, sujets en suspens, demandes sans retour.]

- [Question 1]
- [Question 2]

## Alertes logistiques

[Uniquement si des problèmes ont été détectés par le skill
detection-conflits : conflits, temps de trajet serré, etc. Omettre
cette section si aucun problème.]
```

**Règle de confidentialité** : Ne pas inclure d'informations issues des
agendas personnels ou familiaux dans les briefings. Si un conflit avec
un événement personnel est détecté, le signaler dans « Alertes
logistiques » comme « engagement personnel » sans détailler.

## Étape 4 — Mise à jour de la mémoire

Si de nouvelles connaissances ont été identifiées pendant la recherche
documentaire, utiliser le skill `memory-management` :

- **Nouveaux participants** identifiés dans les mails ou documents mais
  absents de la mémoire → créer `memory/people/{name}.md`
- **Nouveaux sujets ou dossiers** découverts en lien avec la réunion →
  créer `memory/projects/{name}.md`
- **Nouveaux lieux** de réunion rencontrés → mettre à jour
  `memory/context/lieux.md`
- Mettre à jour `CLAUDE.md` si les informations sont d'usage fréquent

**Note** : en mode `--parallel`, chaque Task collecte localement ses
suggestions mémoire ; l'étape 4 les consolide avant écriture pour
éviter les doublons.

## Étape 5 — Finalisation (OBLIGATOIRE)

> **`release_lock()` doit être appelé même en cas d'erreur** (utiliser un
> `try/finally` Python). Sans release, le prochain cycle est bloqué par
> le verrou orphelin et l'utilisateur voit une bannière bleue permanente
> dans son dashboard.

Bloc de finalisation Python obligatoire :

```bash
python3 - <<'PY'
import sys, os
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
sys.path.insert(0, plugin_root)
from lib.state import update_checkpoint, release_lock

update_checkpoint("briefing:done", "ok", {"files_generated": N})
release_lock()
print("LOCK RELEASED — cycle briefing termine")
PY
```

Afficher à l'utilisateur la liste des fichiers générés :

```
Briefings générés :
- to-brief/2026-03-03_14h30_copil-bouclier-securite-rn88.md
- to-brief/2026-03-03_16h00_point-bilateral-sg.md

[N] briefing(s) déposé(s) dans to-brief/.
```

Afficher aussi les stats du `RagCache` (`rag_cache.stats()` → hits/misses)
pour observabilité.

Si des réunions n'ont pas pu être briefées (manque d'information, erreur),
les lister avec l'explication.

## Notes

- Les briefings sont des fichiers autonomes, consultables indépendamment
  les uns des autres.
- Le répertoire `to-brief/` suit la même logique que `to-send/` et
  `to-work/` : Claude y dépose des fichiers que l'utilisateur consulte à
  son rythme.
- Les briefings ne modifient pas l'agenda (le plugin est en lecture seule
  sur les calendriers).
- Pour les réunions récurrentes identifiées dans la mémoire, le briefing
  intègre le contexte historique (décisions précédentes, actions en
  cours).
- **Dashboard notifié automatiquement** : chaque `save_state()` touche
  `.todomail/invalidate.txt`, déclenchant le refresh du polling 3s et
  l'affichage de la bannière bleue « Claude travaille… (lock: briefing) »
  pendant toute la durée du cycle.
