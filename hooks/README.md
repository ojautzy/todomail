# Hooks TodoMail

Hooks Claude Code livrés avec le plugin TodoMail (Phase 4, alpha.5).
Leur rôle est d'automatiser ce qui était auparavant déclaratif (à la
charge du LLM) : warm-up mémoire, garde-fou filesystem, invalidation
du dashboard, injection contextuelle, anti-compaction.

## Principes

- **Aucune logique métier** : chaque hook reste court et déterministe.
  Si un hook commence à dépasser 100 lignes, sa logique doit être
  extraite dans `lib/`.
- **Graceful degradation** : tous les hooks wrappent leur `main()` dans
  un `try/except Exception: pass` global et sortent en exit 0 en cas
  d'erreur inattendue. Seul `enforce_classify` peut émettre une
  décision de refus.
- **Entrée** : chaque hook lit son payload JSON sur **stdin** (format
  officiel Claude Code). Les variables d'environnement utilisées sont
  `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` et
  `$CLAUDE_PROJECT_DIR` (la `cwd` du payload sert de repli).
- **Sortie** : JSON structuré sur stdout (`hookSpecificOutput` avec
  `additionalContext` ou `permissionDecision`). Silence par défaut.

## Hooks livrés

### `session_start.py` — event `SessionStart`

À chaque démarrage/reprise de session :

- vérifie les répertoires standards (`inbox/`, `todo/`, `mails/`,
  `to-send/`, `to-work/`, `docs/`) dans `$CLAUDE_PROJECT_DIR` ;
- compile un index léger de la mémoire (`memory/people/`,
  `memory/projects/`, `memory/context/`) dans
  `${CLAUDE_PLUGIN_DATA}/memory_cache.json` ;
- lit `state.json` via `lib.state.load_state()` ; si `active_lock`,
  erreurs en attente ou répertoires manquants, injecte un message
  sous forme `hookSpecificOutput.additionalContext` pour signaler à
  Claude qu'une reprise est possible (`--retry`).

Timeout : 10 s. Non bloquant.

### `enforce_classify.py` — event `PreToolUse` (matcher `Write|Edit`)

Garde-fou structurel pour `docs/`. Refuse toute écriture dont le chemin
est sous `docs/` sans commencer par `docs/AURA/` ou `docs/MIN/` (voir
`skills/classify-attachment/SKILL.md`). Émet un JSON :

```json
{"hookSpecificOutput": {
  "hookEventName": "PreToolUse",
  "permissionDecision": "deny",
  "permissionDecisionReason": "..."
}}
```

Timeout : 5 s. Seul hook qui peut bloquer une action (volontairement).

### `invalidate_dashboard_cache.py` — event `PostToolUse` (matcher `Bash`)

Filtré par `if: "Bash(mv *)"` et `if: "Bash(rm *)"` dans
`hooks.json`. Si la commande Bash exécutée contient un `mv` ou un `rm`
touchant `todo/`, `inbox/` ou `mails/` :

- `touch` de `$CLAUDE_PROJECT_DIR/dashboard_invalidate.txt` (signal pour
  le dashboard v3 qui polle ce fichier toutes les 3 s — Phase 5) ;
- incrémente `state.counters.modifications`.

Timeout : 5 s. Non bloquant.

### `inject_context.py` — event `UserPromptSubmit`

Avant chaque prompt utilisateur, lit `state.json` et injecte un résumé
compact (`phase | lock | erreurs`) via
`hookSpecificOutput.additionalContext` **uniquement** si quelque chose
mérite l'attention de Claude. Silencieux le reste du temps.

Timeout : 5 s. Non bloquant.

### `pre_compact.py` — event `PreCompact`

Avant la compaction du contexte, sauvegarde un snapshot du `state.json`
et des derniers checkpoints dans
`${CLAUDE_PLUGIN_DATA}/precompact_snapshot_<timestamp>.json`. Conserve
les 10 snapshots les plus récents.

Timeout : 10 s. Ne bloque jamais la compaction.

## Format `hooks.json`

Validé avec la doc officielle Claude Code
(<https://code.claude.com/docs/en/hooks>). Structure indicative :

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/enforce_classify.py\"",
            "timeout": 5 }
        ]
      }
    ]
  }
}
```

Le champ `if` (`"if": "Bash(mv *)"`) filtre les commandes Bash via la
syntaxe des règles de permission — plus déclaratif qu'une regex côté
Python.

## Désactivation individuelle

Trois moyens, du plus ciblé au plus global :

1. **Commenter l'entrée** dans `hooks/hooks.json` (retirer l'objet
   concerné du tableau de l'event). Nécessite un bump de version côté
   plugin pour que Claude Desktop rafraîchisse le cache.
2. **Désactiver via `settings.local.json`** côté utilisateur :
   ```json
   {
     "disabledHooks": {
       "todomail": ["enforce_classify.py"]
     }
   }
   ```
   (à confirmer selon la version de Claude Code installée — clé exacte
   exposée via `claude plugin list --json`).
3. **Désactiver le plugin entier** via `/plugin` → *Disable*.

## Test manuel

Le script `hooks/tests/test_hooks.sh` invoque chaque hook avec des
payloads JSON fictifs :

```bash
bash hooks/tests/test_hooks.sh
```

Exemple minimal pour `enforce_classify` :

```bash
echo '{"hook_event_name":"PreToolUse","tool_name":"Write",
       "tool_input":{"file_path":"docs/RANDOM/x.pdf"}}' \
  | python3 hooks/enforce_classify.py
# → JSON avec permissionDecision=deny
```

## Smoke-test Claude Desktop

Pour vérifier que les hooks se déclenchent bien via le chemin
*Customize → Plugins* de Claude Desktop, créer un fichier vide
`.hooks_debug` à la racine du projet (`$CLAUDE_PROJECT_DIR`) avant
d'ouvrir une session. `session_start.py` écrira alors une ligne
dans `${CLAUDE_PLUGIN_DATA}/.hooks_fired.log` à chaque déclenchement.

Chemin typique :
`~/.claude/plugins/data/todomail-<marketplace>/.hooks_fired.log`.

Supprimer `.hooks_debug` désactive le log (silencieux par défaut).

## Wrapper `_run.sh` (macOS Claude Desktop)

Toutes les commandes dans `hooks.json` passent par
`hooks/_run.sh <script.py>` plutôt que d'appeler `python3` directement.
Raison : sur macOS, Claude Desktop (app GUI) hérite d'un PATH minimal
(`/usr/bin:/bin:/usr/sbin:/sbin`) qui ne contient ni `/opt/homebrew/bin`
ni `/usr/local/bin`. Les utilisateurs installant Python via Homebrew
(cas très majoritaire) verraient sinon leurs hooks échouer
silencieusement.

Le wrapper :

1. Préfixe le `PATH` avec `/opt/homebrew/bin:/usr/local/bin:/opt/local/bin`.
2. Vérifie que `python3` est trouvable — sinon sort en exit 0 (graceful
   degradation : on ne plante jamais une session).
3. `exec python3 "$@"` avec le PATH étendu.

Ce wrapper est inoffensif en CLI : le PATH hérité est déjà complet, les
préfixes ajoutés ne gênent pas.

## Limitations connues

- **Plugin cache en lecture seule** (`${CLAUDE_PLUGIN_ROOT}` =
  `~/.claude/plugins/cache/<id>/`) : aucun hook n'écrit dans le
  répertoire plugin. Toute persistance va dans `${CLAUDE_PLUGIN_DATA}`
  (survit aux updates) ou dans `$CLAUDE_PROJECT_DIR` (signal dashboard).
- **Claude Desktop ne rafraîchit le cache plugin qu'à l'update** : un
  changement de script côté dépôt nécessite un bump de version dans
  `.claude-plugin/plugin.json` et une mise à jour via
  *Customize → Plugins → Update*.
- Les **monitors** (plugin-level background tasks) ne fonctionnent
  qu'en CLI interactif et sont hors périmètre de cette phase.

## Références

- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
- `REFACTOR_PLAN.md` — section Phase 4
- `lib/README.md` — APIs consommées par les hooks
