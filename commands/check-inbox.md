---
description: Télécharger et trier les mails de la boîte de réception
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(python3:*), Bash(pip:*), Glob, Grep, Task, mcp
argument-hint: "[--strict] [--retry]"
---

## Accès aux helpers Python du plugin (à lire en premier)

Les modules `lib.state`, `lib.fs_utils`, `lib.rag_cache` référencés ci-dessous vivent dans **`${CLAUDE_PLUGIN_ROOT}/lib/`**. Toute invocation Python DOIT d'abord ajouter ce chemin au `sys.path` :

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 - <<'PY'
import sys, os
sys.path.insert(0, os.environ["CLAUDE_PLUGIN_ROOT"])
from lib.state import load_state, save_state, acquire_lock, release_lock, get_pending_errors, clear_error
# ...
PY
```

Si `ModuleNotFoundError: lib`, ne **jamais** conclure « pas de lib externe » — fixer le `sys.path` et retenter. Les helpers sont indispensables : sans eux, le dashboard n'est pas notifié du cycle.

## Parsing des arguments

Les arguments passés à la commande sont disponibles dans la variable `$ARGUMENTS`.
Le parsing est effectué en lisant sémantiquement cette variable (pas de parseur
externe).

Flags supportés :
- `--strict` : active le mode strict (`ErrorHandler(mode="strict")`) — arrêt
  immédiat à la première erreur avec demande utilisateur.
- `--retry` : **saute le téléchargement IMAP**, lit `lib.state.get_pending_errors()`
  et retraite uniquement les mails inscrits dans `state.errors[]`. Le mode reste
  `lenient` quelle que soit la combinaison de flags.

Règle de priorité :
1. Si `$ARGUMENTS` contient `--retry` → mode retry (Étape 1 sautée, analyse ciblée
   sur les mails en échec, chaque retry réussi retire l'entrée via
   `lib.state.clear_error(mail_id)`).
2. Sinon si `$ARGUMENTS` contient `--strict` → `ErrorHandler(mode="strict")`,
   cycle complet.
3. Sinon → mode par défaut (`lenient`, cycle complet).

## Vérification préalable

### 1. Répertoires

Vérifier que le répertoire de travail contient `inbox/`. Absence → **ARRÊT
OBLIGATOIRE — Répertoire inadéquat** (message clair, attendre).

### 2. Serveur MCP (désambiguation alpha.2 — **ne jamais supprimer**)

Lire `.todomail-config.json` à la racine du répertoire de travail. Appeler le
tool MCP `status` et comparer `status.rag_name` avec `expected_rag_name` du
fichier de config.

- Si `.todomail-config.json` n'existe pas : demander à l'utilisateur de lancer
  `/todomail:start` pour configurer le workspace, puis arrêter.
- Si `status.rag_name != expected_rag_name` :

> **ARRÊT OBLIGATOIRE — Mauvais serveur MCP**
> Afficher : « Le serveur MCP connecté (`<status.rag_name>`) ne correspond pas
> au serveur attendu pour ce workspace (`<expected_rag_name>`). Vérifier les
> connexions MCP dans Claude Desktop ou relancer `/todomail:start` pour
> reconfigurer. »

Cette vérification est **obligatoire** et s'exécute **avant** toute autre étape.
Elle couvre tous les composants en aval (sort-mails, analyse, etc.), qui n'ont
donc pas à la refaire.

## Étape 1 — Téléchargement des mails (sautée si `--retry`)

Appeler le tool MCP `check_inbox` pour télécharger les mails depuis le serveur
IMAP. Chaque mail est placé dans un sous-répertoire de `inbox/` dont le nom est
l'horodate du mail. Le sous-répertoire contient :
- le mail au format EML
- un `message.json` (métadonnées + corps)
- chaque pièce jointe

**Important** : le tool s'exécute en tâche de fond. Attendre la fin avant de
passer à l'étape suivante.

## Étape 2 — Tri des mails (skill sort-mails)

Lire `@${CLAUDE_PLUGIN_ROOT}/skills/sort-mails/SKILL.md` et suivre ses étapes.

**Transmission des flags** : transmettre le mode d'erreur (`lenient` / `strict`)
au skill via l'`ErrorHandler` déjà instancié dans l'environnement de session.

**Mode `--retry`** : au lieu de lister `inbox/`, lister les `mail_id` retournés
par `lib.state.get_pending_errors()`. Pour chaque `mail_id`, localiser son
répertoire source (dans `inbox/` ou déjà dans `todo/<catégorie>/` selon où il
est resté) et relancer uniquement l'Étape 2 de sort-mails sur ce mail. À chaque
retry réussi : `lib.state.clear_error(mail_id)`. Les `pending_emails.json` sont
re-fusionnés en conséquence.

## Étape 3 — Compte-rendu

### Statistiques

- Nombre total de mails téléchargés (cycle complet) **ou** nombre de mails
  retraités (`--retry`).
- Stats pré-filtrage Haiku et cache RAG (héritées du skill sort-mails).
- Répartition par catégorie.

### Erreurs éventuelles

Lister les erreurs persistantes de `state.errors[]` avec, pour chacune :
`mail_id`, `phase`, `error_type`, `retry_count`, `permanent_failure`.

Si au moins une erreur est non résolue :

> Relancer `/todomail:check-inbox --retry` pour retraiter uniquement les mails
> en échec.

### Accès au dashboard

Indiquer à l'utilisateur qu'il peut ouvrir le dashboard interactif dans son
navigateur :

```
file://<chemin_absolu_du_répertoire_de_travail>/dashboard.html
```
