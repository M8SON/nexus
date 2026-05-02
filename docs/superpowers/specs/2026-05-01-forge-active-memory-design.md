# Forge Active Memory (Phase 2)

Date: 2026-05-01
Status: Draft for review

## Overview

Phase 2 of forge wires MemPalace into both supported agents (Claude Code
and Codex CLI) under `~/linux/`, replacing forge's existing BM25/SQLite
recall engine. Forge becomes a nexus: a small framework that distributes
shared philosophy (markdown policies) and shared memory (a per-repo wing
in a single local MemPalace palace), with thin agent-specific adapters.

This is the "active memory" portion of the original phase-2 scope. Token
telemetry has been dropped from this round; if active recall and active
saving work as intended, context-pressure becomes a smaller problem on
its own.

## Goals

- Give every agent under `~/linux/` access to the same local memory
  store, isolated by repo.
- Make recall happen automatically at session start and at prompt time
  (where the agent harness allows), not only when the agent thinks to
  ask.
- Make saving happen automatically at message intervals and before
  context compaction, not only at session end.
- Keep all storage local, with no daemons, ports, or network calls.
- Keep forge's existing role as the philosophy/policy distributor; phase
  2 adds memory orchestration alongside it.
- Reduce forge's surface area by retiring the BM25 layer.

## Non-Goals

- Cross-machine sync of the palace.
- Token-budget telemetry, warnings, or compaction tooling — explicitly
  deferred.
- Reimplementing MemPalace functionality inside forge.
- Wiring agents outside `~/linux/`.
- Closing the Codex/Claude prompt-injection asymmetry (deferred until
  Codex CLI ships an equivalent hook).

## Scope

In scope:

- A `forge.memory` subpackage with three small modules: `wings`, `env`,
  `install`.
- Three new CLI subcommands: `forge memory init`, `forge memory status`,
  and a rewritten `forge context`.
- Storage redirection so MemPalace's bulk data lives at
  `/home/daedalus/linux/forge/data/`.
- Hook wiring for Claude Code (`SessionStart`, `UserPromptSubmit`,
  `Stop`, `PreCompact`) and Codex CLI (`Stop`, `PreCompact`).
- A rewrite of `forge/policies/continuity.md` with concrete recall and
  save triggers.
- A one-time backfill of `~/.claude/projects/` and `~/.codex/sessions/`
  into the appropriate wings.
- Removal of the BM25 layer: `forge/db.py`, `forge/query.py`,
  `forge/indexer.py`, the `recall`/`index`/`stats` CLI subcommands,
  `tests/test_query.py`, `tests/test_indexer.py`, the
  `~/.claude/tools/forge/forge.db` data file, and any references in
  `forge/cli.py`.

Out of scope (this phase):

- Token telemetry, deferred to a later phase if still wanted.
- A new philosophy file specific to Codex.
- A `/recall` slash skill for Codex (rejected as unnecessary; tool
  surface plus policy is sufficient).
- Cross-machine palace sync.

## Architecture

```
~/linux/forge/
├── forge/
│   ├── policies/                 # philosophy (existing; continuity.md rewritten)
│   │   ├── core.md
│   │   └── continuity.md
│   ├── adapters/                 # thin agent entrypoints (existing, unchanged)
│   │   ├── claude/CLAUDE.md
│   │   └── codex/AGENTS.md
│   ├── memory/                   # NEW: MemPalace orchestration
│   │   ├── wings.py              # cwd → wing-name resolver
│   │   ├── env.py                # env-var assembly for MemPalace
│   │   └── install.py            # `forge memory init` implementation
│   └── cli.py                    # gains `memory` subcommand; recall/index/stats removed
├── data/                         # NEW: gitignored MemPalace storage
│   ├── palace/                   # ChromaDB drawers + closets collections
│   └── hook_state/               # save-hook counters and log
└── (forge/db.py, query.py, indexer.py REMOVED)
```

Storage redirection via env vars set at hook invocation time:

- `MEMPALACE_PALACE_PATH=/home/daedalus/linux/forge/data/palace`
- `STATE_DIR=/home/daedalus/linux/forge/data/hook_state`
- `MEMPAL_DIR=<repo-root>` so the save hook also mines the active repo's
  files on every save trigger.

MemPalace's small tool-config files (`~/.mempalace/config.json`,
`~/.mempalace/knowledge_graph.db`) stay at their default paths because
MemPalace does not currently expose env-overrides for the config dir.
They are metadata, not bulk data, so this is acceptable.

`data/` is gitignored. ChromaDB stores binary blobs and verbatim
conversation drawers; neither belongs in git.

## Wing Convention

`forge.memory.wings.resolve_wing(cwd: Path) -> str | None` returns the
wing name for a given directory, using the same managed-repo predicate
as `ForgeConfig.is_managed_repo`:

- If `cwd` is `/home/daedalus/linux/<repo>/...`, wing = `<repo>`
  (e.g., `forge`, `miniclaw`).
- If `cwd` is `/home/daedalus/linux/` itself, wing = `workspace`.
- Otherwise, wing = `None`. The install refuses to run; SessionStart
  hook silently no-ops; UserPromptSubmit hook silently no-ops.

Wing names are normalized via `mempalace.config.normalize_wing_name()`
(lower-case, `-`/space → `_`) so MemPalace's own filename and ChromaDB
metadata rules are honored.

## Components

### `forge.memory.wings`

Single function: `resolve_wing(cwd: Path) -> str | None`. Pure, no I/O
beyond `Path.resolve()`. Reuses the existing workspace-root config.

### `forge.memory.env`

Single function: `mempalace_env(wing: str, repo_root: Path) -> dict[str, str]`.
Returns the env block to pass when shelling out to MemPalace:

- `MEMPALACE_PALACE_PATH`
- `STATE_DIR`
- `MEMPAL_DIR`

### `forge.memory.install`

`forge memory init [--repo <path>] [--skip-backfill]`:

1. Resolve the wing for `--repo` (default `cwd`). Refuse with a clear
   message if the wing is `None`.
2. Create `~/linux/forge/data/{palace,hook_state}/` if missing.
3. Idempotently merge hook entries into `~/.claude/settings.json`:
   - Keep the existing `SessionStart` entry pointing at
     `forge-session-start.sh` (the hook script doesn't change shape).
   - Add `UserPromptSubmit` → `forge-user-prompt-submit.sh` (new, ships
     with forge).
   - Add `Stop` → MemPalace's `mempal_save_hook.sh`.
   - Add `PreCompact` → MemPalace's `mempal_precompact_hook.sh`.
4. Idempotently write `~/.codex/hooks.json` with `Stop` and `PreCompact`
   entries pointing at the same MemPalace hook scripts.
5. Write a `.bak` of any settings file before mutation; restore on any
   merge failure.
6. If a backfill marker for this wing is missing under
   `data/.backfill-markers/<wing>` and `--skip-backfill` is not set, run:
   - `mempalace mine ~/.claude/projects/ --mode convos --wing <wing>`
   - `mempalace mine ~/.codex/sessions/ --mode convos --wing <wing>`
   then write the marker. Backfill failure does not roll back the rest
   of the install; the user can re-run.
7. Print a short summary of what was added and what was skipped.

### `forge memory status`

Best-effort, independent checks; reports each:

- Palace path, exists, size on disk.
- Current wing (resolved from cwd) and drawer count for that wing.
- Last save timestamp from `data/hook_state/hook.log`.
- Hook installation state for Claude Code and Codex.
- `mempalace` CLI on PATH and importable.

Never fails the process; missing components produce diagnostic lines,
not exit codes.

### `forge context` (rewritten)

Replaces the BM25 query with `mempalace wake-up --wing <wing>`. Output
shape is unchanged from today's `Project docs:` / `Prior session
context:` blocks, so no caller code changes.

- Resolve wing. If `None`, emit local-doc block only (current behavior
  outside `~/linux/` already silent-no-ops upstream).
- Run `mempalace wake-up --wing <wing>` with a 10-second wall-clock cap
  in a subprocess. On timeout, kill and fall through.
- Run `discover_context_docs(repo_path)` (unchanged).
- Merge into the existing two-block format and print.

### `forge doctor` (extended)

Adds checks to the existing list:

- `palace path exists`
- `wing has at least one drawer` (warning only, not failure — fresh
  wings legitimately have zero)
- `mempalace on PATH`
- `claude hooks installed`, `codex hooks installed`

### Hook scripts

Three forge-owned scripts under `~/.claude/hooks/`:

- `forge-session-start.sh` — already exists; no body change beyond what
  the rewritten `forge context` produces.
- `forge-user-prompt-submit.sh` — new; reads the prompt from
  `$CLAUDE_USER_PROMPT`, runs `mempalace search "$prompt" --wing $wing
  --limit 3` with a 5-second cap, prepends the result as additional
  context. Failures produce empty injection, never a dropped prompt.

The Stop and PreCompact hooks point directly at MemPalace's shipped
scripts; forge does not wrap them.

### Policy rewrite: `forge/policies/continuity.md`

Expand from the current three-bullet stub into concrete triggers, in
the same Karpathy-style imperative voice as `core.md`:

- When to call `mempalace_wake_up` at session start (and what to do
  with the output).
- When to call `mempalace_search` mid-task: user references prior work,
  about to make a design decision, the task looks like a continuation,
  you are stuck or repeating yourself.
- When to save: durable facts (decisions, constraints, user
  preferences) vs ephemeral state (what files were just edited).
- Wing scoping: always pass the active repo's wing unless explicitly
  searching across.

This file is read by both Claude Code (via the Claude adapter) and
Codex (via the Codex adapter). One file covers both agents.

## Data Flow

Typical Claude Code session in `~/linux/forge`:

```
session opens
   ↓
SessionStart hook → forge context --repo-path .
   ↓
   resolve_wing("/home/daedalus/linux/forge") → "forge"
   discover_context_docs(repo)        → 6 doc snippets
   mempalace wake-up --wing forge      → top-K drawers
   ↓
   merged output injected into session context

user types a message
   ↓
UserPromptSubmit hook → forge-user-prompt-submit.sh
   ↓
   mempalace search "<prompt>" --wing forge --limit 3
   ↓
   hits prepended to prompt; agent sees enriched prompt

agent works; calls MCP tools when judgment + policy say to
   ↓
   mempalace_search / mempalace_wake_up scoped to wing

every 15 messages → Stop hook → mempal_save_hook.sh
   ↓
   mempalace mine $TRANSCRIPT --mode convos --wing forge
   block AI to save key topics/decisions/quotes

near context limit → PreCompact hook → mempal_precompact_hook.sh
   ↓
   mempalace mine $TRANSCRIPT --mode convos --wing forge
   block AI for emergency save
```

Codex session in the same directory uses the same wiring minus the
SessionStart and UserPromptSubmit hooks. The agent reaches for
memory via tool calls per the philosophy in `continuity.md`. Save and
PreCompact hooks operate identically.

### MCP wing scoping

MemPalace's MCP server is launched per session by the agent. To ensure
tool calls scope to the active wing without the agent having to pass
`wing=` every call, the `.mcp.json` blocks (Claude and Codex plugins)
should set `MEMPALACE_DEFAULT_WING=<wing>` in the server's environment.
This requires runtime resolution of the wing per session, which the
forge install helper handles by writing per-repo `.mcp.json` files in
each managed repo (or the agent's project-scoped config). If MemPalace
does not honor `MEMPALACE_DEFAULT_WING`, the install adds a thin
wrapper script that injects `--wing` into stdio messages. Confirmation
of MemPalace's behavior here is a planning-stage check.

## Error Handling

SessionStart hook (`forge context`):

- MemPalace not on PATH → log to
  `~/.cache/forge/session-start-hook.log`, emit only the doc block.
- Palace not initialized for this wing → emit doc block plus a single
  diagnostic line: `Prior session context: (palace not initialized for
  wing '<name>'; run forge memory init)`.
- `mempalace wake-up` non-zero or > 10 s → kill, log, doc-only output.
- The hook never blocks session start. Existing `|| exit 0` discipline
  preserved.

UserPromptSubmit hook:

- On any failure the original prompt must reach the agent unmodified.
  Wrapper exits 0 with empty injection; the agent never sees a missing
  prompt.
- 5-second wall-clock cap on the search call.

Save / PreCompact hooks: MemPalace owns failure handling. Forge does
not wrap.

`forge memory init`:

- Settings.json mutations are read-modify-write with `.bak` first;
  restore on merge failure.
- Refuses if cwd resolves to wing `None`.
- Backfill is best-effort; failure does not undo the hook installation.
  The marker is written only on success, so re-running retries
  backfill.

`forge memory status`:

- Best-effort; each check independent. Always exits 0 unless invoked
  with `--strict`.

## Testing

Keep, modify:

- `tests/test_config.py` — workspace activation predicate, unchanged.
- `tests/test_doc_recall.py` — local-doc discovery, unchanged.
- `tests/test_context.py` — rewrite to mock `mempalace wake-up` output
  rather than BM25 hits.
- `tests/test_cli.py` — drop `recall`/`index`/`stats` cases; add
  `memory init` and `memory status` cases.

Add:

- `tests/test_wings.py` — table-driven `cwd → wing` cases: managed repo,
  workspace root, outside, nested subpath, symlinks resolving back into
  the workspace.
- `tests/test_install.py` — install idempotency: run twice, assert
  `~/.claude/settings.json` ends up with one entry per hook type, not
  duplicates; backup written; backfill marker behavior; refuses outside
  workspace.
- `tests/test_smoke.py` — end-to-end against a real (small) palace at
  `tmp_path`, mine a fixture transcript, assert `mempalace wake-up
  --wing test` returns drawer text. Marked `slow`; skipped if
  `mempalace` is not importable.

Delete:

- `tests/test_query.py`
- `tests/test_indexer.py`

Manual validation gate (post-implementation):

- Fresh Claude Code session in `~/linux/forge` produces both
  `Project docs:` and `Prior session context:` blocks.
- A prompt referencing prior work shows MemPalace hits injected by the
  UserPromptSubmit hook.
- Reaching 15 messages fires the Save hook (verify via
  `data/hook_state/hook.log` and palace drawer count).
- Same checks in `~/linux/miniclaw` confirm wing isolation.
- Codex session: Save and PreCompact hooks fire correctly; agent uses
  MemPalace tools per the policy in `continuity.md`. Document any gaps
  for a follow-up phase.

## Risks

- **MemPalace MCP wing-scoping behavior**: if `MEMPALACE_DEFAULT_WING`
  is not honored, the wrapper-script fallback adds complexity. Confirm
  during planning, not at implementation time.
- **Codex hook surface limits active memory**: accepted asymmetry until
  upstream changes.
- **Backfill duration**: a deep transcript history can mine for
  minutes. Surfaced via clear progress output and `--skip-backfill`
  escape hatch.
- **Settings.json merge bugs**: aggressive testing plus `.bak`
  restoration mitigate. Forge never mutates settings without a backup.
- **ChromaDB cold-start latency at SessionStart**: 1–3 s on first
  session of a boot. Acceptable per the user's quality-over-speed
  preference; the SessionStart hook timeout is 60 s.
- **Storage growth in `data/palace/`**: drawer counts grow with
  conversation volume. No automatic pruning in this phase; revisit if
  it becomes a real problem.

## Recommended Implementation Order

1. Add `forge/memory/wings.py` and tests; nothing else depends on it.
2. Add `forge/memory/env.py` and tests.
3. Add `forge/memory/install.py` and tests, with hooks pointed at
   MemPalace's shipped scripts.
4. Add `forge memory init` and `forge memory status` CLI subcommands.
5. Rewrite `forge context` to call `mempalace wake-up`; update tests.
6. Write `forge-user-prompt-submit.sh`; integrate via install.
7. Rewrite `forge/policies/continuity.md` with concrete triggers.
8. Run `forge memory init` in `~/linux/forge` and `~/linux/miniclaw`;
   validate hooks fire and wings stay isolated.
9. Remove the BM25 layer and its tests; commit separately so the diff
   is reviewable.
10. Update `WORKING_MEMORY.md` and the user-side memory entries to
    reflect the new shape.

Each step ends in a green test suite and a commit; the order is chosen
so the BM25 removal happens last, after the replacement is proven.
