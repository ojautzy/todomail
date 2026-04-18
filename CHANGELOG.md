# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

---

## [2.0.0-alpha.8] - 2026-04-18

### Ajouté

- **Dashboard v3** — Polling 3s sur `dashboard_invalidate.txt` et `.todomail-state.json` pour détecter les modifications de Claude. Le dashboard rafraîchit automatiquement les compteurs et la catégorie active sans action utilisateur.
- Helper `extractEmailsAndMeta(data)` dans `skills/dashboard.html` : extension du hotfix alpha.3 (`extractEmails` conservé en lecture v1/v2) qui retourne aussi le bloc `_meta`. Idem `extractInstructionsAndMeta(data)` pour les `instructions.json`.
- **Banner de fraîcheur** affiché en vue Catégorisation si le `_meta.session_id` du `pending_emails.json` ne correspond plus à la session courante du workspace (lue depuis `.todomail-state.json`).
- **Verrou visuel** pendant qu'un cycle Claude tourne : bannière bleue « Claude travaille… (lock: X) », dropdowns de décision et boutons bulk grisés.
- **Panneau d'erreurs** déployable depuis la zone principale : liste des entrées de `state.errors[]` avec phase, type, compteur de tentatives et message. Bouton « Retry tous » et « Ignorer » par erreur.
- **Fichiers-marqueurs `retry_request.txt` et `errors_dismiss.txt`** à la racine du workspace : le dashboard exprime une intention utilisateur, `hooks/session_start.py` les consomme au démarrage de la prochaine commande du plugin (marque `retry_requested: true` ou retire l'erreur). Pattern symétrique à `dashboard_invalidate.txt`.
- **Reconnexion automatique** du `DirectoryHandle` via IndexedDB : après la première autorisation, le dashboard rebranche silencieusement le workspace au rechargement (si la permission Chromium a survécu). Si la permission a expiré, un bouton « Reprendre la connexion » permet de ré-autoriser sans rouvrir le picker. Nouveau bouton « Oublier ce projet » pour invalider le handle persisté.
- **Écran d'avertissement plein page** si le navigateur ne supporte pas l'API File System Access (Safari, Orion, Firefox) avec la liste explicite des moteurs compatibles.
- **Vue Mémoire activée** (`memory` passe de `enabled: false` à `enabled: true`) : sidebar avec 4 sections — CLAUDE.md (racine), Personnes (`memory/people/`), Sujets (`memory/projects/`), Contexte (`memory/context/`). Chaque fichier est éditable via une modale textarea et supprimable (sauf CLAUDE.md) avec confirmation inline.
- **Mirror `.todomail-state.json`** : `lib/state.py.save_state()` écrit désormais une copie du state canonique à la racine du workspace (`$CLAUDE_PROJECT_DIR`) pour que le dashboard HTML y accède via File System Access. No-op silencieux si la variable d'environnement n'est pas définie.
- `.gitignore` : ajout de `.todomail-state.json`, `dashboard_invalidate.txt`, `retry_request.txt`, `errors_dismiss.txt` (artefacts runtime du workspace).

### Modifié

- **Suppression de l'auto-écriture systématique de `instructions.json`** au chargement d'une catégorie (ligne 239 alpha.7). Les fichiers d'instructions ne sont plus réécrits que sur action utilisateur réelle (`updateDecision` ou `bulkAction`), ce qui évite l'écrasement d'instructions fraîches en cours de `process-todo`.
- `<title>` de `skills/dashboard.html` : retrait de la mention résiduelle « Cowork » (coquille héritée de la v1.x).
- `README.dashboard.md` : nouvelle section consacrée au mécanisme de polling, au banner de fraîcheur, au verrou, au panneau d'erreurs et à la vue Mémoire.

### Corrigé

- Plus de désynchronisation silencieuse entre le dashboard et Claude : un cycle `/todomail:check-inbox` ou `/todomail:process-todo` est détecté dans les 3s côté dashboard.
- Plus d'écrasement d'`instructions.json` valides lors d'un simple changement d'onglet côté utilisateur.

### Correctifs post-test (bugfix avant merge)

- `lib/state.py.save_state()` touche désormais `dashboard_invalidate.txt` à chaque écriture d'état — `sort-mails` et `process-todo` déplaçant les fichiers via Python (`lib.fs_utils.safe_mv`), le hook `PostToolUse Bash(mv|rm)` ne peut pas être le signal exclusif. Chaque `acquire_lock`/`release_lock`/`update_checkpoint` publie maintenant un top externe visible par le polling 3s. Signal fiable indépendant du canal Bash.
- Banner de fraîcheur durci : on n'affiche « Données obsolètes » que si `pendingMeta.generated_at < workspaceState.started_at` (fichier écrit strictement avant le début de la session active). Évite les faux positifs quand un skill génère son propre `session_id` dans le `_meta` au lieu de réutiliser celui du `state.json`.
- Bouton « Recharger » désormais actif : force un `refreshAll` complet (pending_emails + compteurs + workspace state + invalidate stamp) et masque le banner jusqu'à un changement de catégorie.

---

## [2.0.0-alpha.7] - 2026-04-18

### Supprimé

- `hooks/_run.sh` (wrapper shell ajouté en alpha.6). Le diagnostic initial « PATH minimal sur macOS GUI » s'est révélé erroné : la ligne `.hooks_fired.log` produite en alpha.6 montre que le `PATH` hérité par les hooks contient déjà `/opt/homebrew/bin` (et autres chemins utilisateur). Le wrapper prefixait donc un PATH déjà correct — geste défensif mais inutile.

### Modifié

- `hooks/hooks.json` : retour à l'invocation directe `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<hook>.py"`, alignée avec la façon dont les skills/commandes existants du plugin appellent Python (jamais eu besoin d'étendre le PATH).
- `hooks/README.md` : section « Wrapper `_run.sh` » remplacée par « Déclenchement dans Claude Desktop (lazy init) » qui documente le vrai piège rencontré : Claude Desktop n'instancie le runtime Claude Code (et donc les hooks) que sur **invocation d'une commande du plugin** (`/todomail:start`, `/check-inbox`, etc.) — pas sur simple ouverture de session ou prompt conversationnel.

### Notes post-mortem

- En alpha.5, le log `.hooks_fired.log` restait vide non pas à cause du PATH, mais parce qu'aucune commande du plugin n'avait été invoquée pendant la session de test — le runtime n'était pas instancié.
- Ce qui a débloqué les hooks entre alpha.5 et alpha.6 n'est pas le wrapper, mais **(a)** le bump de version obligatoire pour que Claude Desktop recharge le plugin, combiné à **(b)** l'appel effectif de `/todomail:start`.
- L'amélioration du logging diagnostique (`source`, `session_id`, `cwd`, `sys.executable`, `PATH`) introduite en alpha.6 est conservée — c'est elle qui a permis de diagnostiquer proprement.

---

## [2.0.0-alpha.6] - 2026-04-18

### Corrigé

- **Hooks introuvables sur macOS Claude Desktop** : les apps GUI macOS héritent d'un PATH minimal (`/usr/bin:/bin:/usr/sbin:/sbin`) qui n'inclut ni `/opt/homebrew/bin` ni `/usr/local/bin`. Sur une installation Python par Homebrew (cas courant), les commandes `python3 …` des hooks échouaient silencieusement, rendant les 5 hooks inopérants. Les mêmes hooks fonctionnaient déjà correctement en CLI où le PATH utilisateur est hérité normalement.

### Ajouté

- `hooks/_run.sh` : wrapper shell qui préfixe `PATH` avec les chemins usuels (`/opt/homebrew/bin:/usr/local/bin:/opt/local/bin`) avant de déléguer à `python3`. Sort en exit 0 si `python3` reste introuvable (graceful degradation).
- `hooks/hooks.json` : les 5 commandes `python3 …` ont été remplacées par `sh "${CLAUDE_PLUGIN_ROOT}/hooks/_run.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/<hook>.py"`.
- `session_start.py` : le log `.hooks_fired.log` (activable via `.hooks_debug`) capture désormais `source`, `session_id`, `cwd`, `sys.executable` et les 200 premiers caractères du `PATH`, pour faciliter le diagnostic si un hook ne se déclenche toujours pas.
- `hooks/tests/test_hooks.sh` : deux tests supplémentaires valident l'invocation via `_run.sh` (20 OK au total).

### Notes

- **Bump de version obligatoire** : Claude Desktop ne rafraîchit le cache plugin que lorsque `plugin.json.version` change. Sans ce bump, l'installation via Customize garderait les scripts alpha.5 inchangés.
- Ce hotfix est indépendant du chemin de déclenchement Claude Code CLI — les utilisateurs CLI ne voient aucune différence fonctionnelle.

---

## [2.0.0-alpha.5] - 2026-04-18

### Ajouté — Refactoring v2 Phase 4

- 5 hooks Claude Code livrés avec le plugin, configurés dans `hooks/hooks.json` :
  - **`SessionStart`** → `hooks/session_start.py` : vérifie les répertoires standards, compile un index léger de la mémoire (`memory/people/`, `memory/projects/`, `memory/context/`) dans `${CLAUDE_PLUGIN_DATA}/memory_cache.json`, lit `state.json` et signale toute reprise nécessaire (`active_lock`, erreurs en attente, répertoires manquants) via `hookSpecificOutput.additionalContext`.
  - **`PreToolUse(Write|Edit)`** → `hooks/enforce_classify.py` : garde-fou structurel qui refuse toute écriture sous `docs/` hors de `docs/AURA/` ou `docs/MIN/` (règle `skills/classify-attachment/SKILL.md`). Émet un `permissionDecision: "deny"` structuré avec message explicite.
  - **`PostToolUse(Bash)`** → `hooks/invalidate_dashboard_cache.py` : filtré par `if: "Bash(mv *)"` et `if: "Bash(rm *)"`, touche `$CLAUDE_PROJECT_DIR/dashboard_invalidate.txt` et incrémente `state.counters.modifications` quand la commande affecte `todo/`, `inbox/` ou `mails/`. Signal préparatoire au polling du dashboard v3 (Phase 5).
  - **`UserPromptSubmit`** → `hooks/inject_context.py` : injecte silencieusement un résumé compact du `state.json` (`phase | lock | erreurs`) avant chaque prompt utilisateur uniquement si pertinent.
  - **`PreCompact`** → `hooks/pre_compact.py` : sauvegarde un snapshot horodaté du `state.json` et des derniers checkpoints dans `${CLAUDE_PLUGIN_DATA}/precompact_snapshot_<ts>.json` (rotation : 10 plus récents).
- `hooks/tests/test_hooks.sh` : 18 tests manuels couvrant deny/allow du garde-fou, no-op/touch du signal dashboard, silence de l'injection contextuelle, snapshot PreCompact, robustesse à un stdin vide, validité JSON de `hooks.json`.
- `hooks/README.md` entièrement réécrit : rôle de chaque hook, payload stdin, sortie JSON, timeouts, désactivation, smoke-test Claude Desktop, limitations connues.

### Notes

- **Format stdin JSON, pas env vars** : conforme au format officiel Claude Code 2.1+. Chaque hook lit son payload via `json.load(sys.stdin)` et sort une décision structurée (`hookSpecificOutput`) sur stdout plutôt que de s'appuyer sur des exit codes sensibles.
- **Graceful degradation** : tous les hooks encapsulent `main()` dans un `try/except Exception: pass` global et terminent en exit 0 en cas d'erreur inattendue. Seul `enforce_classify` émet une décision de refus (via JSON, jamais via crash).
- **Persistance via `${CLAUDE_PLUGIN_DATA}`** : `memory_cache.json` et les snapshots PreCompact survivent aux updates de plugin (Claude Desktop recopie `${CLAUDE_PLUGIN_ROOT}` à chaque installation, mais préserve `${CLAUDE_PLUGIN_DATA}`).
- **Signal dashboard dans `$CLAUDE_PROJECT_DIR`** : `dashboard_invalidate.txt` reste à la racine du projet utilisateur, compatible avec le hotfix `extractEmails` et prêt pour le polling 3 s prévu en Phase 5.
- **Smoke-test Claude Desktop activable** : créer `.hooks_debug` à la racine du projet pour que `session_start.py` journalise ses déclenchements dans `${CLAUDE_PLUGIN_DATA}/.hooks_fired.log`.

---

## [2.0.0-alpha.4] - 2026-04-17

### ⚠️ BREAKING — Refactoring v2 Phase 3

- Suppression de l'agent `todo-processor`. La logique d'analyse, de validation et de finalisation des mails est désormais intégrée dans le contexte principal (Opus 4.6 1M) de la commande `/process-todo`. Plus de fan-out `Task` par mail, plus de passage `_treatment.json` entre deux contextes.

### Ajouté

- Flags `--strict`, `--retry` et `--batch-validate` sur `/process-todo` (parsing sémantique via `$ARGUMENTS`, pattern hérité de `/check-inbox` alpha.3) :
  - `--strict` : arrêt à la première erreur avec demande utilisateur.
  - `--retry` : saute les Étapes 1-2 et retraite uniquement les mails inscrits dans `state.errors[]`, chaque entrée étant retirée après succès.
  - `--batch-validate` : **opt-in uniquement, jamais automatique**. Présente toutes les propositions interactives en un seul rendu avec validation en lot (`OUI tous` / `NON tous` / `OUI sauf 3,7,12`). Les mails refusés repassent en mode séquentiel.
- Idempotence systématique des opérations fichiers via `lib/fs_utils.py` (`safe_mv`, `safe_rm`, `atomic_write_json`, `write_pending_emails`, `write_instructions`). Toute étape peut être rejouée sans effet de bord.
- Reprise sur erreur granulaire : `_treatment.json` écrit à chaque phase (`analyze`, `finalize`, `autonomous`) **avant** tout déplacement final, servant d'artefact de reprise si la session meurt entre deux phases.
- Vérification de fraîcheur des `instructions.json` : si `_meta.consumes_session_id` ne correspond pas au `session_id` courant, demande de confirmation (`AskUserQuestion`) avant traitement. Empêche de rejouer aveuglément un `instructions.json` périmé.
- Cache RAG obligatoire pour tous les appels MCP (`search_mail`/`search_doc`/`search_all`/`get_availability`/`fetch_calendar_events`) via `lib/rag_cache.py` — pas d'exception.
- Verrou `process-todo` sur `state.json.active_lock` : arrêt propre si un autre cycle est déjà en cours.
- Signal `dashboard_invalidate.txt` touché en fin de cycle (préparatoire à la Phase 5 ; sans effet visible avant).

### Modifié

- `commands/process-todo.md` : réécrit en 350 lignes (vs 403 précédemment) avec 6 étapes (warm-up, collecte instructions, actions simples, actions `other` complexes, cohérence, finalisation). Vérification préalable MCP (alpha.2) préservée en tête.
- `skills/classify-attachment/SKILL.md` : références à `todo-processor` remplacées par `/process-todo` (le skill reste un document de référence lu par la commande).
- `skills/memory-management/SKILL.md` : section `process-todo` réécrite pour refléter le traitement en flux dans le contexte principal (plus d'agent intermédiaire).
- `README.md` : table des agents simplifiée (seul `mail-prefilter` subsiste), arborescence mise à jour, note sur la suppression de `todo-processor`.
- `CONNECTORS.md` : colonne `todo-processor` retirée du tableau d'utilisation ; les appels MCP de `process-todo` passent de `(i)` à direct. Nouvelle entrée documentant la refonte alpha.4.
- `CLAUDE.md` : arborescence des agents mise à jour.

### Comportement par défaut conservé

- **Validation séquentielle** (un mail à la fois avec ARRÊT OBLIGATOIRE par mail) reste le mode par défaut, identique à l'expérience v1.x.
- Vérification préalable MCP (alpha.2) intacte en première étape.
- `_deferred.json` : file d'attente persistante entre Étape 2 (déplacement inter-catégories) et Étape 3 (traitement `other`), évite un aller-retour dashboard.
- Pré-allocation des numéros `to-send/` (via `max(NN)+1` sur `ls`) conservée pour cohérence, même sans parallélisme.
- Règles anti-hallucination (lecture effective obligatoire, chemins PJ obligatoirement sous `docs/AURA/` ou `docs/MIN/`) préservées et affichées en bloc visible.
- Rétro-compatibilité lecture des `instructions.json` v1 (tableau brut produit par le dashboard actuel) maintenue via `lib.fs_utils.read_v2_json`. Le dashboard continue à fonctionner sans modification (hotfix post-alpha.3 toujours en place).

### Supprimé

- `agents/todo-processor.md`.

---

## [2.0.0-alpha.3] - 2026-04-17

### ⚠️ BREAKING — Refactoring v2 Phase 2

- Suppression de l'agent `mail-analyzer`. Sa logique est désormais intégrée directement dans le skill `sort-mails` qui exploite le contexte 1M d'Opus 4.6 et traite les mails en flux (plus d'isolation systématique par agent).
- Format `pending_emails.json` v2 produit pour la première fois : objet wrapper `{ "_meta": {...}, "emails": [...] }` via `lib/fs_utils.write_pending_emails`. La lecture reste rétro-compatible (les anciens fichiers `[]` sont encore lus grâce à `read_v2_json`).
- La fusion remplace la purge inconditionnelle : les entrées existantes des `pending_emails.json` sont conservées et dédoublonnées par `id` au lieu d'être écrasées.

### Ajouté

- Agent `mail-prefilter` (Haiku 4.5) : un seul appel batch sur les métadonnées de tous les mails de `inbox/` retourne un pré-classement `trash` / `do-read-quick` / `unsure`. Court-circuit en-dessous de 5 mails.
- Cache RAG en mémoire de session via `lib/rag_cache.py` : `sort-mails` mémoïse les appels `search_mail` / `search_doc` / `search_all` / `get_availability` / `fetch_calendar_events` pour éviter les redondances.
- Flags `--strict` et `--retry` sur `/check-inbox` (parsing sémantique via `$ARGUMENTS`) :
  - `--strict` : arrêt immédiat à la première erreur avec demande utilisateur.
  - `--retry` : saute le téléchargement IMAP et retraite uniquement les mails inscrits dans `state.errors[]`, en retirant chaque entrée après retry réussi.
- Artefacts de reprise : chaque mail analysé produit un `_analysis.json` dans son répertoire, réutilisé tel quel si un cycle est interrompu (idempotence granulaire).
- Table de lecture des pièces jointes unifiée via `markitdown` (Microsoft) pour `.docx`, `.xlsx`, `.pptx`, `.rtf`, `.epub`. Remplace les appels spécifiques à `python-docx` et `openpyxl`. ODF reste couvert par le skill `read-odf` interne.
- Batching adaptatif : au-delà de 30 mails, l'analyse est fractionnée en batches de 10 à 15 avec checkpoints intermédiaires pour permettre la reprise granulaire.
- Verrou `sort-mails` sur `state.json.active_lock` : arrêt propre si un autre cycle est déjà en cours.

### Modifié

- `skills/sort-mails/SKILL.md` : réécrit en version 2.0.0 (≤250 lignes) avec 6 étapes (warm-up, pré-filtrage, analyse Opus 1M, tri+écriture v2, finalisation `state.json`, compte-rendu). La vérification du serveur MCP n'est plus dupliquée dans le skill ; elle est assurée une seule fois par `/check-inbox` en amont.
- `commands/check-inbox.md` : frontmatter enrichi (`argument-hint`), transmission des flags au skill, section « Verification préalable » alpha.2 préservée en tête.
- `README.md` : table des agents mise à jour (remplacement de `mail-analyzer` par `mail-prefilter`), section « Cycle de vie des pending_emails.json » réécrite, ajout de `markitdown` aux dépendances.
- `CONNECTORS.md` : colonne `mail-analyzer` retirée du tableau d'utilisation ; les appels MCP de `sort-mails` passent de `(i)` à direct. Section « Désambiguation multi-serveurs » (alpha.2) préservée telle quelle.
- `skills/agenda`, `disponibilites`, `detection-conflits`, `memory-management`, `read-odf` : références à `mail-analyzer` remplacées par `sort-mails`.

### Optimisé

- Suppression du fan-out systématique d'agents à l'analyse : un seul contexte Opus 1M traite jusqu'à ~30 mails sans saturation, les volumes supérieurs sont fractionnés en batches.
- Réduction des appels MCP redondants grâce au cache RAG (typiquement -50% sur un cycle).
- Pré-filtrage Haiku : les newsletters et accusés de réception évidents ne mobilisent plus le contexte Opus.

### Supprimé

- `agents/mail-analyzer.md`.

### Corrigé (hotfix post-merge)

- **Dashboard — rétro-compatibilité de lecture v1/v2** : le dashboard lisait les `pending_emails.json` comme un tableau brut. Dès qu'un cycle alpha.3 écrit le format v2 (wrapper `{ "_meta": ..., "emails": [...] }`), `data.forEach` levait une TypeError et provoquait un écran blanc après sélection du répertoire. Ajout d'une fonction helper `extractEmails(data)` qui accepte les deux formats. Même traitement appliqué à la lecture des `instructions.json` (v1 = tableau, v2 = `{ "_meta": ..., "instructions": [...] }`). Correctif de lecture uniquement — le dashboard continue à écrire le format v1 (refonte complète en Phase 5). Après mise à jour du plugin, relancer `/todomail:start` dans le workspace pour rafraîchir le `dashboard.html` local.

---

## [2.0.0-alpha.2] - 2026-04-17

### Supprime

- `.mcp.json` a la racine du plugin : inadequat dans Claude Desktop (le proxy stdio de FastMCP exige un serveur HTTP local non-authentifie, inexistant dans le setup de l'utilisateur qui utilise uniquement des serveurs Auth0/Cloudflare). Cree plus de problemes qu'il n'en resout (connexions dupliquees, serveur fantome, comportement erratique).

### Ajoute

- Mecanisme de desambiguation au niveau du workspace : fichier `.todomail-config.json` a la racine du repertoire de travail (gitignore, geree automatiquement par le plugin) contenant le `expected_rag_name` du serveur MCP attendu.
- `lib/config.py` : helper Python pour lire/ecrire la config workspace et verifier le `rag_name` via le tool MCP `status`.
- Commande `/start` : nouvelle etape 0 "Configuration du serveur MCP" qui detecte le(s) serveur(s) archiva connecte(s), demande a l'utilisateur lequel utiliser pour ce workspace (via `AskUserQuestion`) et ecrit la config.
- Commandes `/check-inbox` et `/process-todo` : verification prealable obligatoire que `status.rag_name` correspond a `expected_rag_name`. En cas de mismatch, arret avec message clair.

### Modifie

- `CONNECTORS.md` : documentation du mecanisme de desambiguation et du cas d'usage multi-serveurs.
- `README.md` : retrait de la mention `.mcp.json` dans l'arborescence, ajout de `.todomail-config.json` dans l'arborescence workspace.

---

## [2.0.0-alpha.1] - 2026-04-16

### BREAKING — Refactoring v2 Phase 1

- Fork definitif Claude Code : suppression de tout le code de compatibilite Cowork (`allow_cowork_file_delete`, notes VM).
- Le plugin n'est plus compatible avec Claude Cowork. Pour la derniere version Cowork, voir tag v1.4.1.

### Ajoute

- `.mcp.json` : declaration explicite du serveur MCP local via proxy stdio (`archiva-pro`). Remplace le placeholder `~~todomail-mcp` et resout le probleme de double serveur MCP.
- `hooks/hooks.json` : squelette pour les 5 hooks Claude Code (a remplir en Phase 4).
- `lib/` : utilitaires partages Python (`state.py`, `fs_utils.py`, `rag_cache.py`, `error_modes.py`).
- Schema JSON v2 : wrapper `_meta` avec `schema_version`, `session_id`, `generated_at` pour `pending_emails.json` et `instructions.json`.
- Strategie d'erreur formalisee : `lenient` par defaut, `resume` toujours actif, `--strict` opt-in.

### Supprime

- Toutes les references a `allow_cowork_file_delete` dans les commandes, agents et skills.
- Notes et mentions Cowork dans la documentation (README, CONNECTORS, CLAUDE.md, README.dashboard).

---

## [1.4.1] - 2026-03-30

### Corrigé
- **Skill `classify-attachment`** — Ajout du frontmatter YAML conforme Cowork (`name`, `description`, `version`) qui manquait et empêchait l'installation du plugin. Rétablissement des accents. Reformulation de la section « Sortie attendue » en « Format de stockage dans `_treatment.json` » avec ajout du champ `classification_anomaly`.
- **todo-processor** — Utilisation de chemins absolus `${CLAUDE_PLUGIN_ROOT}` pour les 3 références au skill. Correction des formulations « si le skill retourne null » en « si l'algorithme aboutit à une anomalie ».

---

## [1.4.0] - 2026-03-30

### Ajouté
- **Skill `classify-attachment`** — Nouveau skill centralisant les règles de classement des pièces jointes dans `docs/`. Impose la structure canonique à deux branches (`docs/AURA/` et `docs/MIN/`), les conventions de nommage (MAJUSCULES, underscores), et un garde-fou qui refuse tout chemin hors de cette hiérarchie. Inclut un algorithme en 4 étapes (branche racine, recherche RAG filtrée, fallback par table de correspondances, validation) et une table de 18 correspondances thématiques.

### Modifié
- **todo-processor** — Les trois modes (autonomous, analyze, finalize) délèguent désormais le classement des PJ au skill `classify-attachment` au lieu de contenir leur propre logique basée sur `search_doc` sans contrainte structurelle. Cela empêche la création de répertoires parasites à la racine de `docs/`.

---

## [1.3.0] - 2026-03-30

### Corrigé
- **Opérations fichiers Cowork** — Ajout de pré-autorisations `allow_cowork_file_delete` dans `process-todo`, `todo-processor`, `sort-mails` et `check-inbox` pour corriger les `mv`/`rm` qui échouent silencieusement avec "Operation not permitted" sur les fichiers créés dans une session Cowork antérieure. Ajout de gestion d'erreur avec retry automatique.

---

## [1.2.0] - 2026-03-13

### Ajouté
- **Dashboard — Vue Tâches** — Nouvelle vue complète « Tâches » dans le dashboard avec 3 sections : Suivi consultations (lecture/édition de `consult.md`), Mails à envoyer (gestion des fichiers `to-send/` avec aperçu, copie presse-papier, édition), Travail à faire (gestion des dossiers `to-work/` avec checklist et documents). Suppression inline avec confirmation, modales d'édition, filtres et tris.
- **Format structuré des fichiers `to-send/`** — Les fichiers `.md` générés dans `to-send/` utilisent désormais un frontmatter YAML obligatoire (`to`, `cc`, `subject`, `date`, `ref_mail_id`) pour structurer les mails comme des messages prêts à envoyer.

### Modifié
- **process-todo** — Étape 3f : la mise à jour de `consult.md` inclut désormais les mails `do-other` en plus de `do-consult-and-decide`.
- **todo-processor** — Mode `finalize` : ajout de `finalization.consult_entry` pour la catégorie `do-other`. Spécification du format frontmatter YAML obligatoire pour tous les fichiers `to-send/`.

---

## [1.0.0] - 2026-03-13

Première release stabilisée de TodoMail.

### Ajouté
- **Dashboard v2 — Sauvegarde automatique** — Les fichiers `instructions.json` sont désormais générés et mis à jour automatiquement à chaque action utilisateur. Suppression du bouton « VALIDER LES ORDRES ». Toast de confirmation visuel à chaque sauvegarde.
- **Dashboard v2 — Valeurs par défaut intelligentes** — Action par défaut SUPPRIMER pour la catégorie Corbeille, TRAITER pour toutes les autres catégories. Les décisions existantes dans un `instructions.json` sont rechargées automatiquement au retour dans une catégorie.
- **Dashboard v2 — Menu de navigation** — Menu horizontal dans l'en-tête avec onglets Catégorisation (actif), Mémoire (placeholder) et Tâches (placeholder), préparant l'ajout de futures fonctionnalités.
- **Dashboard v2 — Scrollbar cartes dépliables** — Scrollbar discret dans les zones dépliables pour les synthèses longues.

### Modifié
- **README.md** — Mise à jour de la description du dashboard (auto-sync, défauts, menu nav). Ajout de `todo-processor.md` dans l'arborescence agents.
- **README.dashboard.md** — Documentation des nouvelles fonctionnalités : sauvegarde automatique, valeurs par défaut, menu de navigation principal, scrollbar. Mise à jour de la section instructions.json.

---

## [0.32.1] - 2026-03-12

### Modifié
- **todo-processor** — Passage du modèle Sonnet à Opus pour améliorer la qualité d'analyse et de rédaction.

---

## [0.32.0] - 2026-03-12

### Ajouté
- **Nouvel agent `todo-processor`** — Agent autonome qui traite un mail unique pour process-todo dans un contexte isolé. Trois modes : « autonomous » (traitement complet do-read-long : archivage, classement PJ, nettoyage), « analyze » (Phase 1 d'analyse et production de propositions pour les catégories interactives), « finalize » (Phase 2 d'archivage et finalisation après validation utilisateur). Produit un fichier `_treatment.json` dans le répertoire du mail.

### Modifié
- **process-todo** — Refonte de l'Étape 3. Les traitements « other » complexes sont désormais délégués à l'agent `todo-processor` via `Task` dans des contextes isolés. Phase 1 (analyse) parallélisée sur tous les mails. Les ARRÊTS OBLIGATOIRES restent dans le contexte principal. Phase 2 (finalisation) parallélisée après validation utilisateur. Ajout de `Task` dans les `allowed-tools`. Pré-allocation des numéros `to-send/` pour éviter les conflits entre agents parallèles. Consolidation centralisée de `consult.md` et de la mémoire après collecte de tous les résultats. Production des livrables do-self dans le contexte principal via les skills plateforme.
- **CONNECTORS.md** — Ajout de la colonne `todo-processor` dans le tableau d'utilisation des tools MCP. Mise à jour de la légende pour refléter la délégation process-todo → todo-processor.
- **README.md** — Ajout de `todo-processor` dans la table Agents.
- **memory-management** — Mise à jour de la section Intégration pour refléter la délégation à `todo-processor` et la consolidation mémoire centralisée.

### Optimisé
- **Réduction de la consommation de contexte** — Isolation du traitement de chaque mail dans un agent dédié, éliminant l'accumulation de contexte qui saturait le traitement dès 10-20 mails. Exécution parallèle des analyses (Phase 1) et des finalisations (Phase 2).

---

## [0.31.0] - 2026-03-03

### Ajouté
- **Nouvel agent `mail-analyzer`** — Agent autonome qui analyse un mail unique dans un contexte isolé : lecture du mail et de toutes les pièces jointes, contextualisation RAG, classification, détection agenda avec vérification de disponibilité et de conflits, production de synthèses multi-niveaux. Produit un fichier `_analysis.json` dans le répertoire du mail.

### Modifié
- **sort-mails v1.0.0** — Refonte complète du flux de tri. Les mails sont désormais analysés en parallèle par des agents `mail-analyzer` indépendants (un par mail), puis triés et les `pending_emails.json` générés exclusivement à partir des `_analysis.json`. Suppression de la triple lecture des mails. Suppression de la vérification par sondage (rendue inutile par l'isolation des contextes). Ajout de `Task` dans les `allowed-tools`.
- **Gains de performance** — Réduction drastique de la consommation de contexte, exécution parallèle des analyses, élimination des compressions de contexte en cours d'exécution.
- **README.md** — Ajout de la section Agents dans l'architecture, mise à jour de l'arborescence, cycle de vie des `pending_emails.json`.

---

## [0.30.0] - 2026-02-28

### Modifié
- **process-todo** — Traitement automatique après déplacement inter-catégories : lorsqu'un mail est reclassé via le dashboard vers une autre catégorie, il est désormais automatiquement traité comme une action `other` dans la catégorie de destination. Les déplacements vers `do-read-quick` sont traités immédiatement (archivage). Les déplacements vers les autres catégories sont mis en file d'attente via `todo/_deferred.json`. Le champ `agenda-info` est explicitement recopié lors des déplacements inter-catégories.

---

## [0.29.0] - 2026-02-25

### Corrigé
- Correction du nommage `/check_agenda` → `/check-agenda` dans tous les fichiers (cohérence kebab-case).
- Ajout de `AskUserQuestion` dans les `allowed-tools` du skill `agenda`.
- Correction du skill `disponibilites` : ajout d'un appel `fetch_calendar_events` (étape 1b) pour calculer les buffers de déplacement.
- Harmonisation de la taille cible de CLAUDE.md à ~250 lignes dans le skill `memory-management`.

### Modifié
- **dashboard.html** — Affichage des informations `agenda-info` : badge compact dans la carte principale et panneau détaillé dans la section dépliable.
- **process-todo** — Exploitation du champ `agenda-info` dans les 4 handlers d'actions complexes.
- **start** — Ajout de la création de `memory/context/preferences-agenda.md` lors du bootstrap calendrier.
- **/briefing** — Ajout d'une étape de mise à jour de la mémoire. Ajout de `Task` dans les `allowed-tools`.
- **/check-agenda** — Ajout d'une étape de mise à jour de la mémoire.
- **CONNECTORS.md** — Refonte du tableau d'utilisation des tools.

### Optimisé
- **sort-mails** — Pré-chargement calendrier unique sur 14 jours au lieu d'appels redondants par mail.
- Externalisation de la géographie : remplacement des données codées en dur par des références à la mémoire.

---

## [0.28.0] - 2026-02-22

### Ajouté
- **Skill `agenda` v1.0.0** — Connaissance du programme de l'utilisateur (consultation calendrier, enrichissement contextuel, détection conflits, signalement déplacements).
- **Skill `disponibilites` v1.0.0** — Connaissance des créneaux libres avec filtres contextuels.
- **Skill `detection-conflits` v1.0.0** — Détection des conflits, superpositions, temps de déplacement insuffisant et surcharge.
- **Commande `/briefing`** — Génération de dossiers de préparation pour les réunions.
- **Commande `/check-agenda`** — Audit de cohérence et faisabilité de l'agenda avec rapport structuré.
- **sort-mails v0.15.0** — Détection des mails liés à l'agenda. Enrichissement automatique avec vérification de disponibilité et détection de conflits. Ajout du champ optionnel `agenda-info`.
- **memory-management v0.3.0** — Ajout des sections mémoire calendrier : réunions récurrentes, lieux fréquents, préférences agenda.
- **start** — Ajout du répertoire `to-brief/`, bootstrap calendriers, nouvelles sections CLAUDE.md.
- **CONNECTORS.md** — Ajout des tools calendrier et du tableau d'utilisation par composant.

---

## [0.27.0] - 2026-02-18

### Modifié
- **sort-mails v0.14.0** — Si inbox est vide, ne plus purger ni régénérer les `pending_emails.json` existants (préservation des synthèses).
- **process-todo** — Mise à jour du `pending_emails.json` de la catégorie destination lors des déplacements inter-catégories. Remplacement de la suppression des `instructions.json` par un écrasement avec `[]`.
- **memory-management v0.2.0** — Enrichissement de la description avec des phrases de déclenchement. Ajout de `process-todo` dans la section intégration.

### Corrigé
- **README.dashboard.md** — Correction du libellé de l'action `delete`.

---

## [0.26.0] - 2026-02-15

### Modifié
- **sort-mails v0.13.0** — Ajout d'une purge préalable des `pending_emails.json` en début d'Étape 2.
- **process-todo** — Mise à jour incrémentale des `pending_emails.json` au fil de l'eau au lieu d'une régénération complète en Étape 4.
