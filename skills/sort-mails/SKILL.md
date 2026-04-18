---
name: sort-mails
description: >
  This skill should be used when the user asks to "sort mails",
  "trier les mails", "trier mes messages" or needs
  to sort incoming emails into action categories.
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(python3:*), Bash(pip:*), Glob, Grep, Task, mcp
version: 2.0.0
---

# sort-mails — Tri des mails (Opus 1M, pré-filtrage Haiku, cache RAG)

Trie `inbox/` dans les 7 catégories de `todo/`. Exploite le contexte 1M d'Opus
pour analyser les mails en flux (pas d'agent par mail), avec pré-filtrage Haiku
sur les évidences et cache RAG pour éviter les appels MCP redondants.

## Accès aux helpers Python du plugin (à lire en premier)

Les modules `lib.state`, `lib.fs_utils`, `lib.rag_cache`, `lib.error_modes`,
`lib.config` mentionnés dans ce SKILL vivent dans **`${CLAUDE_PLUGIN_ROOT}/lib/`**,
PAS dans le répertoire du skill ni dans le workspace utilisateur. Ne pas chercher
`skills/sort-mails/lib/` — ce chemin n'existe pas.

Toute invocation Python qui importe `lib.*` DOIT d'abord ajouter
`${CLAUDE_PLUGIN_ROOT}` au `sys.path`. Pattern canonique pour chaque bloc Bash :

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 - <<'PY'
import sys, os
sys.path.insert(0, os.environ["CLAUDE_PLUGIN_ROOT"])
from lib.state import load_state, save_state, acquire_lock, release_lock, update_checkpoint, record_error, get_pending_errors
from lib.fs_utils import safe_mv, atomic_write_json, read_v2_json, write_v2_json, read_pending_emails, write_pending_emails
from lib.rag_cache import RagCache
# ... suite du traitement ...
PY
```

Si un `import lib.X` renvoie `ModuleNotFoundError`, ne **JAMAIS** conclure « pas de lib externe, analyse directe en flux » — c'est un bug d'import, pas une caractéristique du skill. Fixer le `sys.path` et retenter. Les helpers sont indispensables : sans `acquire_lock`/`save_state`, le dashboard n'est pas notifié du cycle et `state.json` reste incohérent.

## Vérification préalable des répertoires

Vérifier la présence de `inbox/`, `todo/`, `to-clean-by-user/` et des 7 sous-dossiers
de `todo/` (`trash`, `do-read-quick`, `do-read-long`, `do-decide`,
`do-consult-and-decide`, `do-other`, `do-self`). En cas d'absence :

> **ARRÊT OBLIGATOIRE — Répertoire inadéquat**
> Lister les répertoires manquants et demander à l'utilisateur de corriger.

La vérification du serveur MCP (alpha.2) est assurée par `/check-inbox` en amont.

## Étape 0 — Warm-up

1. `Read` de `CLAUDE.md` et de `memory/*` en mémoire de session.
2. Instancier `RagCache` depuis `lib.rag_cache`.
3. `load_state()` depuis `lib.state` ; si `errors[]` non vide, signaler la reprise
   possible via `--retry`.
4. `acquire_lock("sort-mails")`. Si déjà verrouillé :
   > **ARRÊT OBLIGATOIRE — Verrou actif**. Demander si attente ou déverrouillage.
5. Initialiser `ErrorHandler(mode="lenient")` (ou `"strict"` si flag).

## Étape 1 — Listage et pré-filtrage Haiku

Lister les sous-répertoires de `inbox/`. Si vide, passer à l'Étape 4.

Pour chaque sous-répertoire contenant déjà un `_analysis.json` (reprise après
interruption), réutiliser le fichier tel quel : passer directement à l'Étape 3.

**Court-circuit petits volumes** : si le nombre de mails restants `<= 5`, sauter
le pré-filtrage, tout passe à l'Étape 2.

### Construction du batch

Pour chaque mail restant, lire `message.json` et extraire uniquement : `id`,
`from`, `from_name`, `subject`, `date`, `size_bytes`, `has_attachments`,
`attachment_count`, et les 200 premiers caractères du `body_text` (`body_preview`).
**Ne pas charger le corps complet.**

### Appel de l'agent `mail-prefilter`

Lancer un **unique** `Task` avec `subagent_type: "mail-prefilter"` sur tout le
batch, avec pour prompt le JSON `{ "mails": [...] }` décrit dans
`agents/mail-prefilter.md`. Parser la sortie.

Pour chaque verdict :

- `trash` → `safe_mv(inbox/id, todo/trash/id)`, entrée minimale `{id, sender, date, summary: reason}`.
- `do-read-quick` → idem vers `todo/do-read-quick/`, entrée `{id, sender, date, synth: reason}`.
- `unsure` → rester dans `inbox/`, passer à l'Étape 2.

Utiliser `lib.fs_utils.safe_mv` + `is_already_in_destination` pour l'idempotence.

Checkpoint : `update_checkpoint("sort-mails:prefilter", "ok", {"trash": n, "quick": n, "unsure": n})`.

## Étape 2 — Analyse principale (Opus 1M)

Pour chaque mail restant dans `inbox/`, Claude lit **dans son contexte principal** :

1. `message.json` complet (métadonnées + corps).
2. Toutes les pièces jointes selon la table ci-dessous.

### Table de lecture des pièces jointes

| Format | Méthode |
|--------|---------|
| `.txt`, `.md`, `.html`, `.csv`, `.json`, `.ics` | `Read` natif |
| `.pdf` | `Read` natif (multimodal) |
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | `Read` natif (multimodal) |
| `.docx`, `.xlsx`, `.pptx`, `.rtf`, `.epub` | `python3 -m markitdown "<chemin>"` |
| `.odt`, `.ods`, `.odp` | `python3 "${CLAUDE_PLUGIN_ROOT}/skills/read-odf/scripts/read_odf.py" "<chemin>"` |
| Autres binaires | Ne pas lire. Noter « non lisible : [nom] ». |

Installer `markitdown` si absent : `pip install markitdown --break-system-packages`
(même pattern qu'`odfpy`).

> **ANTI-HALLUCINATION** : ne produire aucune synthèse sans avoir lu la source.

### Contextualisation RAG (cache obligatoire)

Avant chaque appel `search_mail` / `search_doc` / `search_all` :

```python
hit = rag_cache.get(tool_name, query, filter)
if hit is None:
    result = mcp_call(tool_name, ...)
    rag_cache.put(tool_name, query, filter, value=result)
else:
    result = hit
```

Appels types par mail : expéditeur (nom + email), sujet/dossier si identifiable.
Remplir le champ `rag-context`. Si rien de pertinent → `null` (pas de
rapprochement forcé).

### Détection agenda

Si le mail implique l'agenda (demande RDV, invitation, changement, annulation,
proposition créneau, rappel), appeler `get_availability` et `fetch_calendar_events`
(cache RAG idem) sur la période concernée. Produire :

```json
{
  "type": "demande-rdv|invitation|changement|annulation|proposition-creneau|rappel",
  "dates-proposees": ["2026-04-20T14:00:00"],
  "disponibilite": "disponible|conflit|possiblement libre",
  "conflit-detail": "...",
  "creneaux-alternatifs": ["2026-04-20 10:00 - 11:00"],
  "coherence": "cohérent|description des écarts"
}
```

Sinon : `agenda-detected: false`, `agenda-info: null`.

### Classification

| Catégorie | Critères |
|-----------|----------|
| `trash` | Spam, newsletter, notification système sans valeur |
| `do-read-quick` | Info simple sans PJ significative, aucune action |
| `do-read-long` | PJ à lire, pas d'arbitrage |
| `do-decide` | Décision tranchable seul |
| `do-consult-and-decide` | Décision nécessitant consultation (transversal) |
| `do-other` | Production demandée à un service |
| `do-self` | Production personnelle de l'utilisateur |

### Synthèses (tous les champs, quelle que soit la catégorie)

| Champ | Taille cible |
|-------|-------------|
| `summary` | 1-2 phrases |
| `synth` | ~100 mots |
| `detailed-synth` | ~500 mots (inclut chaque PJ) |
| `choose-points` | si applicable |
| `transmit` | si applicable |

### Écriture du `_analysis.json` (artefact de reprise)

Pour **chaque mail analysé**, écrire dans son répertoire via
`lib.fs_utils.atomic_write_json` :

```json
{
  "id": "...", "sender": "...", "sender_email": "...",
  "date": "17 Avr", "date_iso": "2026-04-17T09:15:00",
  "subject": "...", "category": "do-decide",
  "has_attachments": true,
  "attachments": [{"name": "...", "readable": true, "type": "pdf", "summary": "..."}],
  "summary": "...", "synth": "...", "detailed-synth": "...",
  "choose-points": "...", "transmit": null,
  "agenda-detected": false, "agenda-info": null,
  "rag-context": "..."
}
```

Ce fichier est réutilisé en cas d'interruption (cf. Étape 1).

### Batching adaptatif

Si `> 30` mails à analyser, traiter par **batches de 10 à 15** : analyser le batch,
écrire ses `_analysis.json`, `update_checkpoint("sort-mails:analyze-batch-N", "ok")`,
puis batch suivant. Permet la reprise granulaire.

### Gestion d'erreur

Chaque échec (lecture PJ, timeout MCP, parsing) passe par
`ErrorHandler.handle(exc, {"mail_id": id, "phase": "sort-mails:analyze"})` :

- `lenient` : erreur enregistrée dans `state.errors[]`, mail reste dans `inbox/`,
  on continue.
- `strict` : STOP immédiat, demande utilisateur.

## Étape 3 — Tri et écriture des `pending_emails.json` v2

Pour chaque mail ayant un `_analysis.json` :

1. Lire via `lib.fs_utils.atomic_read_json`, extraire `category`.
2. Si `is_already_in_destination(id, f"todo/{category}/")` → skip.
3. Sinon `safe_mv(f"inbox/{id}", f"todo/{category}/{id}")`.

### Construction des entrées par catégorie

Au-delà des champs communs `id`, `sender`, `date` :

| Catégorie | Champs additionnels (source) |
|-----------|------------------------------|
| `trash` | `summary` |
| `do-read-quick` | `synth` |
| `do-read-long` | `detailed-synth` |
| `do-decide` | `choose-points` |
| `do-consult-and-decide` | `choose-points`, `transmit` |
| `do-other` | `synth`, `transmit` |
| `do-self` | `synth` (depuis `detailed-synth`) |

Si `agenda-detected == true` → ajouter `agenda-info` à l'entrée.

### Écriture fusionnée (pas de purge inconditionnelle)

Pour chaque catégorie contenant de nouveaux mails :

```python
existing = read_pending_emails(category_dir)  # lit v1 et v2
merged = dedup_by_id(existing + new_entries)
write_pending_emails(category_dir, merged, session_id)
```

`lib.fs_utils.write_pending_emails` produit un objet v2 avec `_meta` wrapper.

Checkpoint : `update_checkpoint("sort-mails:write", "ok", {"categories": {...}})`.

## Étape 4 — Finalisation `state.json`

```python
update_checkpoint("sort-mails:done", "ok", {"stats": {...}})
release_lock()
rag_cache.clear()
```

## Étape 5 — Compte-rendu utilisateur

- **Pré-filtrage** : « N mails reçus, M pré-filtrés en trash, K en do-read-quick,
  L analysés en Opus ».
- **Cache RAG** : `rag_cache.stats()` → hits / miss.
- **Répartition** :

  | Catégorie | Mails |
  |-----------|-------|
  | trash / do-read-quick / do-read-long / do-decide / do-consult-and-decide / do-other / do-self | ... |

- **Erreurs** : si `state.errors[]` non vide, lister et suggérer :
  > Relancer `/todomail:check-inbox --retry` pour retraiter uniquement les mails
  > en échec.
