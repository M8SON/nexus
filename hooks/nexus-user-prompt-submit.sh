#!/usr/bin/env bash
# Nexus UserPromptSubmit hook. Prepends mempalace search hits to the user's
# prompt as additional context. Best-effort: any failure produces empty
# injection, never a dropped prompt.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve the wing for this repo. Explicit $NEXUS_WING wins (manual runs and
# tests); otherwise derive it from the project dir via the same resolve_wing()
# that `nexus load` uses, so the hook scopes per repo with no per-repo env
# setup. Dirs outside the workspace resolve to empty — no injection.
WING="${NEXUS_WING:-}"
if [ -z "$WING" ]; then
    NEXUS_PY="$SCRIPT_DIR/../.venv/bin/python"
    [ -x "$NEXUS_PY" ] || NEXUS_PY="$(command -v python3 2>/dev/null || true)"
    if [ -n "$NEXUS_PY" ]; then
        WING="$(PYTHONPATH="$SCRIPT_DIR/.." "$NEXUS_PY" -c '
import sys
from pathlib import Path
from nexus.memory.wings import resolve_wing
print(resolve_wing(Path(sys.argv[1])) or "")
' "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || true)"
    fi
fi
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

# 15s, not 5s: a warm search runs ~3.4s, but a cold one loads the embedder
# model and overruns 5s, silently yielding no injection on a session's first
# prompt. Claude Code's hook budget for this entry is 30s.
HITS="$(timeout 15 "$MEMPALACE_BIN_RESOLVED" search "$PROMPT" --wing "$WING" --results 3 2>>"$LOG" || true)"
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
