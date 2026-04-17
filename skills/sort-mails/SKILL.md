---
name: sort-mails
description: >
  This skill should be used when the user asks to "sort mails",
  "trier les mails", "trier mes messages" or needs
  to sort incoming emails into action categories.
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(python3:*), Bash(pip:*), Glob, Grep, Task, mcp
version: 2.0.0
---

# sort-mails — Tri des mails (Opus 1M, pre-filtrage Haiku, cache RAG)

Trie `inbox/` dans les 7 categories de `todo/`. Exploite le contexte 1M d'Opus
pour analyser les mails en flux (pas d'agent par mail), avec pre-filtrage Haiku
sur les evidences et cache RAG pour eviter les appels MCP redondants.

## Verification prealable des repertoires

Verifier la presence de `inbox/`, `todo/`, `to-clean-by-user/` et des 7 sous-dossiers
de `todo/` (`trash`, `do-read-quick`, `do-read-long`, `do-decide`,
`do-consult-and-decide`, `do-other`, `do-self`). En cas d'absence :

> **ARRET OBLIGATOIRE — Repertoire inadequat**
> Lister les repertoires manquants et demander a l'utilisateur de corriger.

La verification du serveur MCP (alpha.2) est assuree par `/check-inbox` en amont.

## Etape 0 — Warm-up

1. `Read` de `CLAUDE.md` et de `memory/*` en memoire de session.
2. Instancier `RagCache` depuis `lib.rag_cache`.
3. `load_state()` depuis `lib.state` ; si `errors[]` non vide, signaler la reprise
   possible via `--retry`.
4. `acquire_lock("sort-mails")`. Si deja locke :
   > **ARRET OBLIGATOIRE — Verrou actif**. Demander si attente ou deverrouillage.
5. Initialiser `ErrorHandler(mode="lenient")` (ou `"strict"` si flag).

## Etape 1 — Listage et pre-filtrage Haiku

Lister les sous-repertoires de `inbox/`. Si vide, passer a l'Etape 4.

Pour chaque sous-repertoire contenant deja un `_analysis.json` (reprise apres
interruption), reutiliser le fichier tel quel : passer directement a l'Etape 3.

**Court-circuit petits volumes** : si le nombre de mails restants `<= 5`, sauter
le pre-filtrage, tout passe a l'Etape 2.

### Construction du batch

Pour chaque mail restant, lire `message.json` et extraire uniquement : `id`,
`from`, `from_name`, `subject`, `date`, `size_bytes`, `has_attachments`,
`attachment_count`, et les 200 premiers caracteres du `body_text` (`body_preview`).
**Ne pas charger le corps complet.**

### Appel de l'agent `mail-prefilter`

Lancer un **unique** `Task` avec `subagent_type: "mail-prefilter"` sur tout le
batch, avec pour prompt le JSON `{ "mails": [...] }` decrit dans
`agents/mail-prefilter.md`. Parser la sortie.

Pour chaque verdict :

- `trash` → `safe_mv(inbox/id, todo/trash/id)`, entree minimale `{id, sender, date, summary: reason}`.
- `do-read-quick` → idem vers `todo/do-read-quick/`, entree `{id, sender, date, synth: reason}`.
- `unsure` → rester dans `inbox/`, passer a l'Etape 2.

Utiliser `lib.fs_utils.safe_mv` + `is_already_in_destination` pour l'idempotence.

Checkpoint : `update_checkpoint("sort-mails:prefilter", "ok", {"trash": n, "quick": n, "unsure": n})`.

## Etape 2 — Analyse principale (Opus 1M)

Pour chaque mail restant dans `inbox/`, Claude lit **dans son contexte principal** :

1. `message.json` complet (metadonnees + corps).
2. Toutes les pieces jointes selon la table ci-dessous.

### Table de lecture des pieces jointes

| Format | Methode |
|--------|---------|
| `.txt`, `.md`, `.html`, `.csv`, `.json`, `.ics` | `Read` natif |
| `.pdf` | `Read` natif (multimodal) |
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | `Read` natif (multimodal) |
| `.docx`, `.xlsx`, `.pptx`, `.rtf`, `.epub` | `python3 -m markitdown "<chemin>"` |
| `.odt`, `.ods`, `.odp` | `python3 "${CLAUDE_PLUGIN_ROOT}/skills/read-odf/scripts/read_odf.py" "<chemin>"` |
| Autres binaires | Ne pas lire. Noter « non lisible : [nom] ». |

Installer `markitdown` si absent : `pip install markitdown --break-system-packages`
(meme pattern qu'`odfpy`).

> **ANTI-HALLUCINATION** : ne produire aucune synthese sans avoir lu la source.

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

Appels types par mail : expediteur (nom + email), sujet/dossier si identifiable.
Remplir le champ `rag-context`. Si rien de pertinent → `null` (pas de
rapprochement force).

### Detection agenda

Si le mail implique l'agenda (demande RDV, invitation, changement, annulation,
proposition creneau, rappel), appeler `get_availability` et `fetch_calendar_events`
(cache RAG idem) sur la periode concernee. Produire :

```json
{
  "type": "demande-rdv|invitation|changement|annulation|proposition-creneau|rappel",
  "dates-proposees": ["2026-04-20T14:00:00"],
  "disponibilite": "disponible|conflit|possiblement libre",
  "conflit-detail": "...",
  "creneaux-alternatifs": ["2026-04-20 10:00 - 11:00"],
  "coherence": "coherent|description des ecarts"
}
```

Sinon : `agenda-detected: false`, `agenda-info: null`.

### Classification

| Categorie | Criteres |
|-----------|----------|
| `trash` | Spam, newsletter, notification systeme sans valeur |
| `do-read-quick` | Info simple sans PJ significative, aucune action |
| `do-read-long` | PJ a lire, pas d'arbitrage |
| `do-decide` | Decision tranchable seul |
| `do-consult-and-decide` | Decision necessitant consultation (transversal) |
| `do-other` | Production demandee a un service |
| `do-self` | Production personnelle de l'utilisateur |

### Syntheses (tous les champs, quelle que soit la categorie)

| Champ | Taille cible |
|-------|-------------|
| `summary` | 1-2 phrases |
| `synth` | ~100 mots |
| `detailed-synth` | ~500 mots (inclut chaque PJ) |
| `choose-points` | si applicable |
| `transmit` | si applicable |

### Ecriture du `_analysis.json` (artefact de reprise)

Pour **chaque mail analyse**, ecrire dans son repertoire via
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

Ce fichier est reutilise en cas d'interruption (cf. Etape 1).

### Batching adaptatif

Si `> 30` mails a analyser, traiter par **batches de 10 a 15** : analyser le batch,
ecrire ses `_analysis.json`, `update_checkpoint("sort-mails:analyze-batch-N", "ok")`,
puis batch suivant. Permet la reprise granulaire.

### Gestion d'erreur

Chaque echec (lecture PJ, timeout MCP, parsing) passe par
`ErrorHandler.handle(exc, {"mail_id": id, "phase": "sort-mails:analyze"})` :

- `lenient` : erreur enregistree dans `state.errors[]`, mail reste dans `inbox/`,
  on continue.
- `strict` : STOP immediat, demande utilisateur.

## Etape 3 — Tri et ecriture des `pending_emails.json` v2

Pour chaque mail ayant un `_analysis.json` :

1. Lire via `lib.fs_utils.atomic_read_json`, extraire `category`.
2. Si `is_already_in_destination(id, f"todo/{category}/")` → skip.
3. Sinon `safe_mv(f"inbox/{id}", f"todo/{category}/{id}")`.

### Construction des entrees par categorie

Au-dela des champs communs `id`, `sender`, `date` :

| Categorie | Champs additionnels (source) |
|-----------|------------------------------|
| `trash` | `summary` |
| `do-read-quick` | `synth` |
| `do-read-long` | `detailed-synth` |
| `do-decide` | `choose-points` |
| `do-consult-and-decide` | `choose-points`, `transmit` |
| `do-other` | `synth`, `transmit` |
| `do-self` | `synth` (depuis `detailed-synth`) |

Si `agenda-detected == true` → ajouter `agenda-info` a l'entree.

### Ecriture fusionnee (pas de purge inconditionnelle)

Pour chaque categorie contenant de nouveaux mails :

```python
existing = read_pending_emails(category_dir)  # lit v1 et v2
merged = dedup_by_id(existing + new_entries)
write_pending_emails(category_dir, merged, session_id)
```

`lib.fs_utils.write_pending_emails` produit un objet v2 avec `_meta` wrapper.

Checkpoint : `update_checkpoint("sort-mails:write", "ok", {"categories": {...}})`.

## Etape 4 — Finalisation `state.json`

```python
update_checkpoint("sort-mails:done", "ok", {"stats": {...}})
release_lock()
rag_cache.clear()
```

## Etape 5 — Compte-rendu utilisateur

- **Pre-filtrage** : « N mails recus, M pre-filtres en trash, K en do-read-quick,
  L analyses en Opus ».
- **Cache RAG** : `rag_cache.stats()` → hits / miss.
- **Repartition** :

  | Categorie | Mails |
  |-----------|-------|
  | trash / do-read-quick / do-read-long / do-decide / do-consult-and-decide / do-other / do-self | ... |

- **Erreurs** : si `state.errors[]` non vide, lister et suggerer :
  > Relancer `/todomail:check-inbox --retry` pour retraiter uniquement les mails
  > en echec.
