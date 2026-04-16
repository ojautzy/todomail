# Hooks TodoMail

Squelette des hooks Claude Code pour le plugin TodoMail.
Les hooks sont definis dans `hooks.json` et seront implementes en **Phase 4** du refactoring v2.

## Hooks prevus

### SessionStart

Script prevu : `hooks/session_start.py`

- Verification de l'existence des repertoires de travail
- Compilation de la memoire (`CLAUDE.md` + `memory/`) dans un cache serialise dans `${CLAUDE_PLUGIN_DATA}/memory_cache.json`
- Verification du statut RAG via MCP et alerte si desynchronise
- Lecture de `state.json` et signalement de toute session interrompue a reprendre

### PreToolUse

Scripts prevus :

- `hooks/enforce_classify.py` (matcher `Write|Edit`) : bloque toute ecriture dans `docs/` qui ne commence pas par `docs/AURA/` ou `docs/MIN/`. Emet `permissionDecision: "deny"` en cas de violation.
- Matcher `Bash` avec `mv`/`rm` sur `mails/`, `to-clean-by-user/` : log et avertissement.

### PostToolUse

Script prevu : `hooks/invalidate_dashboard_cache.py` (matcher `Bash(mv:*)` et `Bash(rm:*)` sur `todo/` et `inbox/`)

- Mise a jour du `state.json` (increment compteur de modifications)
- Touch de `dashboard_invalidate.txt` pour le polling dashboard (3s)

### UserPromptSubmit

Script prevu : `hooks/inject_context.py`

- Injection silencieuse du resume de `state.json` et des compteurs dashboard dans le contexte avant chaque prompt utilisateur

### PreCompact

Script prevu : `hooks/pre_compact.py`

- Sauvegarde de l'etat complet de la session (variables cles, file d'attente) dans `state.json` pour permettre la reprise apres compaction

## Notes

- Les hooks sont desactivables individuellement via `settings.local.json`
- Aucune logique metier dans les hooks : ils doivent etre courts, deterministes et desactivables
- Ce fichier `hooks.json` est un artefact de planification. Les hooks reels seront configures dans les settings Claude Code en Phase 4 via les scripts Python ci-dessus.
- Voir `REFACTOR_PLAN.md` Phase 4 pour le detail complet
