# Nexus

Local-first shared assistant framework for Claude and Codex — a nexus point for AI agents working across the repos in your workspace directory.

Nexus combines per-repo session recall, local-doc discovery, and shared agent policies into one repo, and hosts an active-memory layer (via MemPalace) with per-repo wing scoping.

## Why

Working with Claude Code and Codex CLI across multiple repos creates two pain points:

- **Each session starts cold.** Prior decisions, constraints, and context don't carry over. You re-explain.
- **Each agent learns separately.** Anything you tell Claude doesn't reach Codex, and vice versa.

Nexus fixes both:

- **Session activation.** Every Claude Code session started inside the configured workspace gets a `Project docs:` block (working memory + adapter policies) and a `Prior session context:` block (MemPalace `wake-up` for the active repo's wing) injected automatically. No manual recall query needed.
- **Shared policies, shared memory.** Both agents read the same `core.md` (Karpathy-derived behavioral baseline) and `continuity.md` (when to recall, when to save). Both write to the same MemPalace, scoped per repo via *wings* — work done inside `<workspace>/foo/` writes to a wing derived from that path (e.g. `_home_user_workspace_foo`), work inside `<workspace>/bar/` writes to its own wing. Wing names match what mempalace's auto-mining produces, so its save hooks and nexus's recall converge on one name without forking either tool. Memory crosses agents but stays scoped to the project it belongs to.
- **Best-effort, never blocks.** Hook failures (mempalace not installed, palace empty, network hiccup) inject empty context and let the prompt through. The agent harness is never bricked by a memory miss.

## Structure

```
nexus/
├── nexus/
│   ├── adapters/{claude,codex}/   # Thin adapter pointers to shared policies
│   ├── memory/                    # Active-memory plumbing (Phase 2)
│   │   ├── wings.py               # cwd → wing name resolution
│   │   ├── install.py             # Idempotent installer for both agents
│   │   ├── migration.py           # Wing rename helper (workspace path moves)
│   │   └── status.py              # Read-only diagnostic
│   ├── policies/
│   │   ├── core.md                # Karpathy-derived behavioral baseline
│   │   └── continuity.md          # Recall/save triggers
│   ├── cli.py                     # context | doctor | memory {init,status,rename-wing}
│   ├── config.py                  # Workspace config + managed-repo predicate
│   ├── context.py                 # Context summary assembly
│   └── doc_recall.py              # Local-doc discovery (working memory, README, etc.)
├── hooks/
│   └── nexus-user-prompt-submit.sh  # Best-effort wake-up injection per prompt
├── docs/superpowers/{specs,plans}/  # Design docs and TDD-style plans
├── data/backfill_markers/          # Per-wing one-shot mining markers (gitignored)
└── tests/                          # pytest suite
```

Palace data and hook state live at MemPalace's standard `~/.mempalace/palace`
and `~/.mempalace/hook_state` — nexus does not redirect them. Wing names are
path-derived (e.g. `_home_user_workspace_repo`), matching mempalace's own
`normalize_wing_name` so its save hooks and nexus's recall agree on the same
label without manual `--wing` flags.

## Activation

The workspace root resolves from `$NEXUS_WORKSPACE_ROOT` if set, otherwise
from this package's location (the parent of the nexus repo). Any repo placed
underneath the workspace is treated as a managed repo. For a Claude Code
session started inside a managed repo:

1. A `CLAUDE.md` at the workspace root points at `nexus/adapters/claude/CLAUDE.md` → `core.md` + `continuity.md`. Loaded via Claude Code's CLAUDE.md ancestor walk.
2. A SessionStart hook (registered in `~/.claude/settings.json`) runs `nexus context --repo-path "$CLAUDE_PROJECT_DIR"`; stdout is injected as session context.
3. UserPromptSubmit hook (`hooks/nexus-user-prompt-submit.sh`) runs per prompt to inject `mempalace search` hits for the active wing.
4. Stop and PreCompact hooks (provided by MemPalace) auto-mine transcripts so memory grows over time.

Codex CLI gets the same Stop/PreCompact wiring; UserPromptSubmit support is pending upstream.

## CLI

```
nexus context --repo-path <path>           # Assemble session context (wraps `mempalace wake-up`)
nexus doctor  --repo-path <path>           # Workspace + memory wiring health check
nexus memory init --mempalace-repo <path> --user-prompt-hook <path>
nexus memory status
nexus memory rename-wing --from <X> --to <Y>   # Rewrite a wing label across all drawers
```

`nexus memory init` is idempotent and creates `.bak` of any settings file it touches before the first edit.

`memory rename-wing` is the recovery path when the workspace path changes (e.g. moving `~/linux/` → `~/projects/`): wing names are path-derived, so a directory move would otherwise orphan prior memories. The command walks mempalace's drawers and rewrites the `wing` metadata field in place; no re-mining needed.

## Install

```bash
# 1. Clone nexus into your workspace
cd ~/your-workspace
git clone https://github.com/M8SON/nexus.git
cd nexus

# 2. Set up the venv
python -m venv .venv
.venv/bin/pip install -e .

# 3. Clone and install mempalace (provides the active-memory layer)
git clone https://github.com/MemPalace/mempalace.git ~/mempalace
.venv/bin/pip install mempalace

# 4. Wire hooks into Claude Code + Codex
.venv/bin/python -m nexus.cli memory init \
  --mempalace-repo ~/mempalace \
  --user-prompt-hook "$(pwd)/hooks/nexus-user-prompt-submit.sh"

# 5. Verify the wiring
.venv/bin/python -m nexus.cli doctor
```

Step 4 merges Stop/PreCompact/UserPromptSubmit hooks into `~/.claude/settings.json` and `~/.codex/hooks.json` (with once-only `.bak` backups), then backfills any existing transcripts that map to managed repos. The CLI resolves via `python -m nexus.cli` from anywhere; there is no `[project.scripts]` entry, by design.

## Configuration

The shared layer (policies, adapters under `nexus/`) is version-controlled — every user gets the same behavioral contract. The per-user knobs:

1. **Workspace root** — where your managed repos live. Set `$NEXUS_WORKSPACE_ROOT` in your shell profile, or rely on the default (the parent of the nexus repo).

2. **Identity (recommended)** — write a short personal-context blurb to `~/.mempalace/identity.txt`. MemPalace surfaces this as the L0 layer of every wake-up. Keep it short, path-free, and **never commit it** — the repo's `.gitignore` already blocks `identity.txt` and `.mempalace/` defensively. Example:
   ```
   Jane Doe. Builds project X (a Y) and project Z (a W). Primary
   language Python; prefers terse progress updates and surgical changes.
   ```

3. **Workspace `CLAUDE.md`** — at the root of your workspace, create a `CLAUDE.md` that imports the nexus policies. Claude Code's CLAUDE.md ancestor walk picks it up:
   ```markdown
   # Nexus-managed workspace

   @nexus/nexus/policies/core.md
   @nexus/nexus/policies/continuity.md
   ```

   The `@nexus/nexus/policies/...` paths assume nexus lives at `<workspace>/nexus/`. If you cloned it elsewhere, adjust the import paths (Claude Code resolves `@`-imports relative to the `CLAUDE.md` file's directory) — e.g. with nexus at `<workspace>/tools/nexus/`, use `@tools/nexus/nexus/policies/core.md`.

## Status

Phase 1 (session recall, local-doc discovery, shared policies, session activation) shipped 2026-04-30.
Phase 2 (active memory via MemPalace) shipped 2026-05-02. The earlier BM25 sqlite layer is retired.

See `WORKING_MEMORY.md` for the current state and remaining limitations.
