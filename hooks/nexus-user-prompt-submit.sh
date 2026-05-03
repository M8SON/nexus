#!/usr/bin/env bash
# Nexus UserPromptSubmit hook. Prepends mempalace search hits to the user's
# prompt as additional context. Best-effort: any failure produces empty
# injection, never a dropped prompt.

set -e

WING="${NEXUS_WING:-}"
[ -n "$WING" ] || exit 0

# Read the prompt from stdin (Claude Code passes it as JSON).
PAYLOAD="$(cat)"
PROMPT="$(printf '%s' "$PAYLOAD" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("user_prompt",""))' 2>/dev/null || true)"
[ -n "$PROMPT" ] || { printf '%s' "$PAYLOAD"; exit 0; }

LOG_DIR="$HOME/.cache/nexus"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="$LOG_DIR/user-prompt-hook.log"

# Resolve the mempalace binary. Claude Code may launch hooks with a stripped
# PATH that omits the nexus venv's bin/, so falling back to the venv adjacent
# to this script is the reliable path. Resolution order:
#   1. $MEMPALACE_BIN  (explicit override)
#   2. <script>/../.venv/bin/mempalace  (sibling venv of this hook script)
#   3. command -v mempalace  (last-resort PATH lookup)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMPALACE_BIN_RESOLVED="${MEMPALACE_BIN:-}"
if [ -z "$MEMPALACE_BIN_RESOLVED" ] || [ ! -x "$MEMPALACE_BIN_RESOLVED" ]; then
    if [ -x "$SCRIPT_DIR/../.venv/bin/mempalace" ]; then
        MEMPALACE_BIN_RESOLVED="$SCRIPT_DIR/../.venv/bin/mempalace"
    else
        MEMPALACE_BIN_RESOLVED="$(command -v mempalace 2>/dev/null || true)"
    fi
fi
if [ -z "$MEMPALACE_BIN_RESOLVED" ] || [ ! -x "$MEMPALACE_BIN_RESOLVED" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] mempalace binary not found (set MEMPALACE_BIN to override)" >> "$LOG"
    printf '%s' "$PAYLOAD"
    exit 0
fi

HITS="$(timeout 5 "$MEMPALACE_BIN_RESOLVED" search "$PROMPT" --wing "$WING" --results 3 2>>"$LOG" || true)"
if [ -z "$HITS" ]; then
    printf '%s' "$PAYLOAD"
    exit 0
fi

# Append hits as additional context. Claude Code's UserPromptSubmit hook
# expects the JSON payload back on stdout with optional `additional_context`.
printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
data = json.load(sys.stdin)
data['additional_context'] = '''Prior session hits:
$HITS'''
print(json.dumps(data))
" 2>>"$LOG" || printf '%s' "$PAYLOAD"
