# Forge Working Memory

Updated: 2026-04-26

## Current Status

Phase 1 of `forge` is complete. All ten plan tasks shipped.

Completed and review-clean:
- Task 1: repo skeleton
- Task 2: migrated `claude-recall` engine into `forge`
- Task 3: workspace config and `/home/daedalus/linux` activation predicate
- Task 4: local-doc discovery and ranking
- Task 5: context assembly
- Task 6: phase-1 CLI
- Task 7: shared policies (`core.md`, `continuity.md`) and skills doc
- Task 8: thin Claude/Codex adapters under `forge/adapters/<agent>/`
- Task 9: migration-quality regression test against fixtures
- Task 10: retired `claude-recall`; archived to `~/.archive/claude-recall-2026-04-26/`

Phase 2 (active memory, token telemetry) remains documented in the spec but intentionally deferred.

## Important Implementation Notes

- The recall engine migration took several hardening passes.
- Query normalization now preserves:
  - valid quoted phrases
  - valid fielded queries like `tool_name:grep`
  - mixed fielded + punctuation-heavy literal queries
- Query handling no longer hides generic sqlite/schema failures as "no hits".
- Indexing now safely handles rewritten transcript files instead of assuming every change is append-only.
- Local-doc priority order is:
  - `WORKING_MEMORY.md`
  - `CLAUDE.md`
  - `AGENTS.md`
  - `README.md`
- Discovery recurses only inside:
  - `docs/superpowers/specs/`
  - `docs/superpowers/plans/`
- CLI defaults now derive the Claude projects slug from the configured workspace root instead of hardcoding `-home-daedalus-linux`.
- `pyproject.toml` does not declare a `[project.scripts]` entry; the test in `tests/test_config.py` enforces this. CLI is invoked via `python -m` style, not via an installed entry point.
- Adapters under `forge/adapters/{claude,codex}/` are intentionally thin pointers to the shared policies. Do not inline policy text into adapter files.
- `forge/policies/core.md` is the Karpathy-derived behavioral baseline (think before coding, simplicity first, surgical changes, goal-driven execution), sourced from `forrestchang/andrej-karpathy-skills` (MIT). Treat it as a core feature of forge — both Claude and Codex adapters point at it.

## Current Limitations

- `forge context` still uses global recall results, not repo-scoped recall, because the migrated query layer does not yet expose a repo/cwd filter.
- The default Claude projects path derivation is still a local string-convention helper; there is no shared slug utility yet.

## Recent Commits (Tasks 7–10)

- `7c7df6f` `docs: add shared forge policies and skills`
- `29d48b9` `fix: drop forge.cli script entry to match self-contained packaging`
- `22d8f89` `docs: add forge agent adapters`
- `ec67500` `test: validate forge recall migration quality`
- `2c6c19c` `chore: retire claude-recall in favor of forge`
- `6876f0d` `feat: adopt karpathy guidelines as core forge policy`

## Next Step

Plan `2026-04-26-forge.md` is fully executed. Active follow-ups, in chosen order:
1. Wire forge into Claude Code sessions — spec at `docs/superpowers/specs/2026-04-30-forge-session-activation-design.md`. Static CLAUDE.md at `~/linux/CLAUDE.md` + SessionStart hook running `forge.cli context`. Active session recall deferred to phase 2.
2. Add a repo/cwd filter to the recall query layer (currently global; called out under Current Limitations).
3. Write a phase-2 plan for active memory and token telemetry.
