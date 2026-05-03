# Nexus Working Memory

Updated: 2026-05-02

## Current Status

Phase 1 (session recall, local-doc discovery, shared policies, session activation) is complete.
Phase 2 (active memory via MemPalace) is complete. The earlier BM25 sqlite layer is retired.

Phase 1 tasks shipped (1–10):
- Repo skeleton, claude-recall migration, workspace config, local-doc discovery, context assembly, phase-1 CLI, shared policies (`core.md`, `continuity.md`), thin Claude/Codex adapters, regression tests, retired `claude-recall` (archived to `~/.archive/claude-recall-2026-04-26/`).

Session activation (2026-04-30) is live for Claude Code sessions inside managed repos:
- A workspace-level `CLAUDE.md` points at `nexus/adapters/claude/CLAUDE.md` → `core.md` + `continuity.md` (loaded via Claude Code's CLAUDE.md ancestor walk).
- A `SessionStart` hook in `~/.claude/settings.json` runs `nexus context --repo-path "$CLAUDE_PROJECT_DIR"`; stdout is injected as session context.

Phase 2 tasks shipped (1–19): MemPalace is the recall + save engine for both Claude and Codex with per-repo wing scoping. The 2026-05-02 install ran end-to-end on this machine; SessionStart and UserPromptSubmit injection were verified in a fresh Claude Code session.

## Important Implementation Notes

- `nexus.memory` package houses Phase 2 plumbing:
  - `wings.resolve_wing(cwd)` — maps a path under the workspace to a MemPalace wing name (lower-cased, `-`/space → `_`).
  - `install.{merge_claude_hooks, write_codex_hooks, locate_mempalace_hooks, init}` — idempotent installer for both agents.
  - `install._safe_write_json(path, data)` — atomic JSON write (`os.replace`) with once-only `.bak`. Reused by both Claude settings merge and Codex hook write so atomicity + write-once backup carry over.
  - `status.status_report(repo, nexus_root)` — read-only diagnostic; `nexus_root` only locates the backfill marker.
- CLI surface is `{context, doctor, memory init, memory status}`. The phase-1 `recall`, `index`, `stats` subcommands and the `nexus.db`/`nexus.query`/`nexus.indexer` modules are gone (Task 17).
- `nexus context` is a thin shell over `mempalace wake-up --wing <wing>`; falls back to local doc snippets if MemPalace returns empty or is unavailable. Recall failures are logged to `~/.cache/nexus/recall.log`.
- `nexus doctor` exit code is gated only by *fatal* checks (workspace exists, repo exists, managed repo). Memory wiring (`palace path exists`, `mempalace on path`, `claude hooks installed`) is reported but informational.
- UserPromptSubmit hook script ships at `hooks/nexus-user-prompt-submit.sh`. Best-effort: any failure produces empty injection, never a dropped prompt.
- Palace data lives at MemPalace's standard `~/.mempalace/palace`. Nexus does **not** redirect storage — wing scoping (`--wing <repo>`) gives the isolation an alternate path used to provide. Backfill markers live under `<nexus_root>/data/backfill_markers/<wing>.done`.
- Workspace root resolves from `$NEXUS_WORKSPACE_ROOT`, else from this package's location (`Path(nexus.__file__).parents[2]`). Same pattern for the nexus repo root via `$NEXUS_ROOT`.
- Continuity policy at `nexus/policies/continuity.md` rewritten 2026-05-02 with concrete recall and save triggers (when to call `mempalace_search`, what to save, wing scoping).
- Local-doc priority order: `WORKING_MEMORY.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`. Discovery recurses only inside `docs/superpowers/{specs,plans}/`.
- `pyproject.toml` does not declare a `[project.scripts]` entry; the test in `tests/test_config.py` enforces this. CLI is invoked via `python -m nexus.cli`.
- Adapters under `nexus/adapters/{claude,codex}/` are intentionally thin pointers to the shared policies. Do not inline policy text into adapter files.
- `nexus/policies/core.md` is the Karpathy-derived behavioral baseline (think before coding, simplicity first, surgical changes, goal-driven execution), sourced from `forrestchang/andrej-karpathy-skills` (MIT). Treat it as a core feature of nexus — both Claude and Codex adapters point at it.

## Current Limitations

- Codex CLI does not currently support a UserPromptSubmit-equivalent hook, so the wake-up context injection is Claude-only. Save and PreCompact hooks fire on both agents.
- The palace was created without HNSW cosine metadata, so `mempalace search` similarity scores are not meaningful (BM25 ranking still works). Run `mempalace repair` once to rebuild the index with the correct metric.

## Next Step

Phase 2 is functionally done. Future work:

1. Close the Codex prompt-injection gap when upstream supports it — port the UserPromptSubmit logic to whatever Codex provides.
2. Run `mempalace repair` to give cosine ranking real meaning on the current palace.
