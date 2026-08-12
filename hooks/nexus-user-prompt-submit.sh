#!/usr/bin/env bash
# Nexus UserPromptSubmit hook. Prepends mempalace search hits to the user's
# prompt as additional context. Best-effort: any failure produces empty
# injection, never a dropped prompt.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LOG_DIR="$HOME/.cache/nexus"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="$LOG_DIR/user-prompt-hook.log"

# Read the payload from stdin. Claude Code sends UserPromptSubmit as JSON with
# keys: cwd, hook_event_name, permission_mode, prompt, prompt_id, session_id,
# transcript_path. The prompt text is `prompt` — verified against a live
# payload, not assumed. A no-op is silent: empty stdout with exit 0
# adds no context and never blocks the prompt.
PAYLOAD="$(cat)"
PROMPT="$(printf '%s' "$PAYLOAD" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("prompt",""))' 2>/dev/null || true)"
[ -n "$PROMPT" ] || exit 0

# Resolve the wing. Explicit $NEXUS_WING wins (manual runs and tests);
# otherwise derive it from the payload's own `cwd` via the same resolve_wing()
# that `nexus load` uses. Preferring the payload cwd over $CLAUDE_PROJECT_DIR
# means a session launched at the workspace root still scopes to whichever
# repo the work has moved into, instead of pinning to the catch-all wing.
# resolve_wing() collapses any subdirectory to its repo and returns empty
# outside the workspace, in which case there is nothing to inject.
WING="${NEXUS_WING:-}"
if [ -z "$WING" ]; then
    PAYLOAD_CWD="$(printf '%s' "$PAYLOAD" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("cwd","") or "")' 2>/dev/null || true)"
    NEXUS_PY="$SCRIPT_DIR/../.venv/bin/python"
    [ -x "$NEXUS_PY" ] || NEXUS_PY="$(command -v python3 2>/dev/null || true)"
    if [ -n "$NEXUS_PY" ]; then
        WING="$(PYTHONPATH="$SCRIPT_DIR/.." "$NEXUS_PY" -c '
import sys
from pathlib import Path
from nexus.memory.wings import resolve_wing
print(resolve_wing(Path(sys.argv[1])) or "")
' "${PAYLOAD_CWD:-${CLAUDE_PROJECT_DIR:-$PWD}}" 2>/dev/null || true)"
    fi
fi
[ -n "$WING" ] || exit 0

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
    exit 0
fi

# 15s, not 5s: a warm search runs ~3.4s, but a cold one re-reads the 87MB
# ONNX model from disk instead of page cache and overruns 5s, silently
# yielding no injection. Claude Code's hook budget for this entry is 30s.
SEARCH_TIMEOUT=15
set +e
HITS="$(timeout "$SEARCH_TIMEOUT" "$MEMPALACE_BIN_RESOLVED" search "$PROMPT" --wing "$WING" --results 3 2>>"$LOG")"
SEARCH_RC=$?
set -e

# `timeout` reports 124 when it kills the command. Label it so `nexus doctor`
# can distinguish a cold-start overrun from an ordinary empty result.
if [ "$SEARCH_RC" -eq 124 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] search timed out after ${SEARCH_TIMEOUT}s for wing $WING" >> "$LOG"
    exit 0
fi
if [ -z "$HITS" ]; then
    exit 0
fi

# Emit a UserPromptSubmit control object. Hits are passed through the
# environment rather than interpolated into the Python source, so quotes,
# backslashes and `$` in recalled text cannot corrupt the program.
NEXUS_HITS="$HITS" python3 -c "
import json, os
ctx = 'Prior session hits:\n' + os.environ.get('NEXUS_HITS', '')
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'UserPromptSubmit',
        'additionalContext': ctx,
    }
}))
" 2>>"$LOG" || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] injected ${#HITS} chars for wing $WING" >> "$LOG"
