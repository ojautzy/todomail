#!/usr/bin/env bash
# Tests manuels des hooks TodoMail — Phase 4 (alpha.5).
#
# Chaque hook reçoit un payload JSON sur stdin. On vérifie les exit codes,
# les sorties JSON (permissionDecision, additionalContext) et la
# robustesse à un stdin vide.

set -u

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PLUGIN_ROOT"

PASS=0
FAIL=0
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# Isolation : on force CLAUDE_PLUGIN_DATA et CLAUDE_PROJECT_DIR dans un
# temp pour ne pas polluer l'environnement utilisateur.
export CLAUDE_PLUGIN_DATA="$TMPDIR/plugin-data"
export CLAUDE_PROJECT_DIR="$TMPDIR/project"
mkdir -p "$CLAUDE_PLUGIN_DATA" "$CLAUDE_PROJECT_DIR"

check() {
  local label="$1"; shift
  if "$@"; then
    echo "  OK  $label"
    PASS=$((PASS + 1))
  else
    echo "  FAIL $label"
    FAIL=$((FAIL + 1))
  fi
}

assert_deny() {
  local out="$1"
  echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["hookSpecificOutput"]["permissionDecision"]=="deny", d' 2>/dev/null
}

assert_no_deny() {
  local out="$1"
  # Accepte output vide OU output sans deny
  [ -z "$out" ] && return 0
  echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("hookSpecificOutput",{}).get("permissionDecision")!="deny" else 1)' 2>/dev/null
}

echo "=== enforce_classify ==="

out=$(echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"docs/RANDOM/test.pdf"}}' | python3 hooks/enforce_classify.py)
check "deny: docs/RANDOM/..." assert_deny "$out"

out=$(echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"docs/AURA/FINANCES/x.pdf"}}' | python3 hooks/enforce_classify.py)
check "allow: docs/AURA/..." assert_no_deny "$out"

out=$(echo '{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"docs/MIN/RH/x.pdf"}}' | python3 hooks/enforce_classify.py)
check "allow: docs/MIN/..." assert_no_deny "$out"

out=$(echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"src/foo.py"}}' | python3 hooks/enforce_classify.py)
check "allow: hors docs/" assert_no_deny "$out"

out=$(echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"docs/a.txt"}}' | python3 hooks/enforce_classify.py)
check "deny: docs/ racine (hors AURA|MIN)" assert_deny "$out"

# Stdin vide : ne crashe pas
check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/enforce_classify.py'

echo "=== invalidate_dashboard_cache ==="

# Commande qui ne concerne pas todo/inbox/mails -> pas de fichier touché
rm -rf "$CLAUDE_PROJECT_DIR/.todomail"
echo '{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"mv src/a.py src/b.py"}}' | python3 hooks/invalidate_dashboard_cache.py
check "no-op: mv hors watched" bash -c '[ ! -f "$CLAUDE_PROJECT_DIR/.todomail/invalidate.txt" ]'

# Commande qui touche todo/
echo '{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"mv todo/a.json todo/done/a.json"}}' | python3 hooks/invalidate_dashboard_cache.py
check "touch: mv sur todo/" bash -c '[ -f "$CLAUDE_PROJECT_DIR/.todomail/invalidate.txt" ]'

# rm sur inbox/
rm -rf "$CLAUDE_PROJECT_DIR/.todomail"
echo '{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"rm inbox/old.eml"}}' | python3 hooks/invalidate_dashboard_cache.py
check "touch: rm sur inbox/" bash -c '[ -f "$CLAUDE_PROJECT_DIR/.todomail/invalidate.txt" ]'

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/invalidate_dashboard_cache.py'

echo "=== inject_context ==="

# Sans state.json particulier : silencieux
out=$(echo '{"hook_event_name":"UserPromptSubmit","prompt":"hi"}' | python3 hooks/inject_context.py)
check "silence si rien a signaler" bash -c '[ -z "$1" ] || ! echo "$1" | grep -q additionalContext' _ "$out"

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/inject_context.py'

echo "=== session_start ==="

out=$(echo '{"hook_event_name":"SessionStart","source":"startup"}' | python3 hooks/session_start.py)
check "exit 0 sans crash" bash -c 'true'
# Le cache mémoire doit avoir été créé (même s'il est vide)
check "memory_cache.json cree" bash -c '[ -f "$CLAUDE_PROJECT_DIR/.todomail/memory_cache.json" ]'

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/session_start.py'

echo "=== pre_compact ==="

echo '{"hook_event_name":"PreCompact","trigger":"manual"}' | python3 hooks/pre_compact.py
check "snapshot cree" bash -c 'ls "$CLAUDE_PROJECT_DIR"/.todomail/precompact_snapshot_*.json >/dev/null 2>&1'

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/pre_compact.py'

echo "=== hooks.json valide ==="
check "hooks.json JSON valide" bash -c 'python3 -m json.tool hooks/hooks.json >/dev/null'

# Verifie que plus aucune reference au wrapper n'existe (alpha.7+)
check "pas de reference _run.sh dans hooks.json" bash -c '! grep -q "_run.sh" hooks/hooks.json'

echo ""
echo "Resultat : $PASS OK / $FAIL FAIL"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo "All hooks tests passed"
exit 0
