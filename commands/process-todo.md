---
description: Exécuter les instructions du dashboard sur les mails triés
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(cp:*), Bash(python3:*), Bash(pip:*), Glob, Grep, AskUserQuestion, Task, mcp
argument-hint: "[--strict] [--retry] [--batch-validate]"
---

# /process-todo — Exécution des instructions du dashboard (Opus 1M)

Traite les `instructions.json` produits par le dashboard dans `todo/`. Exploite
le contexte 1M pour analyser et finaliser en flux, sans agent. **Séquentiel par
défaut** : un mail à la fois avec ARRÊT OBLIGATOIRE. `--batch-validate`
strictement opt-in.

> **RÈGLE D'EXÉCUTION :** à chaque ARRÊT OBLIGATOIRE, afficher la proposition,
> cesser toute exécution et attendre une réponse explicite.

## Parsing des arguments

Arguments dans `$ARGUMENTS`, parsing sémantique (pas de script externe).

- `--strict` : `ErrorHandler(mode="strict")` — arrêt à la première erreur avec
  demande utilisateur.
- `--retry` : saute Étapes 1 et 2, lit `lib.state.get_pending_errors()`,
  retraite chaque `mail_id` à la phase qui a échoué (`state.errors[].phase`),
  retire l'entrée via `clear_error(mail_id)` après succès. Mode reste `lenient`.
- `--batch-validate` : **opt-in uniquement, jamais automatique**. Présente toutes
  les propositions interactives en un seul rendu avec validation en lot (Étape
  3b bis).

Priorité : `--retry` > `--strict` (sinon `lenient`). `--batch-validate` est
orthogonal.

## Vérification préalable

### 1. Répertoires

Vérifier `todo/` et ses 7 sous-répertoires (`trash`, `do-read-quick`,
`do-read-long`, `do-decide`, `do-consult-and-decide`, `do-other`, `do-self`),
`to-clean-by-user/`, `mails/`, `to-send/`, `to-work/`, `docs/`. Absence →
**ARRÊT OBLIGATOIRE — Répertoire inadéquat** avec liste des manquants.

### 2. Serveur MCP (désambiguation alpha.2 — **ne jamais supprimer**)

Lire `.todomail-config.json` à la racine du répertoire de travail, appeler le
tool MCP `status`, comparer `status.rag_name` avec `expected_rag_name`.

- Si `.todomail-config.json` absent : demander à l'utilisateur de lancer
  `/todomail:start`, puis arrêter.
- Si mismatch :

> **ARRÊT OBLIGATOIRE — Mauvais serveur MCP**
> « Le serveur MCP connecté (`<status.rag_name>`) ne correspond pas au serveur
> attendu (`<expected_rag_name>`). Vérifier Claude Desktop ou relancer
> `/todomail:start`. »

## Étape 0 — Warm-up

1. `Read` de `CLAUDE.md` et `memory/*`.
2. Instancier `RagCache` (`lib.rag_cache`).
3. `load_state()` ; si `errors[]` non vide, signaler `--retry` possible.
4. `acquire_lock("process-todo")`. Verrouillé → **ARRÊT OBLIGATOIRE — Verrou actif**.
5. `ErrorHandler(mode="lenient"|"strict")` selon flag.
6. Si `--retry` : sauter Étapes 1-2 ; pour chaque `mail_id` dans
   `get_pending_errors()`, rejouer la phase échouée (cf. 3a/3b) puis Étape 6.

## Étape 1 — Collecte des instructions

Pour chaque sous-répertoire de `todo/`, lire `instructions.json` via
`lib.fs_utils.read_v2_json(path, "instructions")` — **accepte v1 (tableau brut
produit par le dashboard actuel) ET v2 (`{_meta, instructions}`)**.

**Fraîcheur** : si `_meta.consumes_session_id` est présent et ne correspond pas
au `session_id` du `pending_emails.json` de la même catégorie (ou à défaut
`state.session_id`), demander confirmation via `AskUserQuestion` avant de
poursuivre. Ne jamais traiter aveuglément un `instructions.json` périmé.

Si aucun `instructions.json` trouvé :

> **ARRÊT OBLIGATOIRE — Aucune instruction**
> « Aucun fichier instructions.json trouvé. Utilisez d'abord le dashboard. »

Afficher un résumé par catégorie (total + nombre d'actions `other`).

## Étape 2 — Actions simples (idempotentes)

Tout passe par `lib.fs_utils` (`safe_mv`/`safe_rm`/`atomic_write_json`), rejouable
sans effet de bord.

- **`keep`** : rien.
- **`delete`** : `safe_mv(todo/<src>/<id>, to-clean-by-user/<id>)`.
- **Déplacement inter-catégories** (action = nom de catégorie) :
  1. `safe_mv(todo/<src>/<id>, todo/<dst>/<id>)`.
  2. **Lire effectivement** `message.json` (anti-hallucination) et produire
     les champs descriptifs de `pending_emails.json` destination selon le schéma
     de `sort-mails`. Recopier `agenda-info` si présent dans l'entrée source.
  3. `write_pending_emails` destination (dédoublonnage par `id`).
  4. Si `dst == do-read-quick` → enchaîner archivage immédiat (voir ci-dessous).
  5. Sinon → ajouter `{id, destination, source}` dans `todo/_deferred.json`
     (créer `[]` si absent) pour Étape 3.
- **`other` dans `do-read-quick`** (archivage) : renommer `message.eml` →
  `<id>.eml`, extraire `AAAA/MM` des 10 premiers caractères de l'`id`,
  `mkdir_p(mails/AAAA/MM)`, `safe_mv` du `.eml` puis du répertoire vers
  `to-clean-by-user/`.

Après chaque action : retirer l'entrée par `id` du `pending_emails.json` source
via `write_pending_emails`.

`update_checkpoint("process-todo:simple-actions", "ok", {...})`.

## Étape 3 — Actions `other` complexes (contexte principal 1M)

File de traitement = instructions `action == "other"` + entrées de
`todo/_deferred.json` (mail dans `todo/<dst>/<id>/`, handler de `<dst>`).

Partition :
- **file_autonome** : `do-read-long`.
- **file_interactive** : `do-decide`, `do-consult-and-decide`, `do-other`,
  `do-self`.

Pour chaque mail interactif, lire `agenda-info` dans le `pending_emails.json`
de sa catégorie.

### Étape 3a — file_autonome (en flux)

Pour chaque mail `do-read-long` :

1. **Lecture** : `message.json` + PJ selon la **table canonique de
   `skills/sort-mails/SKILL.md`** (`Read` natif pour PDF/images/texte/HTML/CSV/
   JSON/ICS ; `python3 -m markitdown "<chemin>"` pour docx/xlsx/pptx/rtf/epub ;
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/read-odf/scripts/read_odf.py" "<chemin>"`
   pour ODF). PJ illisible → « non lisible : [nom] ». Ne pas réinventer.
2. **Contextualisation** : CLAUDE.md → `memory/` → MCP via `RagCache`. **Tous**
   les appels `search_mail`/`search_doc`/`search_all`/`get_availability`/
   `fetch_calendar_events` passent par le cache (obligatoire).
3. **Classification PJ** : algorithme de `skills/classify-attachment/SKILL.md`.
   Anomalie → consigner dans `state.errors[]` mais ne pas bloquer.
4. **Archivage** : renommer `message.eml` → `<id>.eml`, `mkdir_p(mails/AAAA/MM)`,
   `safe_mv`.
5. **Suggestions mémoire** : collecter en local (consolidées Étape 5). **NE PAS**
   écrire CLAUDE.md ni `memory/` ici.
6. **Écrire `_treatment.json`** (`mode: "autonomous"`, `status: "success"`,
   `analysis`, `finalization`, `memory_updates`) **AVANT** tout `safe_mv` final
   → artefact de reprise.
7. `safe_mv(todo/do-read-long/<id>, to-clean-by-user/<id>)`.
8. Retirer entrée du `pending_emails.json` source.
9. `update_checkpoint("process-todo:autonomous", ...)`.

Erreur → `ErrorHandler.handle(...)`. `lenient` continue, `strict` STOP.

### Étape 3b — file_interactive (séquentiel par défaut)

**Un mail à la fois, ARRÊT OBLIGATOIRE par mail** (cf. Q2 du REFACTOR_PLAN).
Ordre : `do-decide` → `do-consult-and-decide` → `do-other` → `do-self`.

Pour chaque mail :

**1. Phase analyze** (contexte principal 1M)
- Lecture mail + PJ (table canonique) + contextualisation RAG cachée.
- Exploiter `agenda-info` si présent (disponibilité/conflit/créneaux dans la
  proposition).
- Produire la proposition selon la catégorie :
  - **`do-decide`** → projet d'arbitrage markdown structuré : contexte du
    dossier, demande d'arbitrage, options **avec avantages et inconvénients**,
    **recommandation argumentée**, destinataire déduit de l'expéditeur original.
  - **`do-consult-and-decide`** → résumé du mail + identification du
    **consultant** (personne ou service **à consulter avant arbitrage**) via
    lookup mémoire.
  - **`do-other`** → résumé du mail + identification du **destinataire**
    (personne ou service **à qui déléguer le traitement**) via lookup mémoire.
  - **`do-self`** → plan d'action sous forme de `checklist.md` :
    ```markdown
    # Plan d'action {objet du mail}

    **Contexte:** {résumé de la demande}
    **Contact:** {expéditeur}

    ## A FAIRE
    - [ ]  {tâche 1} pour le {échéance 1}
    - [ ]  {tâche 2} pour le {échéance 2}
    ```
    + **liste des livrables proposés** (note / graphique / tableau Excel /
    présentation PowerPoint) avec description du contenu de chacun.
- Pré-calculer classification PJ (chemins `docs/AURA/*` ou `docs/MIN/*`).
- **Écrire `_treatment.json`** (`mode: "analyze"`, proposition complète,
  métadonnées de finalisation). Reprise post-mortem possible.

**2. ARRÊT OBLIGATOIRE — Validation utilisateur**

Bandeau :
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Validation mail {N}/{total} — {id}
Catégorie : {catégorie}[ (reclassé depuis {source})]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Présenter la proposition puis poser la question selon la catégorie :

| Catégorie | Question |
|-----------|----------|
| `do-decide` | « Projet d'arbitrage pour {id} ({sender}) — Validez-vous ? OUI pour valider, ou indiquez vos modifications. » |
| `do-consult-and-decide` | « Mail {id} ({sender}) — Consultation, j'ai identifié : {consultant}. OUI pour confirmer, ou indiquez le correct. » |
| `do-other` | « Mail {id} ({sender}) — Transmission avec suite à donner : {handler}. OUI pour confirmer, ou indiquez le correct. » |
| `do-self` | « Mail {id} ({sender}) — Plan d'action et livrables. Validez-vous ? OUI pour lancer, ou indiquez vos modifications. » |

> **NE PAS poursuivre avant réponse explicite. Cesser toute exécution. Attendre.**

**3. Phase finalize** (après validation)
- Mettre à jour `_treatment.json` (`mode: "finalize"`, décision utilisateur —
  contenu modifié ou « validé sans modification » —, destinataire confirmé/
  corrigé).
- Allouer numéro `to-send/` : lister `to-send/<destinataire>_*.md`, prendre
  `max(NN)+1` (format 2 chiffres).
- **Contenu du fichier `to-send/<destinataire>_<NN>.md` selon la catégorie** :
  - **`do-decide`** → projet d'arbitrage validé, destiné à la personne chargée
    de mettre en œuvre l'arbitrage.
  - **`do-consult-and-decide`** → mail de transmission **demandant les éléments
    d'analyse avant arbitrage**, adressé au consultant.
  - **`do-other`** → mail de transmission **pour suite à donner**, adressé au
    destinataire identifié.
  - **`do-self`** → projet de mail de réponse à l'expéditeur initial
    (**accusé de réception avec engagement d'échéance**).
- Tous les fichiers `to-send/*.md` portent un frontmatter YAML obligatoire :
  ```markdown
  ---
  to: prenom.nom@email.com
  cc: ... (si présent, sinon omettre)
  subject: ...
  date: AAAA-MM-JJ
  ref_mail_id: <id>
  ---

  <corps>
  ```
- `do-consult-and-decide` / `do-other` : préparer `consult_entry`
  (`| {id} | {date_du_jour} | {destinataire} | {résumé} |`) dans
  `_treatment.json.finalization.consult_entry` (consolidé Étape 5).
- `do-self` : créer `to-work/<nom-descriptif>/`, y sauvegarder le `checklist.md`
  validé, copier les documents à signer et documents à relire depuis le
  répertoire du mail. **Livrables** (note/excel/pptx/graphique) produits via
  les skills plateforme `docx`/`xlsx`/`pptx` ou `python3 + matplotlib` dans ce
  même répertoire, à partir des spécifications de `proposal.deliverables` et
  du contexte `analysis.summary` (pas besoin de relire le mail original).
- Archiver le mail (`<id>.eml` → `mails/AAAA/MM/`).
- Classer les PJ via `classify-attachment` (chemin **obligatoirement**
  `docs/AURA/*` ou `docs/MIN/*`).
- `safe_mv(todo/<cat>/<id>, to-clean-by-user/<id>)`.
- Retirer entrée du `pending_emails.json` source.
- `update_checkpoint("process-todo:interactive", "ok", {"mail_id": id, "validated": true})`.

**Ne consolide PAS les ARRÊTS.** Défaut = un mail à la fois.

### Étape 3b bis — Mode `--batch-validate` (opt-in)

Si et seulement si `$ARGUMENTS` contient `--batch-validate` :

1. Phase analyze en flux pour **tous** les mails interactifs (écriture
   `_treatment.json` au fur et à mesure).
2. Présenter toutes les propositions en **un seul rendu structuré** par
   catégorie, mails numérotés `[1]`, `[2]`, … globalement, format compact.
3. **UN SEUL ARRÊT OBLIGATOIRE** : « Validation en bloc. Répondez `OUI tous` /
   `NON tous` (aucun `to-send/` créé) / `OUI sauf 3,7,12`. Les mails refusés
   repasseront en mode séquentiel. »
4. Mails validés → phase finalize en flux (cf. 3b point 3). Mails refusés →
   repasser en 3b séquentiel pour ces seuls mails.

**Pas d'activation automatique ni de seuil.**

## Étape 4 — Vérification de cohérence

Pour chaque sous-répertoire de `todo/`, lire `pending_emails.json` via
`read_pending_emails` et retirer les entrées dont le répertoire `todo/<cat>/<id>/`
n'existe plus. Réécrire. Compter les orphelins pour le compte-rendu.

## Étape 5 — Consolidation `consult.md` + mémoire

### `consult.md`

Collecter les `finalization.consult_entry` non null (do-consult-and-decide +
do-other). Créer `consult.md` à la racine avec en-tête si absent :
```markdown
# Registre des consultations

| ID | Date | Destinataire | Résumé |
|----|------|-------------|--------|
```
Ajouter les lignes collectées. Écriture séquentielle.

### Mémoire

Collecter tous les `memory_updates` (autonome + interactive) et appliquer selon
les conventions de `@${CLAUDE_PLUGIN_ROOT}/skills/memory-management/SKILL.md` :
`new_people` → `memory/people/`, `new_projects` → `memory/projects/`,
`new_terms` → section Termes de CLAUDE.md, `preferences` → section Preferences.
Évaluer ajout à CLAUDE.md si contact fréquent ou projet actif.

## Étape 6 — Finalisation + compte-rendu

1. Écraser chaque `instructions.json` traité avec `write_instructions(..., [])`
   (format v2, `instructions` vide).
2. Écraser `todo/_deferred.json` avec `[]` si existant.
3. `update_checkpoint("process-todo:done", "ok", {"stats": ...})`.
4. `release_lock()`.
5. `rag_cache.clear()` + afficher `rag_cache.stats()` (hits/miss).
6. `touch` (`atomic_write_json`) `dashboard_invalidate.txt` à la racine (signal
   dashboard — sans effet avant Phase 5).

### Compte-rendu

| Action | Nombre |
|--------|--------|
| `keep` / `delete` / déplacés / archivés `do-read-quick` | ... |
| Traités autonomes (`do-read-long`) | ... |
| Traités interactifs (par catégorie) | ... |
| Reclassés et traités (`_deferred`) | ... |

Fichiers créés dans `to-send/` et `to-work/` : lister. Orphelins retirés : N.

**Erreurs** : si `state.errors[]` non vide, lister (`mail_id`, `phase`,
`error_type`, `retry_count`, `permanent_failure`) et suggérer :
> Relancer `/todomail:process-todo --retry` pour retraiter uniquement les mails
> en échec.

---

## Schéma `_treatment.json`

Contrat produit pour chaque mail (artefact de reprise, réécrit à chaque phase).

```json
{
  "id": "...", "category": "do-...", "mode": "autonomous|analyze|finalize",
  "status": "success|error", "error": null,
  "analysis": {
    "sender": "...", "sender_email": "...", "date": "...", "subject": "...",
    "summary": "...",
    "attachments": [{"name": "...", "readable": true, "summary": "...",
                     "classified_to": "docs/AURA/... | docs/MIN/... | null"}],
    "agenda_info_exploited": null, "rag_context": null
  },
  "proposal": {
    "type": "arbitrage|consultation|delegation|production",
    "draft": "... (do-decide)", "mail_summary": "... (do-consult|do-other)",
    "recipient": "...", "consultant": "...", "handler": "...",
    "checklist": "... (do-self)",
    "deliverables": [{"type": "note|excel|pptx|graphique", "description": "..."}]
  },
  "memory_updates": {"new_people": [], "new_projects": [], "new_terms": [], "preferences": []},
  "finalization": {
    "archived_to": "mails/AAAA/MM/<id>.eml",
    "attachments_classified": [{"from": "...", "to": "..."}],
    "to_send_files": [], "to_work_dir": null,
    "consult_entry": null
  }
}
```

## Règles anti-hallucination (critiques)

- **Lire effectivement** `message.json` et chaque PJ avant toute analyse ou
  synthèse. Aucune production dérivée du seul nom de fichier.
- PJ illisible → « non lisible : [nom] » dans `analysis.attachments`.
- Chemins de classement PJ **obligatoirement** `docs/AURA/*` ou `docs/MIN/*` —
  toute autre destination = anomalie (consignée, pas créée).
- Toute proposition (projet d'arbitrage, résumé, plan d'action, livrable)
  traçable à un fichier effectivement lu dans cette session.
- **`status: "success"` dans `_treatment.json` uniquement si les fichiers ont
  effectivement été déplacés/écrits** (modes `autonomous` et `finalize`). Sinon
  `status: "error"` avec `error` renseigné.

## Notes

- **Contexte 1M** : analyse + finalisation en flux, sans Task/agent. Idempotence
  de `lib/fs_utils.py` → chaque opération rejouable.
- **Pré-allocation `to-send/`** par `max(NN)+1` depuis `ls` (cohérence même sans
  parallélisme).
- **`_deferred.json`** : file d'attente entre Étape 2 et Étape 3 pour les
  reclassés, évite un aller-retour dashboard. Écrasé `[]` en Étape 6.
- **Dashboard non modifié** : `dashboard_invalidate.txt` touché en fin (refonte
  = Phase 5).
