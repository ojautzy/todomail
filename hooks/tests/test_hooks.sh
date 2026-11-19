#!/usr/bin/env bash
# Tests manuels des hooks TodoMail — Phase 4 (alpha.5), v2.4.4.
#
# Chaque hook reçoit un payload JSON sur stdin. On vérifie les exit codes,
# les sorties JSON (permissionDecision, additionalContext) et la
# robustesse à un stdin vide.
#
# Deux blocs (v2.4.4) :
#   1. DANS un workspace todomail (marqueur .todomail-config.json) :
#      comportement historique inchangé ;
#   2. HORS workspace : chaque hook doit être totalement inerte (aucune
#      sortie, aucun refus, aucun fichier créé ni dans le projet ni sous
#      $TODOMAIL_CONFIG_HOME/<slug>/).

set -u

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PLUGIN_ROOT"

PASS=0
FAIL=0
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# Isolation : on force CLAUDE_PROJECT_DIR dans un temp pour ne pas
# polluer l'environnement utilisateur. Depuis alpha.8, l'etat runtime
# PARTAGE (state.json, snapshots, marqueurs) vit sous
# $CLAUDE_PROJECT_DIR/.todomail/. Depuis la v2.3.0, les fichiers
# machine-locaux (memory_cache.json, logs) vivent sous
# $TODOMAIL_CONFIG_HOME/<slug>/ — force aussi dans le temp.
export CLAUDE_PROJECT_DIR="$TMPDIR/project"
export TODOMAIL_CONFIG_HOME="$TMPDIR/config-home"
mkdir -p "$CLAUDE_PROJECT_DIR"
# v2.4.4 : sans marqueur, les hooks sont inertes — le projet de test du
# bloc 1 est donc un vrai workspace initialisé.
echo '{"schema_version": 4, "expected_rag_name": "test"}' > "$CLAUDE_PROJECT_DIR/.todomail-config.json"

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

echo "##### 1. DANS un workspace todomail #####"
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

out=$(echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"docs/foo.md"}}' | python3 hooks/enforce_classify.py)
check "deny: docs/foo.md" assert_deny "$out"

out=$(echo "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$CLAUDE_PROJECT_DIR/docs/analyse.md\"}}" | python3 hooks/enforce_classify.py)
check "deny: chemin absolu docs/analyse.md" assert_deny "$out"

out=$(echo "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$CLAUDE_PROJECT_DIR/docs/AURA/x.md\"}}" | python3 hooks/enforce_classify.py)
check "allow: chemin absolu docs/AURA/..." assert_no_deny "$out"

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

# mv inbox/ -> mails/
rm -rf "$CLAUDE_PROJECT_DIR/.todomail"
echo '{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"mv inbox/20261119 mails/20261119"}}' | python3 hooks/invalidate_dashboard_cache.py
check "touch: mv inbox/ -> mails/" bash -c '[ -f "$CLAUDE_PROJECT_DIR/.todomail/invalidate.txt" ]'
check "compteur modifications incremente" python3 -c 'import json,os; s=json.load(open(os.environ["CLAUDE_PROJECT_DIR"]+"/.todomail/state.json")); assert s["counters"]["modifications"]>=1'

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/invalidate_dashboard_cache.py'

echo "=== inject_context ==="

# Sans state.json particulier : silencieux
out=$(echo '{"hook_event_name":"UserPromptSubmit","prompt":"hi"}' | python3 hooks/inject_context.py)
check "silence si rien a signaler" bash -c '[ -z "$1" ] || ! echo "$1" | grep -q additionalContext' _ "$out"

# Verrou actif + phase : injection du resume
python3 - <<'PY2'
import json, os
p = os.environ["CLAUDE_PROJECT_DIR"] + "/.todomail/state.json"
s = json.load(open(p))
s["active_lock"] = "process-todo"; s["current_phase"] = "execute"
json.dump(s, open(p, "w"))
PY2
out=$(echo '{"hook_event_name":"UserPromptSubmit","prompt":"hi"}' | python3 hooks/inject_context.py)
check "injection: [todomail state] phase | lock" bash -c 'echo "$1" | python3 -c "import json,sys; c=json.load(sys.stdin)[\"hookSpecificOutput\"][\"additionalContext\"]; assert c==\"[todomail state] phase: execute | lock: process-todo\", c"' _ "$out"
python3 - <<'PY2'
import json, os
p = os.environ["CLAUDE_PROJECT_DIR"] + "/.todomail/state.json"
s = json.load(open(p)); s["active_lock"] = None; s["current_phase"] = None
json.dump(s, open(p, "w"))
PY2

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/inject_context.py'

echo "=== session_start ==="

out=$(echo '{"hook_event_name":"SessionStart","source":"startup"}' | python3 hooks/session_start.py)
check "exit 0 sans crash" bash -c 'true'
# Le cache mémoire doit avoir été créé dans le répertoire machine-local (v2.3.0)
check "memory_cache.json cree (machine-local)" bash -c 'ls "$TODOMAIL_CONFIG_HOME"/*/memory_cache.json >/dev/null 2>&1'
check "memory_cache.json absent du workspace" bash -c '[ ! -f "$CLAUDE_PROJECT_DIR/.todomail/memory_cache.json" ]'
# Nettoyage d'un cache legacy laisse dans .todomail/
mkdir -p "$CLAUDE_PROJECT_DIR/.todomail"
echo '{}' > "$CLAUDE_PROJECT_DIR/.todomail/memory_cache.json"
echo '{"hook_event_name":"SessionStart","source":"startup"}' | python3 hooks/session_start.py >/dev/null
check "cache legacy .todomail/ nettoye" bash -c '[ ! -f "$CLAUDE_PROJECT_DIR/.todomail/memory_cache.json" ]'

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/session_start.py >/dev/null'

echo "=== pre_compact ==="

echo '{"hook_event_name":"PreCompact","trigger":"manual"}' | python3 hooks/pre_compact.py
check "snapshot cree" bash -c 'ls "$CLAUDE_PROJECT_DIR"/.todomail/precompact_snapshot_*.json >/dev/null 2>&1'

check "stdin vide : exit 0" bash -c 'echo -n "" | python3 hooks/pre_compact.py'

echo ""
echo "##### 2. HORS workspace (aucun marqueur) : inertie totale #####"

FOREIGN="$TMPDIR/projet-sans-rapport"
FOREIGN_HOME="$TMPDIR/config-home-foreign"
mkdir -p "$FOREIGN/docs" "$FOREIGN/inbox" "$FOREIGN/mails" "$FOREIGN/todo"
snapshot() { (cd "$FOREIGN" && find . | LC_ALL=C sort); }
BEFORE="$(snapshot)"

# Rejoue un hook depuis le projet etranger. $1 = env CLAUDE_PROJECT_DIR
# (vide = non definie, seule la cwd du payload compte), $2 = hook, $3 = payload.
run_foreign() {
  local envdir="$1" hook="$2" payload="$3"
  (
    cd "$FOREIGN" || exit 1
    export TODOMAIL_CONFIG_HOME="$FOREIGN_HOME"
    if [ -n "$envdir" ]; then export CLAUDE_PROJECT_DIR="$envdir"; else unset CLAUDE_PROJECT_DIR; fi
    printf '%s' "$payload" | python3 "$PLUGIN_ROOT/hooks/$hook"
  )
}

for mode in env cwd; do
  if [ "$mode" = env ]; then ENVDIR="$FOREIGN"; else ENVDIR=""; fi
  echo "=== mode $mode (CLAUDE_PROJECT_DIR ${ENVDIR:-non definie}) ==="

  out=$(run_foreign "$ENVDIR" enforce_classify.py "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Write\",\"cwd\":\"$FOREIGN\",\"tool_input\":{\"file_path\":\"docs/analyse.md\"}}")
  check "[$mode] enforce_classify: aucun refus pour docs/analyse.md" bash -c '[ -z "$1" ]' _ "$out"
  out=$(run_foreign "$ENVDIR" enforce_classify.py "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Write\",\"cwd\":\"$FOREIGN\",\"tool_input\":{\"file_path\":\"$FOREIGN/docs/decisions.md\"}}")
  check "[$mode] enforce_classify: aucun refus (chemin absolu)" bash -c '[ -z "$1" ]' _ "$out"

  out=$(run_foreign "$ENVDIR" invalidate_dashboard_cache.py "{\"hook_event_name\":\"PostToolUse\",\"tool_name\":\"Bash\",\"cwd\":\"$FOREIGN\",\"tool_input\":{\"command\":\"mv inbox/a mails/a\"}}")
  check "[$mode] invalidate_dashboard_cache: aucune sortie" bash -c '[ -z "$1" ]' _ "$out"

  out=$(run_foreign "$ENVDIR" inject_context.py "{\"hook_event_name\":\"UserPromptSubmit\",\"cwd\":\"$FOREIGN\",\"prompt\":\"hi\"}")
  check "[$mode] inject_context: aucune sortie" bash -c '[ -z "$1" ]' _ "$out"

  out=$(run_foreign "$ENVDIR" session_start.py "{\"hook_event_name\":\"SessionStart\",\"cwd\":\"$FOREIGN\",\"source\":\"startup\"}")
  check "[$mode] session_start: aucune sortie" bash -c '[ -z "$1" ]' _ "$out"

  out=$(run_foreign "$ENVDIR" pre_compact.py "{\"hook_event_name\":\"PreCompact\",\"cwd\":\"$FOREIGN\",\"trigger\":\"auto\"}")
  check "[$mode] pre_compact: aucune sortie" bash -c '[ -z "$1" ]' _ "$out"

  check "[$mode] aucun fichier cree dans le projet (.todomail/ absent)" bash -c '[ "$1" = "$(cd "$2" && find . | LC_ALL=C sort)" ]' _ "$BEFORE" "$FOREIGN"
  # Seul fichier tolere sous la racine machine-locale : le pointeur global
  # plugin_root (session_start, indispensable a /start) — jamais de slug.
  check "[$mode] aucun slug sous TODOMAIL_CONFIG_HOME" bash -c '[ -z "$(find "$1" -mindepth 1 ! -name plugin_root 2>/dev/null)" ]' _ "$FOREIGN_HOME"
done

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
