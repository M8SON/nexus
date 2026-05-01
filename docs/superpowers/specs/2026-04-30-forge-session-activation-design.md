# Forge Session Activation

**Status:** Spec
**Date:** 2026-04-30
**Owner:** Mason Misch

## Problem

Forge phase 1 shipped 2026-04-26 (BM25 session recall + local-doc discovery
+ shared policies + thin Claude/Codex adapters). The CLI works and the
adapter file at `forge/adapters/claude/CLAUDE.md` exists, but **forge is
not actually wired into any Claude Code session**. There's no top-level
`CLAUDE.md` referencing the adapter and no hook that runs `forge context`
at session start. So the policies aren't loaded, and recall stays manual.

This spec wires forge into Claude Code sessions under `~/linux/` so it
delivers what the original forge spec promised: automatic policy
inclusion + automatic local-doc surfacing.

Active session recall (BM25 hits derived from a query) is explicitly
deferred to phase 2 — this spec covers only the activation seam, not
proactive recall.

## Goal

After this lands:

1. Any Claude Code session whose `CLAUDE_PROJECT_DIR` is under
   `/home/daedalus/linux/` automatically loads forge's policy chain
   (`core.md` Karpathy baseline + `continuity.md`) via the adapter file.
2. Local-doc snippets from the working repo (`WORKING_MEMORY.md`,
   `CLAUDE.md`, `AGENTS.md`, `README.md`, plus recursive
   `docs/superpowers/specs/` and `docs/superpowers/plans/`) are injected
   into the session at start as a SessionStart hook.
3. Sessions outside `~/linux/` are unaffected — silent no-op.
4. Failure of the hook for any reason is non-fatal — Claude Code starts
   normally.

## Non-Goals

- Mid-session proactive recall (phase 2).
- Slash commands or user-invokable forge commands inside the session.
- Token-budget telemetry / context-pressure warnings (phase 2).
- Activation outside `~/linux/`.
- Repo/cwd filter on the recall query layer (separate spec).

## Decisions

- **Static policy entry point:** a single new file at
  `~/linux/CLAUDE.md` that points at the existing forge adapter file.
  Claude Code's CLAUDE.md ancestor-walk picks it up for any session whose
  cwd is `~/linux/` or any descendant.
- **No `@path` include in the CLAUDE.md** — Claude Code's include
  semantics are version-dependent and brittle. The CLAUDE.md uses plain
  text instructing the agent to read the adapter file.
- **Adapter file stays canonical.** The CLAUDE.md is a thin pointer; the
  adapter is the single source of truth for what policies apply.
- **Dynamic injection mechanism:** a SessionStart hook registered in
  `~/.claude/settings.json` that runs a small shell wrapper at
  `~/.claude/hooks/forge-session-start.sh`. The wrapper invokes
  `python -m forge.cli context --repo-path "$CLAUDE_PROJECT_DIR"` and
  prints stdout. Claude Code wraps stdout as additional session context.
- **No-op outside `~/linux/`:** the wrapper inspects `$CLAUDE_PROJECT_DIR`
  (falling back to `$PWD`) and exits 0 silently if it's outside the
  managed workspace.
- **Phase-1 recall behavior:** `forge context` is invoked with no `query`
  argument, so the CLI returns only local-doc snippets (no BM25 session
  hits). Phase 2 will add a proactive recall query.
- **Failure path is silent.** All errors swallowed via
  `2>/dev/null || exit 0`. Forge is invisible when it can't help; it
  never blocks or breaks a session.

## Architecture

### Component map

```
~/linux/CLAUDE.md                              ← static policy pointer
                  │
                  └─→ /home/daedalus/linux/forge/forge/adapters/claude/CLAUDE.md
                                       │
                                       ├─→ ../../policies/core.md     (Karpathy baseline)
                                       └─→ ../../policies/continuity.md

~/.claude/settings.json
   "hooks": { "SessionStart": [...forge-session-start.sh...] }
                                          │
                                          ├─ checks $CLAUDE_PROJECT_DIR is under ~/linux/
                                          ├─ runs `python -m forge.cli context --repo-path ...`
                                          └─ prints stdout (doc snippets) → injected as session context
```

### Static policy entry point

File: `~/linux/CLAUDE.md` (new). Plain markdown. Not in any git repo —
this is the workspace-root file that Claude Code reads before entering
any sub-repo's own CLAUDE.md.

Content:

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

### SessionStart hook script

File: `~/.claude/hooks/forge-session-start.sh` (new, mode `0755`).

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

Notes:

- Uses forge's own venv (`$FORGE_DIR/.venv/bin/python`) so the script
  doesn't depend on the calling shell's Python environment.
- `2>/dev/null || exit 0` ensures stderr from `forge.cli` doesn't leak
  into the session and any non-zero exit is treated as a no-op.
- The `case` matcher on `$PROJECT_DIR` enforces the activation scope at
  the hook layer, not in the CLI. This means the CLI is unchanged.

### Settings registration

File: `~/.claude/settings.json` — add a `hooks.SessionStart` entry to the
existing object. The exact schema is verified against the running Claude
Code version before commit (the harness exposes hook config via the
`update-config` skill).

Expected shape:

```json
{
  "model": "opus",
  "enabledPlugins": { ... },
  "effortLevel": "high",
  "hooks": {
    "SessionStart": [
      {
        "command": "/home/daedalus/.claude/hooks/forge-session-start.sh"
      }
    ]
  }
}
```

If the schema turns out to differ (e.g. requires a `matcher` field or a
different array key), the implementation step adapts to the actual
schema. The behavioral contract — "run this script at SessionStart and
inject its stdout" — does not change.

## Data flow

1. User runs `claude` in some directory.
2. Claude Code reads `~/linux/CLAUDE.md` (if cwd is under `~/linux/`)
   and any closer ancestor CLAUDE.md files.
3. Claude Code dispatches the SessionStart hook.
4. Hook script checks `$CLAUDE_PROJECT_DIR`. Outside `~/linux/`: exit 0.
5. Inside: hook runs `python -m forge.cli context --repo-path
   "$CLAUDE_PROJECT_DIR"`. Output is doc snippets (one line per
   discovered doc).
6. Claude Code wraps the stdout as additional session context.
7. Agent now has: workspace CLAUDE.md instructions → adapter →
   policies (`core.md` + `continuity.md`), plus per-repo doc snippets.

## What gets injected (concrete example)

For a session starting in `~/linux/miniclaw`:

```
WORKING_MEMORY.md: # MiniClaw Working Memory
CLAUDE.md: # CLAUDE.md
README.md: # MiniClaw — modular voice assistant for Raspberry Pi
2026-04-30-elevator-music-design.md: # Elevator Music During the Wait
2026-04-30-elevator-music.md: # Elevator Music Implementation Plan
... (more discovered docs)
```

Total: a few hundred tokens at most.

## Error handling

| Failure                                        | Behavior                                              |
|------------------------------------------------|-------------------------------------------------------|
| `~/linux/CLAUDE.md` missing                    | Claude Code starts normally; no policy injection.     |
| Adapter file missing or moved                  | Agent reads the CLAUDE.md instruction, attempts to read the adapter, fails gracefully — work proceeds without forge policies. |
| Forge venv missing                             | Hook exits 0 silently. No injection.                  |
| `forge.cli` raises                             | `2>/dev/null || exit 0` swallows. No injection.       |
| `$CLAUDE_PROJECT_DIR` outside `~/linux/`       | Hook exits 0 silently. No injection.                  |
| Hook itself errors before the case-matcher     | `set -e` would exit non-zero, but Claude Code treats failed SessionStart hooks as non-fatal. Session starts normally. |

The principle: **forge is invisible when it can't help.** It never
blocks or breaks a session.

## Testing

- Unit: nothing in this spec adds new code paths to forge itself; the
  hook is a thin shell wrapper around an existing CLI subcommand.
  `tests/test_context.py` and `tests/test_cli.py` already cover
  `forge context` behavior.
- Manual validation, three cases:
  1. Start `claude` in `~/linux/forge` → expect a SessionStart context
     block containing forge's own docs (e.g. forge `README.md`,
     `WORKING_MEMORY.md`, the design and plan files under
     `docs/superpowers/`).
  2. Start `claude` in `~/linux/miniclaw` → expect MiniClaw's docs in
     the SessionStart block.
  3. Start `claude` in `~` (outside `~/linux/`) → expect no SessionStart
     forge block; only the prior `~/.claude/settings.json` behavior.

## Out of Scope

- Phase 2 proactive recall (separate spec).
- Repo/cwd filter on `forge.query` (separate spec).
- Slash commands and ad-hoc mid-session forge invocations.
- Symlinking the CLAUDE.md to the adapter file (`@path` include
  alternatives) — explicitly rejected for portability.
- Activation under arbitrary `WORKSPACE_ROOT` other than `~/linux/`
  (forge's spec has the workspace root configurable; the hook hardcodes
  it for this phase, matching how forge itself is currently used).
