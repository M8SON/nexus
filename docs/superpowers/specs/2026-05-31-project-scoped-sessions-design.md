# Project-scoped session loading

**Status:** Design approved 2026-05-31
**Author:** Mason Misch (M8SON)

## Problem

The SessionStart hook currently dumps a generic L1 essential story from
`mempalace wake-up --wing <path-derived-wing>`. The wake-up is frozen
before the user has said what they want to work on, so the recall is
whatever the wing's most recent transcript bytes happened to be — often
unrelated to today's topic. The single `core.md` policy (Karpathy /
coding) also applies uniformly, even when the work isn't coding.

The user wants:

1. Project-scoped recall fired *after* the first message states the
   topic, so the recall query reflects what we are actually doing.
2. A per-project policy file that replaces `core.md` when the project's
   philosophy differs (e.g. a writing project, not a coding one).
3. `continuity.md` (memory mechanics) always loads regardless of
   project.

## Architecture

```
SessionStart hook
    │
    ▼
nexus context  →  lean baseline:
    • identity blurb
    • continuity.md (always)
    • available-projects line
    • instruction: wait for first message, then run `nexus load`
    │
    ▼
User: "I want to work on my book today, picking up chapter 3"
    │
    ▼
Claude runs:  nexus load book --topic "picking up chapter 3"
    │
    ▼
nexus load:
    1. Validate ~/linux/book exists
    2. Resolve wing → _home_daedalus_linux_book
    3. Read policy:
         projects/book.md  (if exists)
         else core.md      (with bootstrap note)
    4. mempalace search "<topic>" --wing <wing>
    5. Print policy + recall hits to stdout
    │
    ▼
Claude reads stdout, internalizes policy + recall
```

The SessionStart hook stops loading domain content. The `nexus load`
call is what brings in project-specific context, *after* the topic is
known.

## Components

### SessionStart hook change

`~/.claude/hooks/nexus-session-start.sh` continues to call
`nexus context --repo-path "$CLAUDE_PROJECT_DIR"`. The behavior of
`nexus context` changes:

**Before:** identity + L1 essential story (wing-scoped, generic) +
local docs.

**After:** identity + continuity.md mechanics + available-projects
line + load instruction + local docs.

Example new output:

```
Mason Misch (M8SON). [identity blurb stays — same source]

Workspace projects available: book, miniclaw, nexus, kaizen
When the user states what they want to work on today, run:
  nexus load <project> --topic "<their message>"
Do not pre-load anything else.

[continuity.md content]
[local doc snippets]
```

The available-projects line comes from scanning `<workspace>/*/` one
level deep and emitting folder names — extracted to
`nexus/memory/projects.py` so `list-projects` shares the same source.

### `nexus load <project>` CLI subcommand

New subcommand in `nexus/cli.py`, implemented in `nexus/load.py`.

**Signature:** `nexus load <project> --topic <text> [--limit N]`

| Arg | Required | Description |
|-----|----------|-------------|
| `<project>` | yes | Folder name under `<workspace_root>`, not a path |
| `--topic` | yes | First-message text, passed verbatim as the search query |
| `--limit` | no | Max recall hits. Default 5 |

**nexus_root resolution:** reuse the existing `_default_nexus_root()`
helper in `cli.py` (env var `NEXUS_ROOT`, else infer from package
location).

**Logic:**

1. Resolve project dir: `<workspace_root>/<project>`. Missing → exit
   1, print `nexus load: project '<name>' not found under <workspace>.
   Available: <list>`.
2. Resolve wing: `path_to_wing(project_dir)` (reuse `wings.py`).
3. Resolve policy:
   - `<nexus_root>/nexus/policies/projects/<project>.md` if it exists.
   - Else `<nexus_root>/nexus/policies/core.md` with a one-line note:
     `note: no project policy at projects/<project>.md — using core.md.`
4. Run `mempalace search "<topic>" --wing <wing> --results <limit>`.
   Reuse `_resolve_mempalace_bin` and the 10s-timeout subprocess
   pattern from `_mempalace_wake_up`.
5. Print to stdout:

   ```
   # Project policy: <project>
   <policy file contents>

   # Recall hits for "<topic>" (wing: <wing>)
   <mempalace search output, or "(no prior recall for this topic)">
   ```

**Error handling:** missing mempalace binary → policy only + one-line
warning, log to `~/.cache/nexus/recall.log`. Search timeout → policy +
empty recall. Never crash the session. Exit 0 unless the project
itself is unknown.

### `nexus list-projects` CLI subcommand

```
nexus list-projects
```

Scans `<workspace>/*/` and prints one row per dir:

```
project       wing                              policy           drawers
book          _home_daedalus_linux_book         projects/book.md   47
miniclaw      _home_daedalus_linux_miniclaw     core (default)     0
nexus         _home_daedalus_linux_nexus        core (default)     55
```

`drawers` column from `mempalace_list_wings` when available; `?`
otherwise. Same helper that feeds the SessionStart available-projects
line.

### Policy file convention

**Location:** `<nexus_root>/nexus/policies/projects/<project>.md`.

**Naming:** filename matches the workspace folder name exactly,
lowercase, `.md` extension.

**Structure:** plain markdown, no required schema. Verbatim policy
document.

**Composition rule:**

| File | When loaded | Role |
|------|-------------|------|
| `continuity.md` | Always (SessionStart) | Memory mechanics — applies everywhere |
| `core.md` | Default | Used when no project policy exists |
| `projects/<X>.md` | When `nexus load <X>` runs | **Replaces** `core.md` for that project |

Never both `core.md` and a project file at once.

## Edge cases

1. **Unknown project** — exit 1, print available list. No auto-create.
2. **Project exists, no policy file** — `core.md` + bootstrap note.
3. **Empty recall** — policy + `(no prior recall for this topic)`.
   Exit 0.
4. **Mempalace missing** — policy + warning to stderr and recall log.
   Exit 0.
5. **Ambiguous user message** ("let's do something new") — the
   SessionStart instruction tells the model to ask the user which
   project to load. No code concern.
6. **Switching projects mid-session** — supported implicitly by
   re-running `nexus load`. The new policy + recall layer into
   context; nothing actively unloads the prior policy. Documented
   behavior, not a feature.

## Testing

New tests under `nexus/tests/`:

- `test_load.py`
  - project → wing resolution
  - policy file resolution (project file present / absent)
  - bootstrap note when falling back to `core.md`
  - unknown project exits 1 with available list
  - stdout format matches the documented blob
  - mempalace timeout / missing binary handled cleanly
- `test_projects_listing.py`
  - `list-projects` row format
  - shared helper returns the available-projects line for SessionStart
- `test_session_start_emission.py`
  - `nexus context` no longer emits L1
  - lean baseline + available-projects line + instruction present
- Update existing `test_context.py` for the new `nexus context` shape.

Mempalace stubbed via subprocess monkeypatch (existing pattern from
`_mempalace_wake_up` tests).

## Out of scope

- Auto-creating new project dirs from `nexus load`.
- Policy templates / scaffolding for `projects/<X>.md`.
- Recording which project was "active" across sessions (sticky
  resume). Each session starts fresh and the user states the project.
- Codex CLI hook integration — Codex doesn't have a UserPromptSubmit
  equivalent (per existing project memory). The `nexus load` command
  is portable; whether Codex sessions trigger it is a separate
  question.
