# Nexus

Local-first shared assistant framework for Claude and Codex — a nexus point for AI agents working across the repos in your workspace directory.

Nexus combines per-repo session recall, local-doc discovery, and shared agent policies into one repo, and hosts an active-memory layer (via MemPalace) with per-repo wing scoping.

## Why

Working with Claude Code and Codex CLI across multiple repos creates two pain points:

- **Each session starts cold.** Prior decisions, constraints, and context don't carry over. You re-explain.
- **Each agent learns separately.** Anything you tell Claude doesn't reach Codex, and vice versa.

Nexus fixes both:

- **Session activation.** Every Claude Code session started inside the configured workspace gets a `Project docs:` block (working memory + adapter policies) and a `Prior session context:` block (MemPalace `wake-up` for the active repo's wing) injected automatically. No manual recall query needed.
- **Shared policies, shared memory.** Both agents read the same `core.md` (Karpathy-derived behavioral baseline) and `continuity.md` (when to recall, when to save). Both write to the same MemPalace, scoped per repo via *wings* — work done inside `<workspace>/foo/` writes to wing `foo`, work inside `<workspace>/bar/` writes to wing `bar`. Memory crosses agents but stays scoped to the project it belongs to.
- **Best-effort, never blocks.** Hook failures (mempalace not installed, palace empty, network hiccup) inject empty context and let the prompt through. The agent harness is never bricked by a memory miss.

## Structure

```
nexus/
├── nexus/
│   ├── adapters/{claude,codex}/   # Thin adapter pointers to shared policies
│   ├── memory/                    # Active-memory plumbing (Phase 2)
│   │   ├── wings.py               # cwd → wing name resolution
│   │   ├── install.py             # Idempotent installer for both agents
│   │   └── status.py              # Read-only diagnostic
│   ├── policies/
│   │   ├── core.md                # Karpathy-derived behavioral baseline
│   │   └── continuity.md          # Recall/save triggers
│   ├── cli.py                     # context | doctor | memory {init,status}
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
and `~/.mempalace/hook_state` — nexus does not redirect them. Wing scoping
(`--wing <repo>`) provides logical isolation between repos.

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
nexus context --repo-path <path>      # Assemble session context (wraps `mempalace wake-up`)
nexus doctor  --repo-path <path>      # Workspace + memory wiring health check
nexus memory init --mempalace-repo <path> --user-prompt-hook <path>
nexus memory status
```

`nexus memory init` is idempotent and creates `.bak` of any settings file it touches before the first edit.

## Install

```bash
cd /path/to/nexus
python -m venv .venv
.venv/bin/pip install -e .
```

The CLI resolves via `python -m nexus.cli` from anywhere; no `[project.scripts]` entry, by design (keeps the package self-contained).

## Status

Phase 1 (session recall, local-doc discovery, shared policies, session activation) shipped 2026-04-30.
Phase 2 (active memory via MemPalace) shipped 2026-05-02. The earlier BM25 sqlite layer is retired.

See `WORKING_MEMORY.md` for the current state and remaining limitations.
