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

HITS="$(timeout 5 mempalace search "$PROMPT" --wing "$WING" --results 3 2>>"$LOG" || true)"
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
