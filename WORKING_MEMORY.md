# Nexus Working Memory

Updated: 2026-05-02

## Current Status

Phase 1 of `nexus` is complete. All ten plan tasks shipped.

Completed and review-clean:
- Task 1: repo skeleton
- Task 2: migrated `claude-recall` engine into `nexus`
- Task 3: workspace config and `/home/daedalus/linux` activation predicate
- Task 4: local-doc discovery and ranking
- Task 5: context assembly
- Task 6: phase-1 CLI
- Task 7: shared policies (`core.md`, `continuity.md`) and skills doc
- Task 8: thin Claude/Codex adapters under `nexus/adapters/<agent>/`
- Task 9: migration-quality regression test against fixtures
- Task 10: retired `claude-recall`; archived to `~/.archive/claude-recall-2026-04-26/`

Session activation (2026-04-30) is live. Nexus is wired into Claude Code sessions under `~/linux/`:
- `~/linux/CLAUDE.md` (workspace policy pointer) → adapter → policies via Claude Code's CLAUDE.md ancestor walk.
- `~/.claude/hooks/nexus-session-start.sh` registered in `~/.claude/settings.json` under `hooks.SessionStart` with the `"startup"` matcher.
- Hook runs `nexus.cli context --repo-path "$CLAUDE_PROJECT_DIR"`; stdout is injected as session context.
- Verified end-to-end with fresh sessions in `~/linux/`: agent receives the `Project docs:` block at session start.

Phase 2 active memory shipped 2026-05-02 (token telemetry dropped from scope). The BM25 sqlite recall layer is retired; MemPalace is the recall + save engine for both agents. Tasks 1–15, 17, 18 of the phase-2 plan (`docs/superpowers/plans/2026-05-01-nexus-active-memory.md`) shipped on `main`. Task 16 (real-world end-to-end install on this machine) was intentionally skipped this session — it modifies `~/.claude/settings.json` and `~/.codex/hooks.json` globally; best run interactively with eyes on the diffs. Steps to run it later are in the plan.

## Important Implementation Notes

- `nexus.memory` package houses Phase 2 plumbing:
  - `wings.resolve_wing(cwd)` — maps a path under the workspace to a MemPalace wing name.
  - `env.mempalace_env(wing, repo_root)` — assembles the env-var block for invoking MemPalace.
  - `install.{merge_claude_hooks, write_codex_hooks, locate_mempalace_hooks, init}` — idempotent installer for both agents.
  - `install._safe_write_json(path, data)` — atomic JSON write (`os.replace`) with once-only `.bak`. Reused by both Claude settings merge and Codex hook write so atomicity + write-once backup carry over.
  - `status.status_report(repo, nexus_root)` — read-only diagnostic.
- CLI surface is now `{context, doctor, memory init, memory status}`. The phase-1 `recall`, `index`, `stats` subcommands and the `nexus.db`/`nexus.query`/`nexus.indexer` modules are gone (Task 17).
- `nexus context` is now a thin shell over `mempalace wake-up --wing <wing>`; falls back to local doc snippets if MemPalace returns empty or is unavailable.
- `nexus doctor` exit code is gated only by *fatal* checks (workspace exists, repo exists, managed repo). Memory wiring (`palace path exists`, `mempalace on path`, `claude hooks installed`) is reported but informational.
- UserPromptSubmit hook script ships at `hooks/nexus-user-prompt-submit.sh`. Best-effort: any failure produces empty injection, never a dropped prompt.
- `data/` is gitignored — palace + hook state live there but are not version-controlled.
- Continuity policy at `nexus/policies/continuity.md` rewritten 2026-05-02 with concrete recall and save triggers (when to call `mempalace_search`, what to save, wing scoping).
- Local-doc priority order is:
  - `WORKING_MEMORY.md`
  - `CLAUDE.md`
  - `AGENTS.md`
  - `README.md`
- Discovery recurses only inside:
  - `docs/superpowers/specs/`
  - `docs/superpowers/plans/`
- `pyproject.toml` does not declare a `[project.scripts]` entry; the test in `tests/test_config.py` enforces this. CLI is invoked via `python -m` style, not via an installed entry point.
- Adapters under `nexus/adapters/{claude,codex}/` are intentionally thin pointers to the shared policies. Do not inline policy text into adapter files.
- `nexus/policies/core.md` is the Karpathy-derived behavioral baseline (think before coding, simplicity first, surgical changes, goal-driven execution), sourced from `forrestchang/andrej-karpathy-skills` (MIT). Treat it as a core feature of nexus — both Claude and Codex adapters point at it.

## Current Limitations

- Codex CLI does not currently support a UserPromptSubmit-equivalent hook, so the wake-up context injection is Claude-only. Save/PreCompact hooks fire on both agents.
- Task 16 (real install run) is pending. Until run, `mempalace` is not on PATH on this box, the smoke test in `tests/test_smoke_mempalace.py` skips, and `nexus context` returns docs-only context (no prior-session hits).

## Next Step

Phase 2 is functionally done. Future work:

1. Run Task 16 manually to wire `mempalace` into this machine and validate end-to-end.
2. Close the Codex prompt-injection gap when upstream supports it — port the UserPromptSubmit logic to whatever Codex provides.
