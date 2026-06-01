# Nexus

Local-first shared memory and policy layer for Claude Code and Codex CLI. Nexus gives both agents a common active-memory store (via MemPalace), per-repo wing scoping, and shared behavioral policies — so context, decisions, and conventions carry across sessions and across agents.

## Why

Working with Claude Code and Codex CLI across multiple repos creates two pain points:

- **Each session starts cold.** Prior decisions, constraints, and context don't carry over. You re-explain.
- **Each agent learns separately.** Anything you tell Claude doesn't reach Codex, and vice versa.

Nexus fixes both:

- **Session activation.** Every Claude Code session inside the workspace gets a lean baseline injected: identity blurb (from `~/.mempalace/identity.txt`), the list of workspace projects, the load instruction, and local doc snippets. Targeted recall fires after the user states a topic, via `nexus load <project> --topic "..."` — not as a generic wake-up dump.
- **Shared policies, shared memory.** Both agents read the same `continuity.md` (when to recall, when to save). Each project picks its domain policy: `core.md` (Karpathy coding baseline) by default, or a per-project override at `policies/projects/<project>.md` for projects whose philosophy differs (e.g. writing). Memory is scoped per repo via *wings*: work in `<workspace>/foo/` is isolated from `<workspace>/bar/`, but crosses freely between Claude and Codex.
- **Best-effort, never blocks.** Hook failures (mempalace missing, palace empty, network hiccup) inject empty context and let the prompt through. The agent harness is never bricked by a memory miss.

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
│   │   ├── core.md                # Karpathy-derived coding baseline
│   │   ├── continuity.md          # Recall/save triggers
│   │   └── projects/<name>.md     # Optional per-project policy override
│   ├── cli.py                     # context | doctor | memory {…} | load | list-projects
│   ├── config.py                  # Workspace config + managed-repo predicate
│   ├── context.py                 # Lean baseline assembly
│   ├── doc_recall.py              # Local-doc discovery (working memory, README, etc.)
│   ├── projects.py                # Workspace project listing
│   └── load.py                    # Per-project policy + targeted recall
├── hooks/
│   └── nexus-user-prompt-submit.sh  # Best-effort wake-up injection per prompt
├── docs/superpowers/{specs,plans}/  # Design docs and TDD-style plans
├── data/backfill_markers/          # Per-wing one-shot mining markers (gitignored)
└── tests/                          # pytest suite
```

Palace data and hook state live at MemPalace's standard `~/.mempalace/palace` and `~/.mempalace/hook_state` — nexus does not redirect them. Wing names are path-derived (`/home/user/workspace/repo` → `_home_user_workspace_repo`), matching what mempalace's save hooks auto-derive — so reads and writes converge on one name without forking either tool.

## Activation

Workspace root resolves from `$NEXUS_WORKSPACE_ROOT`, falling back to the parent of the nexus package. Any repo under it is "managed." When a Claude Code session starts inside a managed repo:

1. A workspace-level `CLAUDE.md` imports `core.md` + `continuity.md` via Claude Code's ancestor walk.
2. SessionStart hook runs `nexus context --repo-path "$CLAUDE_PROJECT_DIR"`; stdout (identity + project list + load instruction + doc snippets) is injected as session context.
3. Once the user states what they want to work on, the agent runs `nexus load <project> --topic "<their message>"` to pull project-scoped policy + targeted MemPalace recall.
4. UserPromptSubmit hook (`hooks/nexus-user-prompt-submit.sh`) injects `mempalace search` hits per prompt.
5. Stop / PreCompact hooks (mempalace-provided) auto-mine transcripts as you work.

Codex CLI gets the same Stop/PreCompact wiring; UserPromptSubmit support pending upstream.

## CLI

```
nexus context --repo-path <path>           # Lean SessionStart baseline (identity + projects + load instruction + docs)
nexus list-projects                        # Table of workspace projects with wing + policy source
nexus load <project> --topic "<text>"      # Per-project policy + targeted recall scoped to the wing
nexus doctor  --repo-path <path>           # Workspace + memory wiring health check
nexus memory init --mempalace-repo <path> --user-prompt-hook <path>
nexus memory status
nexus memory rename-wing --from <X> --to <Y>   # Rewrite a wing label across all drawers
```

`memory init` is idempotent and `.bak`s any settings file before the first edit. Use `memory rename-wing` after moving your workspace (e.g. `~/linux/` → `~/projects/`) — path-derived wing names shift with the move, and this command rewrites the `wing` metadata in place so prior memories aren't orphaned.

### Per-project policies

`nexus load <project>` reads its domain policy from `nexus/policies/projects/<project>.md` if present, otherwise falls back to `core.md` with a one-line bootstrap note pointing at the missing file. This lets a coding project use the Karpathy baseline while, say, a writing project ships its own philosophy (show-don't-tell, draft-over-polish, etc.). `continuity.md` always applies regardless of project.

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

Step 4 merges hooks into `~/.claude/settings.json` and `~/.codex/hooks.json` (once-only `.bak` backups), then backfills existing transcripts for managed repos. The CLI is invoked via `python -m nexus.cli` from anywhere — no `[project.scripts]` entry, by design.

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

- Phase 1 (session recall, local-doc discovery, shared policies, session activation) shipped 2026-04-30.
- Phase 2 (active memory via MemPalace) shipped 2026-05-02. Earlier BM25 sqlite layer retired.

See `WORKING_MEMORY.md` for current state and known limitations.
