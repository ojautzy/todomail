---
description: Auditer la cohérence et la faisabilité de l'agenda
allowed-tools: Read, Write, Bash(mkdir:*), Bash(ls:*), Bash(python3:*), Glob, Grep, mcp
argument-hint: "[mois | date-debut date-fin]"
---

# /check-agenda — Audit de cohérence agenda (Opus 1M)

Audite la cohérence et la faisabilité de l'agenda sur une période, avec
rapport structuré et propositions d'actions correctives. Exploite le
contexte 1M d'Opus 4.6 : un seul appel Claude charge tous les événements,
lance `detection-conflits`, fait les recherches contextuelles via
`RagCache`, et produit le rapport en flux.

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

- `/check-agenda` → semaine courante (lundi à vendredi)
- `/check-agenda mois` → mois courant
- `/check-agenda 2026-03-01 2026-03-31` → plage personnalisée

Arguments dans `$ARGUMENTS`, parsing sémantique.

## Vérification préalable

### 1. Mémoire

Vérifier que le répertoire de travail contient :
- `CLAUDE.md` et le répertoire `memory/`

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

> **Aucun shortcut possible, même pour une petite période.** Sans
> `acquire_lock`, le dashboard n'affiche pas la bannière bleue pendant le
> cycle et `state.json.checkpoints` ne trace rien.

1. `Read` de `CLAUDE.md` et `memory/*` (cache compilé disponible dans
   `.todomail/memory_cache.json` via `hooks/session_start.py`).
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
if not acquire_lock("check-agenda"):
    print(f"VERROU ACTIF : {state.get('active_lock')} — ARRET OBLIGATOIRE")
    sys.exit(2)
update_checkpoint("check-agenda:start", "ok")
print("LOCK ACQUIRED — cycle check-agenda demarre")
PY
```

3. Si sortie `VERROU ACTIF` → **ARRÊT OBLIGATOIRE**. Demander à l'utilisateur.
4. Instancier `RagCache` pour la durée du cycle ; tous les appels MCP
   (`fetch_calendar_events`, `get_availability`, `search_mail`,
   `search_doc`) passent par ce cache (obligatoire).

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

`update_checkpoint("check-agenda:events-loaded", "ok", {"count": N})`.

## Étape 2 — Détection des problèmes (contexte principal 1M)

Utiliser le skill `detection-conflits` pour identifier tous les
problèmes sur la période. Le contexte 1M permet de traiter l'ensemble
de la plage en un seul passage, sans batches.

## Étape 3 — Analyse contextuelle approfondie

Pour chaque conflit détecté, enrichir avec une analyse contextuelle
utilisant le skill `memory-management` et les informations de l'agenda.
Toutes les requêtes contextuelles (`search_mail`, `search_doc`,
`get_availability`) passent par le `RagCache` instancié à l'Étape 0.

### 3a. Estimation des temps de déplacement

Consulter `CLAUDE.md` (section « Lieux fréquents ») et
`memory/context/lieux.md` pour résoudre les temps de trajet connus entre
les lieux fréquents (bureau principal, domicile, sites habituels). Pour
les lieux inconnus, appliquer les heuristiques génériques :
- **Même bâtiment / même ville** : 15 min
- **Villes différentes dans le département** : 30 à 60 min
- **Départements différents ou villes éloignées** : 1 à 2h+

Si un nouveau lieu est rencontré, utiliser le skill `memory-management`
pour l'ajouter dans `memory/context/lieux.md` et éventuellement dans
CLAUDE.md (section « Lieux fréquents »).

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

Produire un rapport structuré dans la conversation, organisé par jour
puis par niveau de sévérité.

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
  impossibilité logistique de déplacement (temps insuffisant entre deux
  lieux éloignés)
- 🟡 **Attention** : conflit potentiel (un confirmé + un provisoire),
  timing serré mais pas impossible, nécessité de nuitée probable
- 🟢 **Information** : surcharge (>6h de réunions), recommandation de
  nuitée, suggestion de visioconférence pour simplifier la logistique,
  long trajet détecté

### Types d'actions correctives

Selon la nature du problème, proposer :
- **Déplacer une réunion** : avec créneaux alternatifs (priorité aux
  réunions internes, plus faciles à déplacer)
- **Proposer une visioconférence** : quand un déplacement physique crée
  un problème logistique et que la visio est une option raisonnable
- **Recommander une nuitée** : quand le déplacement est inévitable et
  qu'une nuitée évite un trajet nocturne ou une contrainte horaire forte
- **Suggérer un réaménagement** : quand la surcharge peut être allégée
  en redistribuant des réunions sur d'autres créneaux
- **Annuler un doublon** : si deux événements semblent être le même
  rendez-vous

## Étape 5 — Mise à jour de la mémoire

Si de nouvelles connaissances ont été identifiées pendant l'audit,
utiliser le skill `memory-management` pour les enregistrer :

- **Nouveaux lieux** rencontrés dans l'agenda → créer ou mettre à jour
  `memory/context/lieux.md` avec les temps de trajet estimés
- **Nouvelles réunions récurrentes** détectées (mêmes participants, même
  titre, fréquence régulière) → créer ou mettre à jour
  `memory/context/reunions-recurrentes.md`
- **Préférences agenda** observées (plages systématiquement libres,
  habitudes de planification) → créer ou mettre à jour
  `memory/context/preferences-agenda.md`
- Mettre à jour `CLAUDE.md` si les informations découvertes sont
  d'usage fréquent

## Étape 6 — Synthèse finale + finalisation

> **`release_lock()` doit être appelé même en cas d'erreur** (utiliser un
> `try/finally` Python). Sans release, le prochain cycle est bloqué par
> le verrou orphelin et l'utilisateur voit une bannière bleue permanente
> dans son dashboard.

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

Bloc de finalisation Python obligatoire :

```bash
python3 - <<'PY'
import sys, os
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
sys.path.insert(0, plugin_root)
from lib.state import update_checkpoint, release_lock

update_checkpoint("check-agenda:done", "ok", {"events": N, "issues": M})
release_lock()
print("LOCK RELEASED — cycle check-agenda termine")
PY
```

Afficher aussi les stats du `RagCache` (`rag_cache.stats()` → hits/misses)
pour observabilité.

## Notes

- Ce rapport est présenté directement dans la conversation, pas sous
  forme de fichier. L'utilisateur peut demander un export si nécessaire.
- Les propositions sont toujours soumises à l'utilisateur, jamais
  exécutées automatiquement (le plugin est en lecture seule sur les
  calendriers).
- Les événements personnels/familiaux sont pris en compte pour la
  détection de conflits mais affichés comme « engagement personnel »
  dans le rapport (confidentialité).
- Pour les lieux inconnus, l'estimation de temps de trajet se fait par
  heuristique. Le skill `memory-management` est mis à jour si un nouveau
  lieu est rencontré fréquemment.
- **Dashboard notifié automatiquement** : chaque `save_state()` touche
  `.todomail/invalidate.txt`, déclenchant le refresh du polling 3s et
  l'affichage de la bannière bleue « Claude travaille… (lock:
  check-agenda) » pendant toute la durée du cycle.
