# Forge Session Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire forge into Claude Code sessions under `~/linux/` so policies load automatically and local-doc snippets are injected at session start.

**Architecture:** A workspace-root `CLAUDE.md` at `~/linux/CLAUDE.md` points at forge's adapter file (which already references `core.md` + `continuity.md`). A SessionStart hook script at `~/.claude/hooks/forge-session-start.sh` runs `forge.cli context --repo-path "$CLAUDE_PROJECT_DIR"` and prints stdout, which Claude Code injects as additional session context. The hook is registered in `~/.claude/settings.json` under `hooks.SessionStart` with the `"startup"` matcher. The script is a silent no-op outside `~/linux/` and on any error.

**Tech Stack:** bash, JSON edit, plain markdown. No new code in the forge package itself.

**Spec:** `docs/superpowers/specs/2026-04-30-forge-session-activation-design.md`

---

## File Structure

- **new:** `~/linux/CLAUDE.md` — workspace policy pointer (plain markdown).
- **new:** `~/.claude/hooks/forge-session-start.sh` — SessionStart hook wrapper (executable bash).
- **edit:** `~/.claude/settings.json` — add `hooks.SessionStart` entry that calls the wrapper.

No changes to the forge Python package. No new tests in `forge/tests/` — the existing `test_cli.py` and `test_context.py` already cover the CLI subcommand the hook calls.

The validation is manual: start three real Claude Code sessions (one inside `~/linux/forge`, one inside `~/linux/miniclaw`, one outside `~/linux/`) and confirm the hook fires correctly in each case.

---

## Task 1: Workspace CLAUDE.md

**Files:**
- Create: `/home/daedalus/linux/CLAUDE.md`

- [ ] **Step 1: Write the file**

```markdown
# Forge-managed workspace

You are working in a Forge-managed workspace. Forge is a local-first
shared assistant framework that provides session recall, local-doc
recall, and shared agent policies for repos under /home/daedalus/linux.

Read /home/daedalus/linux/forge/forge/adapters/claude/CLAUDE.md and
apply the policies it references — the Karpathy core baseline
(core.md) and the continuity policy (continuity.md) — for any
non-trivial work.

Forge's CLI: `python -m forge.cli {recall,context,index,stats,doctor}`
from /home/daedalus/linux/forge (its venv is at .venv there).
```

- [ ] **Step 2: Confirm it lives where Claude Code's ancestor walk will find it**

```bash
test -f /home/daedalus/linux/CLAUDE.md && echo "present" || echo "missing"
```

Expected: `present`.

- [ ] **Step 3: No commit**

This file lives in the workspace root, not inside any tracked git repo. There is no repo at `~/linux/` itself. Skip the git step for this task.

---

## Task 2: SessionStart hook script

**Files:**
- Create: `/home/daedalus/.claude/hooks/forge-session-start.sh` (mode `0755`)

- [ ] **Step 1: Ensure the hooks directory exists**

```bash
mkdir -p /home/daedalus/.claude/hooks
```

- [ ] **Step 2: Write the script**

`/home/daedalus/.claude/hooks/forge-session-start.sh`:

```bash
#!/usr/bin/env bash
# Forge SessionStart hook. Injects local-doc snippets (and, in phase 2,
# prior-session recall hits) into Claude Code sessions starting under
# /home/daedalus/linux. Silent no-op outside that scope or on any error.

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"

case "$PROJECT_DIR" in
  /home/daedalus/linux/*|/home/daedalus/linux) ;;
  *) exit 0 ;;
esac

FORGE_DIR="/home/daedalus/linux/forge"
[ -d "$FORGE_DIR" ] || exit 0
[ -x "$FORGE_DIR/.venv/bin/python" ] || exit 0

# Fire-and-forget; never block session start.
"$FORGE_DIR/.venv/bin/python" -m forge.cli context \
    --repo-path "$PROJECT_DIR" 2>/dev/null || exit 0
```

- [ ] **Step 3: Make it executable**

```bash
chmod 0755 /home/daedalus/.claude/hooks/forge-session-start.sh
```

- [ ] **Step 4: Smoke-test the script directly with a real project dir**

```bash
CLAUDE_PROJECT_DIR=/home/daedalus/linux/forge \
    /home/daedalus/.claude/hooks/forge-session-start.sh
```

Expected: a multi-line `Project docs:` block listing forge's own docs (e.g. `WORKING_MEMORY.md`, `README.md`, the spec/plan files under `docs/superpowers/`). Exit code `0`.

- [ ] **Step 5: Smoke-test the script with a project dir outside ~/linux**

```bash
CLAUDE_PROJECT_DIR=/tmp \
    /home/daedalus/.claude/hooks/forge-session-start.sh
echo "exit=$?"
```

Expected: no stdout output, `exit=0`. The case-matcher should silently skip outside-`~/linux/` paths.

- [ ] **Step 6: Smoke-test with no `CLAUDE_PROJECT_DIR` set**

```bash
( cd /home/daedalus/linux/forge && unset CLAUDE_PROJECT_DIR && \
    /home/daedalus/.claude/hooks/forge-session-start.sh )
```

Expected: same multi-line `Project docs:` block as Step 4 (the `${CLAUDE_PROJECT_DIR:-$PWD}` fallback works when the env var isn't set).

- [ ] **Step 7: Smoke-test the failure path (forge venv missing)**

```bash
( CLAUDE_PROJECT_DIR=/home/daedalus/linux/forge \
    PATH=/usr/bin:/bin \
    bash -c 'FORGE_BACKUP=/home/daedalus/linux/forge/.venv && \
             mv "$FORGE_BACKUP" "${FORGE_BACKUP}.tmp" && \
             /home/daedalus/.claude/hooks/forge-session-start.sh; \
             rc=$?; \
             mv "${FORGE_BACKUP}.tmp" "$FORGE_BACKUP"; \
             echo "exit=$rc"' )
```

Expected: no stdout, `exit=0`. Confirms the `[ -x "$FORGE_DIR/.venv/bin/python" ] || exit 0` guard.

If you'd rather not move-and-restore the venv, this step can be skipped — the guard is straightforward to read.

- [ ] **Step 8: No commit**

This file lives in `~/.claude/`, not inside any tracked git repo. Skip the git step.

---

## Task 3: Register the hook in settings.json

**Files:**
- Modify: `/home/daedalus/.claude/settings.json`

- [ ] **Step 1: Read current settings**

```bash
cat /home/daedalus/.claude/settings.json
```

Expected (current, exactly):

```json
{
  "model": "opus",
  "enabledPlugins": {
    "code-review@claude-plugins-official": true,
    "code-simplifier@claude-plugins-official": true,
    "superpowers@claude-plugins-official": true
  },
  "effortLevel": "high"
}
```

If the file already has a `hooks` key, merge the new `SessionStart` entry into it instead of replacing.

- [ ] **Step 2: Write the new settings.json**

Use the `update-config` skill if available; otherwise write directly:

```json
{
  "model": "opus",
  "enabledPlugins": {
    "code-review@claude-plugins-official": true,
    "code-simplifier@claude-plugins-official": true,
    "superpowers@claude-plugins-official": true
  },
  "effortLevel": "high",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "/home/daedalus/.claude/hooks/forge-session-start.sh"
          }
        ]
      }
    ]
  }
}
```

The `"startup"` matcher fires only on fresh session start (not on `resume`, `clear`, or `compact`). This keeps token cost predictable: forge context is injected once per real session, not on every `/clear`.

- [ ] **Step 3: Validate JSON**

```bash
python3 -c "import json,sys; json.load(open('/home/daedalus/.claude/settings.json'))" \
    && echo "json ok" || echo "json BROKEN"
```

Expected: `json ok`. If the JSON is broken, Claude Code may fail to start with the new settings — fix before proceeding.

- [ ] **Step 4: No commit**

`~/.claude/settings.json` lives outside any tracked repo. No git step.

---

## Task 4: End-to-end manual validation

**Files:** none (operational task).

This task confirms the wiring works in real Claude Code sessions. It must be run by the user, not by an agent.

- [ ] **Step 1: Start a fresh Claude Code session inside `~/linux/forge`**

In a terminal:

```bash
cd /home/daedalus/linux/forge && claude
```

Expected: when the session opens, the conversation transcript should show a SessionStart hook context block containing `Project docs:` with one line per discovered doc (forge's `README.md`, `WORKING_MEMORY.md`, the spec and plan markdown files under `docs/superpowers/`, etc.). The agent should also note that it's working in a forge-managed workspace (because `~/linux/CLAUDE.md` was loaded via the ancestor walk).

If the SessionStart block is missing: check `~/.claude/settings.json` was saved correctly and the hook script is executable.

- [ ] **Step 2: Start a fresh Claude Code session inside `~/linux/miniclaw`**

```bash
cd /home/daedalus/linux/miniclaw && claude
```

Expected: SessionStart block listing miniclaw's docs (`README.md`, `WORKING_MEMORY.md`, `CLAUDE.md`, the various 2026-04-* specs and plans in `docs/superpowers/`). Confirms the `--repo-path` derivation from `$CLAUDE_PROJECT_DIR` works.

- [ ] **Step 3: Start a fresh Claude Code session OUTSIDE `~/linux/`**

```bash
cd /tmp && claude
```

Expected: NO forge SessionStart block. The agent should behave exactly as it did before this work landed.

- [ ] **Step 4: Confirm the workspace CLAUDE.md was picked up**

In the session from Step 1 or Step 2, ask the agent: *"What policies are you applying for this work?"*

Expected: the agent should mention the Karpathy core baseline and the continuity policy (or at least confirm it's working under forge). This proves the ancestor walk found `~/linux/CLAUDE.md`, which led the agent to read the adapter file, which referenced both policies.

- [ ] **Step 5: No commit**

Validation produces signals, not code.

---

## Self-Review

**Spec coverage:**

| Spec section                                                        | Task     |
|---------------------------------------------------------------------|----------|
| Static policy entry point at `~/linux/CLAUDE.md`                    | 1        |
| Adapter file remains canonical (CLAUDE.md is a thin pointer)        | 1 (content references the adapter, no inlining) |
| SessionStart hook script at `~/.claude/hooks/forge-session-start.sh`| 2        |
| Hook uses `forge.cli context --repo-path "$CLAUDE_PROJECT_DIR"`     | 2 (Step 2) |
| No-op outside `~/linux/`                                            | 2 (Step 5 smoke-tests it) |
| Failure-silent path (`2>/dev/null \|\| exit 0`)                     | 2 (Step 7 smoke-tests it) |
| Settings registration in `~/.claude/settings.json`                  | 3        |
| Hook matcher: `"startup"` only (not `resume`/`clear`/`compact`)     | 3 (Step 2) |
| Validation case 1: session in `~/linux/forge`                       | 4 (Step 1) |
| Validation case 2: session in `~/linux/miniclaw`                    | 4 (Step 2) |
| Validation case 3: session outside `~/linux/`                       | 4 (Step 3) |
| Phase-2 recall (active query-based)                                 | explicitly out of scope; not implemented |

**Placeholder scan:** every code-changing step contains the actual content. The settings.json edit shows the exact final-state JSON, including the existing keys, so an engineer who reads only Task 3 can produce a valid file.

**Type / signature consistency:** No types or method signatures in this plan — it's all configuration files and shell. The single cross-reference is the path `/home/daedalus/.claude/hooks/forge-session-start.sh`, which appears identically in Tasks 2 and 3.

**One known unknown:** the matcher value `"startup"` is from the documented Claude Code schema but if a future Claude Code version changes the schema, Task 3 will need adapting. The plan does not pin a version. This is acceptable — the spec already documents that the schema may differ and the implementation should adapt.
