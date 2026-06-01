# Project-Scoped Session Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the SessionStart generic L1 wake-up with a `nexus load <project> --topic <text>` flow that fires after the user's first message, and add per-project policy overlay that replaces `core.md` when the project's philosophy differs from coding.

**Architecture:** Two new CLI subcommands (`load`, `list-projects`) and a rewrite of `nexus context` to emit a lean baseline instead of a generic wake-up. Per-project policy files live at `nexus/policies/projects/<project>.md`. Targeted recall uses `mempalace search` scoped to the project's wing. `continuity.md` is unaffected — it loads via `CLAUDE.md` `@`-imports, not via `nexus context`.

**Tech Stack:** Python 3.11+, argparse, subprocess (for `mempalace` CLI), pytest. All work is in the `nexus` repo at `/home/daedalus/linux/nexus`.

**Spec:** `docs/superpowers/specs/2026-05-31-project-scoped-sessions-design.md`

---

## File Structure

**New:**
- `nexus/projects.py` — list / introspect workspace projects
- `nexus/load.py` — policy resolution + targeted recall + load orchestration
- `nexus/policies/projects/.gitkeep` — directory marker (per-project policy files land here)
- `tests/test_projects.py`
- `tests/test_load.py`

**Modified:**
- `nexus/cli.py` — add `load` + `list-projects` subcommands, rewrite `_handle_context`
- `nexus/context.py` — add `build_lean_baseline()` helper
- `tests/test_context.py` — cover lean baseline
- `tests/test_cli.py` — cover new subcommands + updated `context` output

**Unchanged (verify only):**
- `~/.claude/hooks/nexus-session-start.sh` — still calls `nexus context`; inherits new output.
- `nexus/memory/wings.py` — reused as-is for wing resolution.

---

## Task 1: `nexus/projects.py` — list workspace projects

**Files:**
- Create: `nexus/projects.py`
- Test: `tests/test_projects.py`

A workspace project is any directory directly under `workspace_root`. The helper returns enough info for both the SessionStart "available projects" line and the `list-projects` CLI table.

- [ ] **Step 1: Write the failing test**

Create `tests/test_projects.py`:

```python
from pathlib import Path

from nexus.projects import list_projects


def test_lists_directories_under_workspace(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / "miniclaw").mkdir(parents=True)
    (workspace / "nexus").mkdir(parents=True)
    (workspace / "not-a-dir.txt").write_text("ignore me")

    projects = list_projects(workspace)

    names = [p.name for p in projects]
    assert names == ["book", "miniclaw", "nexus"]


def test_includes_policy_presence_flag(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / "miniclaw").mkdir(parents=True)

    nexus_root = tmp_path / "nexus_repo"
    projects_policy_dir = nexus_root / "nexus" / "policies" / "projects"
    projects_policy_dir.mkdir(parents=True)
    (projects_policy_dir / "book.md").write_text("writing rules")

    projects = list_projects(workspace, nexus_root=nexus_root)

    by_name = {p.name: p for p in projects}
    assert by_name["book"].has_policy is True
    assert by_name["miniclaw"].has_policy is False


def test_returns_empty_when_workspace_missing(tmp_path):
    projects = list_projects(tmp_path / "does-not-exist")
    assert projects == []


def test_skips_hidden_and_underscore_dirs(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / ".git").mkdir()
    (workspace / "__pycache__").mkdir()

    projects = list_projects(workspace)
    assert [p.name for p in projects] == ["book"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_projects.py -v`
Expected: `ImportError: cannot import name 'list_projects' from 'nexus.projects'` (module doesn't exist yet).

- [ ] **Step 3: Implement `nexus/projects.py`**

```python
"""Workspace project introspection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    has_policy: bool


def list_projects(workspace_root: Path, nexus_root: Path | None = None) -> list[Project]:
    """List directories directly under `workspace_root` as projects.

    Skips hidden dirs (starting with `.`) and dunder dirs (starting with `_`).
    If `nexus_root` is provided, flags whether each project has a policy file at
    `<nexus_root>/nexus/policies/projects/<name>.md`.
    """
    workspace_root = Path(workspace_root)
    if not workspace_root.is_dir():
        return []

    policy_dir: Path | None = None
    if nexus_root is not None:
        policy_dir = Path(nexus_root) / "nexus" / "policies" / "projects"

    projects: list[Project] = []
    for child in sorted(workspace_root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith(".") or name.startswith("_"):
            continue
        has_policy = bool(policy_dir and (policy_dir / f"{name}.md").is_file())
        projects.append(Project(name=name, path=child, has_policy=has_policy))
    return projects
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_projects.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/daedalus/linux/nexus
git add nexus/projects.py tests/test_projects.py
git commit -m "feat(projects): list workspace projects with policy-presence flag"
```

---

## Task 2: `nexus/load.py` — policy resolution

**Files:**
- Create: `nexus/load.py`
- Create: `nexus/policies/projects/.gitkeep`
- Test: `tests/test_load.py` (new)

Resolves the policy text for a project: per-project file if it exists, else `core.md` with a bootstrap note.

- [ ] **Step 1: Create the projects policy directory marker**

```bash
cd /home/daedalus/linux/nexus
mkdir -p nexus/policies/projects
touch nexus/policies/projects/.gitkeep
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_load.py`:

```python
from pathlib import Path

import pytest

from nexus.load import PolicyResolution, resolve_policy


def _make_nexus_root(tmp_path: Path) -> Path:
    nexus_root = tmp_path / "nexus_repo"
    policies = nexus_root / "nexus" / "policies"
    (policies / "projects").mkdir(parents=True)
    (policies / "core.md").write_text("# Karpathy core policy\nThink before coding.")
    return nexus_root


def test_returns_project_policy_when_file_exists(tmp_path):
    nexus_root = _make_nexus_root(tmp_path)
    project_md = nexus_root / "nexus" / "policies" / "projects" / "book.md"
    project_md.write_text("# Writing policy\nShow, don't tell.")

    result = resolve_policy("book", nexus_root)

    assert isinstance(result, PolicyResolution)
    assert result.source == "projects/book.md"
    assert "Show, don't tell." in result.text
    assert result.bootstrap_note is None


def test_falls_back_to_core_with_bootstrap_note(tmp_path):
    nexus_root = _make_nexus_root(tmp_path)

    result = resolve_policy("book", nexus_root)

    assert result.source == "core.md"
    assert "Karpathy core policy" in result.text
    assert result.bootstrap_note is not None
    assert "projects/book.md" in result.bootstrap_note


def test_raises_when_core_missing(tmp_path):
    nexus_root = tmp_path / "nexus_repo"
    (nexus_root / "nexus" / "policies" / "projects").mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        resolve_policy("book", nexus_root)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_load.py -v`
Expected: `ImportError: cannot import name 'resolve_policy' from 'nexus.load'`.

- [ ] **Step 4: Implement `nexus/load.py`**

```python
"""Project loading: policy resolution + targeted recall."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PolicyResolution:
    """Result of resolving a project's policy file."""

    text: str
    source: str  # "projects/<name>.md" or "core.md"
    bootstrap_note: str | None  # one-line note when falling back to core.md


def resolve_policy(project: str, nexus_root: Path) -> PolicyResolution:
    """Return the policy text for `project`.

    Prefers `<nexus_root>/nexus/policies/projects/<project>.md`. Falls back
    to `<nexus_root>/nexus/policies/core.md` with a bootstrap note. Raises
    FileNotFoundError if core.md is also missing (broken repo state).
    """
    policies = Path(nexus_root) / "nexus" / "policies"
    project_md = policies / "projects" / f"{project}.md"
    core_md = policies / "core.md"

    if project_md.is_file():
        return PolicyResolution(
            text=project_md.read_text(encoding="utf-8"),
            source=f"projects/{project}.md",
            bootstrap_note=None,
        )

    if not core_md.is_file():
        raise FileNotFoundError(
            f"neither projects/{project}.md nor core.md exists under {policies}"
        )

    note = (
        f"note: no project policy at projects/{project}.md — using core.md. "
        "Create the file to customize."
    )
    return PolicyResolution(
        text=core_md.read_text(encoding="utf-8"),
        source="core.md",
        bootstrap_note=note,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_load.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
cd /home/daedalus/linux/nexus
git add nexus/load.py nexus/policies/projects/.gitkeep tests/test_load.py
git commit -m "feat(load): resolve per-project policy with core.md fallback"
```

---

## Task 3: `nexus/load.py` — targeted recall via `mempalace search`

**Files:**
- Modify: `nexus/load.py` (add `mempalace_search`)
- Modify: `tests/test_load.py` (add tests)

Mirror the existing `_mempalace_wake_up` / `_resolve_mempalace_bin` pattern from `cli.py`, but make it `search`-based. Keep the helper public (no leading underscore) so the CLI handler imports it cleanly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_load.py`:

```python
from unittest.mock import patch

from nexus.load import mempalace_search


def test_search_returns_stdout_on_success():
    fake_completed = type("R", (), {"returncode": 0, "stdout": "hit one\nhit two\n", "stderr": ""})()
    with patch("nexus.load.subprocess.run", return_value=fake_completed) as run:
        out = mempalace_search("chapter 3", wing="_x_book", limit=5)

    assert out == "hit one\nhit two\n"
    cmd = run.call_args.args[0]
    assert cmd[1:] == ["search", "chapter 3", "--wing", "_x_book", "--results", "5"]


def test_search_returns_empty_on_nonzero_exit():
    fake = type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()
    with patch("nexus.load.subprocess.run", return_value=fake):
        out = mempalace_search("q", wing="_x", limit=3)
    assert out == ""


def test_search_returns_empty_on_timeout():
    import subprocess
    with patch(
        "nexus.load.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="mempalace", timeout=10),
    ):
        out = mempalace_search("q", wing="_x", limit=3)
    assert out == ""


def test_search_raises_when_binary_missing(monkeypatch):
    monkeypatch.setattr("nexus.load._resolve_mempalace_bin", lambda: "/no/such/mempalace")
    with patch(
        "nexus.load.subprocess.run",
        side_effect=FileNotFoundError("not there"),
    ):
        import pytest
        with pytest.raises(FileNotFoundError):
            mempalace_search("q", wing="_x", limit=3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_load.py -v`
Expected: 4 new failures with `ImportError: cannot import name 'mempalace_search' from 'nexus.load'`.

- [ ] **Step 3: Implement `mempalace_search` in `nexus/load.py`**

Add to `nexus/load.py`:

```python
import os
import subprocess
import sys


def _resolve_mempalace_bin() -> str:
    """Locate the mempalace binary.

    Prefers the binary co-located with sys.executable (Claude Code may strip
    PATH so bare lookups fail). Falls back to bare `mempalace`.
    """
    venv_bin = Path(sys.executable).parent / "mempalace"
    if venv_bin.is_file() and os.access(venv_bin, os.X_OK):
        return str(venv_bin)
    return "mempalace"


def mempalace_search(query: str, *, wing: str, limit: int) -> str:
    """Run `mempalace search` and return stdout. Empty string on any failure
    except missing binary (which raises FileNotFoundError so the caller can
    distinguish 'unavailable' from 'no hits')."""
    cmd = [
        _resolve_mempalace_bin(),
        "search",
        query,
        "--wing",
        wing,
        "--results",
        str(limit),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_load.py -v`
Expected: 7 passed total (3 from Task 2 + 4 new).

- [ ] **Step 5: Commit**

```bash
cd /home/daedalus/linux/nexus
git add nexus/load.py tests/test_load.py
git commit -m "feat(load): mempalace_search helper for targeted recall"
```

---

## Task 4: `nexus/load.py` — `load_project` orchestration

**Files:**
- Modify: `nexus/load.py` (add `load_project`)
- Modify: `tests/test_load.py` (add tests)

The composer: validates the project exists, resolves policy, runs targeted recall, returns a result the CLI handler formats. Keeping orchestration in a function (not the CLI handler) lets us test it directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_load.py`:

```python
from unittest.mock import patch

from nexus.load import LoadResult, load_project
from nexus.memory.wings import path_to_wing


def _make_workspace(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    return workspace


def test_load_project_returns_policy_and_recall(tmp_path):
    workspace = _make_workspace(tmp_path)
    nexus_root = _make_nexus_root(tmp_path)
    project_md = nexus_root / "nexus" / "policies" / "projects" / "book.md"
    project_md.write_text("# Writing policy\nShow, don't tell.")

    with patch("nexus.load.mempalace_search", return_value="hit one\nhit two") as ms:
        result = load_project(
            project="book",
            topic="chapter 3",
            workspace_root=workspace,
            nexus_root=nexus_root,
            limit=5,
        )

    assert isinstance(result, LoadResult)
    assert result.project == "book"
    assert result.wing == path_to_wing(workspace / "book")
    assert result.policy.source == "projects/book.md"
    assert "Show, don't tell." in result.policy.text
    assert result.recall == "hit one\nhit two"
    assert result.memory_unavailable is False

    ms.assert_called_once()
    call_kwargs = ms.call_args.kwargs
    assert call_kwargs["wing"] == result.wing
    assert call_kwargs["limit"] == 5


def test_load_project_unknown_project_raises(tmp_path):
    workspace = _make_workspace(tmp_path)
    nexus_root = _make_nexus_root(tmp_path)

    import pytest
    with pytest.raises(ValueError) as exc:
        load_project(
            project="ghost",
            topic="anything",
            workspace_root=workspace,
            nexus_root=nexus_root,
        )
    assert "ghost" in str(exc.value)
    assert "book" in str(exc.value)  # available list mentions book


def test_load_project_handles_missing_mempalace(tmp_path):
    workspace = _make_workspace(tmp_path)
    nexus_root = _make_nexus_root(tmp_path)

    with patch("nexus.load.mempalace_search", side_effect=FileNotFoundError):
        result = load_project(
            project="book",
            topic="x",
            workspace_root=workspace,
            nexus_root=nexus_root,
        )

    assert result.recall == ""
    assert result.memory_unavailable is True
    assert result.policy.source == "core.md"  # no project file in this test


def test_load_project_empty_recall_is_ok(tmp_path):
    workspace = _make_workspace(tmp_path)
    nexus_root = _make_nexus_root(tmp_path)

    with patch("nexus.load.mempalace_search", return_value=""):
        result = load_project(
            project="book",
            topic="x",
            workspace_root=workspace,
            nexus_root=nexus_root,
        )

    assert result.recall == ""
    assert result.memory_unavailable is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_load.py -v`
Expected: 4 new failures (`ImportError: cannot import name 'load_project' from 'nexus.load'`).

- [ ] **Step 3: Implement `load_project` in `nexus/load.py`**

Append to `nexus/load.py`:

```python
from nexus.memory.wings import path_to_wing
from nexus.projects import list_projects


@dataclass(frozen=True)
class LoadResult:
    project: str
    wing: str
    policy: PolicyResolution
    recall: str
    memory_unavailable: bool


def load_project(
    *,
    project: str,
    topic: str,
    workspace_root: Path,
    nexus_root: Path,
    limit: int = 5,
) -> LoadResult:
    """Validate project, resolve policy, run targeted recall.

    Raises ValueError when `project` doesn't exist under `workspace_root`.
    Never raises for missing/timed-out mempalace — surfaces that via
    `memory_unavailable`.
    """
    project_dir = Path(workspace_root) / project
    if not project_dir.is_dir():
        available = ", ".join(p.name for p in list_projects(workspace_root)) or "(none)"
        raise ValueError(
            f"project '{project}' not found under {workspace_root}. "
            f"Available: {available}"
        )

    wing = path_to_wing(project_dir)
    policy = resolve_policy(project, nexus_root)

    memory_unavailable = False
    try:
        recall = mempalace_search(topic, wing=wing, limit=limit)
    except FileNotFoundError:
        recall = ""
        memory_unavailable = True

    return LoadResult(
        project=project,
        wing=wing,
        policy=policy,
        recall=recall,
        memory_unavailable=memory_unavailable,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_load.py -v`
Expected: 11 passed total.

- [ ] **Step 5: Commit**

```bash
cd /home/daedalus/linux/nexus
git add nexus/load.py tests/test_load.py
git commit -m "feat(load): load_project orchestrator (policy + targeted recall)"
```

---

## Task 5: `nexus load` CLI subcommand

**Files:**
- Modify: `nexus/cli.py` (add subparser + handler)
- Modify: `tests/test_cli.py` (add tests)

Wires `nexus load <project> --topic <text> [--limit N]` and prints the composed output blob from the spec.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_load_subcommand_prints_policy_and_recall(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)

    nexus_root = tmp_path / "nexus_repo"
    policies = nexus_root / "nexus" / "policies"
    (policies / "projects").mkdir(parents=True)
    (policies / "core.md").write_text("# core policy")
    (policies / "projects" / "book.md").write_text("# Writing policy\nShow, don't tell.")

    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    monkeypatch.setattr("nexus.load.mempalace_search", lambda q, **kw: f"hits for: {q}")

    code = cli_main([
        "load", "book",
        "--topic", "chapter 3",
        "--workspace-root", str(workspace),
        "--nexus-root", str(nexus_root),
    ])

    assert code == 0
    out = capsys.readouterr().out
    assert "# Project policy: book" in out
    assert "Show, don't tell." in out
    assert '# Recall hits for "chapter 3"' in out
    assert "hits for: chapter 3" in out


def test_load_subcommand_unknown_project_exits_1(tmp_path, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    workspace.mkdir(parents=True)
    nexus_root = tmp_path / "nexus_repo"
    (nexus_root / "nexus" / "policies" / "projects").mkdir(parents=True)
    (nexus_root / "nexus" / "policies" / "core.md").write_text("core")

    code = cli_main([
        "load", "ghost",
        "--topic", "x",
        "--workspace-root", str(workspace),
        "--nexus-root", str(nexus_root),
    ])

    assert code == 1
    err = capsys.readouterr().err
    assert "ghost" in err


def test_load_subcommand_empty_recall_prints_placeholder(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    nexus_root = tmp_path / "nexus_repo"
    (nexus_root / "nexus" / "policies" / "projects").mkdir(parents=True)
    (nexus_root / "nexus" / "policies" / "core.md").write_text("core")

    monkeypatch.setattr("nexus.load.mempalace_search", lambda q, **kw: "")

    code = cli_main([
        "load", "book",
        "--topic", "x",
        "--workspace-root", str(workspace),
        "--nexus-root", str(nexus_root),
    ])

    assert code == 0
    out = capsys.readouterr().out
    assert "(no prior recall for this topic)" in out


def test_load_subcommand_bootstrap_note_on_missing_project_policy(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    nexus_root = tmp_path / "nexus_repo"
    (nexus_root / "nexus" / "policies" / "projects").mkdir(parents=True)
    (nexus_root / "nexus" / "policies" / "core.md").write_text("# core")

    monkeypatch.setattr("nexus.load.mempalace_search", lambda q, **kw: "")

    code = cli_main([
        "load", "book",
        "--topic", "x",
        "--workspace-root", str(workspace),
        "--nexus-root", str(nexus_root),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "projects/book.md" in out
    assert "using core.md" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_cli.py -v -k load`
Expected: 4 failures (`unrecognized arguments: load`).

- [ ] **Step 3: Wire the subcommand and handler in `nexus/cli.py`**

In `build_parser()`, add this block before `return parser`:

```python
    load_p = subparsers.add_parser(
        "load",
        help="Load per-project policy + targeted recall by topic",
    )
    load_p.add_argument("project", help="Project name (folder under workspace)")
    load_p.add_argument("--topic", required=True, help="Topic query for recall")
    load_p.add_argument("--limit", type=int, default=5)
    load_p.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Workspace root (default: NEXUS_WORKSPACE_ROOT env or auto)",
    )
    load_p.add_argument(
        "--nexus-root",
        type=Path,
        default=default_nexus_root,
    )
    load_p.set_defaults(handler=_handle_load)
```

Then add the handler near `_handle_context`:

```python
def _handle_load(args: argparse.Namespace) -> int:
    from nexus.load import load_project

    workspace_root = (
        Path(args.workspace_root)
        if args.workspace_root is not None
        else NexusConfig.default().workspace_root
    )

    try:
        result = load_project(
            project=args.project,
            topic=args.topic,
            workspace_root=workspace_root,
            nexus_root=Path(args.nexus_root),
            limit=args.limit,
        )
    except ValueError as exc:
        print(f"nexus load: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"nexus load: {exc}", file=sys.stderr)
        return 1

    print(f"# Project policy: {result.project} (source: {result.policy.source})")
    if result.policy.bootstrap_note:
        print(result.policy.bootstrap_note)
    print()
    print(result.policy.text.rstrip())
    print()
    print(f'# Recall hits for "{args.topic}" (wing: {result.wing})')
    if result.memory_unavailable:
        print("(memory unavailable — mempalace binary not found)")
    elif result.recall.strip():
        print(result.recall.rstrip())
    else:
        print("(no prior recall for this topic)")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_cli.py -v -k load`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/daedalus/linux/nexus
git add nexus/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'nexus load <project> --topic' subcommand"
```

---

## Task 6: `nexus list-projects` CLI subcommand

**Files:**
- Modify: `nexus/cli.py` (add subparser + handler)
- Modify: `tests/test_cli.py` (add tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_list_projects_subcommand(tmp_path, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / "miniclaw").mkdir(parents=True)

    nexus_root = tmp_path / "nexus_repo"
    (nexus_root / "nexus" / "policies" / "projects").mkdir(parents=True)
    (nexus_root / "nexus" / "policies" / "core.md").write_text("core")
    (nexus_root / "nexus" / "policies" / "projects" / "book.md").write_text("writing")

    code = cli_main([
        "list-projects",
        "--workspace-root", str(workspace),
        "--nexus-root", str(nexus_root),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "book" in out
    assert "miniclaw" in out
    assert "projects/book.md" in out
    assert "core (default)" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_cli.py -v -k list_projects`
Expected: `unrecognized arguments: list-projects`.

- [ ] **Step 3: Wire subcommand + handler in `nexus/cli.py`**

Add to `build_parser()`:

```python
    lp = subparsers.add_parser("list-projects", help="List workspace projects")
    lp.add_argument("--workspace-root", type=Path, default=None)
    lp.add_argument("--nexus-root", type=Path, default=default_nexus_root)
    lp.set_defaults(handler=_handle_list_projects)
```

Add handler:

```python
def _handle_list_projects(args: argparse.Namespace) -> int:
    from nexus.memory.wings import path_to_wing
    from nexus.projects import list_projects

    workspace_root = (
        Path(args.workspace_root)
        if args.workspace_root is not None
        else NexusConfig.default().workspace_root
    )

    projects = list_projects(workspace_root, nexus_root=Path(args.nexus_root))
    if not projects:
        print("(no projects found)")
        return 0

    rows = [("project", "wing", "policy")]
    for p in projects:
        policy_label = f"projects/{p.name}.md" if p.has_policy else "core (default)"
        rows.append((p.name, path_to_wing(p.path), policy_label))

    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    for r in rows:
        print(f"{r[0]:<{widths[0]}}  {r[1]:<{widths[1]}}  {r[2]:<{widths[2]}}")
    return 0
```

(Drawer counts via `mempalace_list_wings` are out of scope for v1 — added later if useful. The spec's `drawers` column is optional and would require an extra subprocess call per invocation.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_cli.py -v -k list_projects`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/daedalus/linux/nexus
git add nexus/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'nexus list-projects' subcommand"
```

---

## Task 7: Rewrite `nexus context` for lean baseline

**Files:**
- Modify: `nexus/context.py` (add `build_lean_baseline()`)
- Modify: `nexus/cli.py` (rewrite `_handle_context`)
- Modify: `tests/test_context.py`
- Modify: `tests/test_cli.py`

`nexus context` stops emitting an L1 dump. It emits identity (if available) + the available-projects line + the load instruction + local doc snippets.

Identity comes from `~/.mempalace/identity.txt` (per existing project memory: "Per-user identity at `~/.mempalace/identity.txt`"). If absent, the line is simply omitted.

- [ ] **Step 1: Write/update failing tests for `build_lean_baseline`**

Replace the body of `tests/test_context.py` with:

```python
from pathlib import Path

from nexus.context import build_context_summary, build_lean_baseline


def test_builds_combined_summary_from_hits_and_docs():
    summary = build_context_summary(
        recall_hits=["Wake offload was completed", "Use hailo tiny for wake"],
        doc_snippets=["README says wake offload is shipped"],
    )
    assert "Prior session context:" in summary
    assert "Project docs:" in summary
    assert "Wake offload was completed" in summary


def test_collapses_multiline_entries_and_drops_blank_items():
    summary = build_context_summary(
        recall_hits=["  First line\nsecond line  ", "   "],
        doc_snippets=["Doc line one\n\nDoc line two", "\t"],
    )
    assert "First line second line" in summary
    assert "Doc line one Doc line two" in summary


def test_lean_baseline_includes_projects_and_instruction():
    out = build_lean_baseline(
        identity="Mason Misch (M8SON). Builds MiniClaw and Nexus.",
        project_names=["book", "miniclaw", "nexus"],
        doc_snippets=["CLAUDE.md: Nexus-managed workspace"],
    )
    assert "Mason Misch" in out
    assert "Workspace projects available: book, miniclaw, nexus" in out
    assert "nexus load <project> --topic" in out
    assert "Project docs:" in out
    assert "CLAUDE.md" in out


def test_lean_baseline_omits_identity_when_absent():
    out = build_lean_baseline(
        identity=None,
        project_names=["book"],
        doc_snippets=[],
    )
    assert "Mason" not in out
    assert "Workspace projects available: book" in out


def test_lean_baseline_handles_empty_projects():
    out = build_lean_baseline(identity=None, project_names=[], doc_snippets=[])
    assert "no projects found" in out.lower()


def test_agent_adapters_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "nexus" / "adapters" / "claude" / "CLAUDE.md").exists()
    assert (root / "nexus" / "adapters" / "codex" / "AGENTS.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_context.py -v`
Expected: 3 new failures (`ImportError: cannot import name 'build_lean_baseline'`).

- [ ] **Step 3: Implement `build_lean_baseline` in `nexus/context.py`**

Append to `nexus/context.py`:

```python
def build_lean_baseline(
    *,
    identity: str | None,
    project_names: list[str],
    doc_snippets: list[str],
) -> str:
    """Lean SessionStart context: identity + project list + load instruction + docs.

    No L1 essential story. The caller (e.g. SessionStart hook) is expected
    to wait for the user's first message and then run `nexus load`.
    """
    doc_snippets = _clean_entries(doc_snippets)
    sections: list[str] = []

    if identity:
        sections.append(identity.strip())

    if project_names:
        sections.append(
            "Workspace projects available: " + ", ".join(project_names) + "\n"
            "When the user states what they want to work on today, run:\n"
            "  nexus load <project> --topic \"<their message>\"\n"
            "Do not pre-load anything else."
        )
    else:
        sections.append("(no projects found under workspace; nothing to load)")

    if doc_snippets:
        sections.append("Project docs:\n- " + "\n- ".join(doc_snippets))

    return "\n\n".join(sections).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_context.py -v`
Expected: 6 passed.

- [ ] **Step 5: Update the existing CLI integration test for `context`**

Open `tests/test_cli.py` and replace `test_context_assembles_docs_and_recall_hits` with:

```python
def test_context_emits_lean_baseline(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    repo = workspace / "demo"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("Demo project overview", encoding="utf-8")
    (workspace / "other").mkdir()

    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    # No identity file in tmp_path → identity section omitted.
    monkeypatch.setattr("nexus.cli._read_identity_blurb", lambda: None)

    code = cli_main(["context", "--repo-path", str(repo)])
    assert code == 0

    out = capsys.readouterr().out
    assert "Workspace projects available: demo, other" in out
    assert "nexus load <project> --topic" in out
    assert "Project docs:" in out
    assert "Demo project overview" in out
    # The old L1 wake-up dump must not appear.
    assert "Prior session context:" not in out
```

- [ ] **Step 6: Run that test to verify it fails**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/test_cli.py::test_context_emits_lean_baseline -v`
Expected: failure (current `_handle_context` still emits L1 / calls `_mempalace_wake_up`).

- [ ] **Step 7: Rewrite `_handle_context` in `nexus/cli.py`**

Replace the entire `_handle_context` function with:

```python
def _read_identity_blurb() -> str | None:
    """Read `~/.mempalace/identity.txt` if it exists. Empty file → None."""
    path = Path(os.path.expanduser("~")) / ".mempalace" / "identity.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _handle_context(args: argparse.Namespace) -> int:
    from nexus.context import build_lean_baseline
    from nexus.projects import list_projects

    repo_path = Path(args.repo_path).resolve()
    workspace_root = NexusConfig.default().workspace_root.resolve()

    if workspace_root != repo_path and workspace_root not in repo_path.parents:
        # cwd is outside the managed workspace — silent no-op (matches old behavior).
        return 0

    projects = list_projects(workspace_root)
    doc_snippets = [_read_doc_snippet(p) for p in discover_context_docs(repo_path)]
    identity = _read_identity_blurb()

    out = build_lean_baseline(
        identity=identity,
        project_names=[p.name for p in projects],
        doc_snippets=doc_snippets,
    )
    print(out or "No local context found.")
    return 0
```

Also delete the now-unused `_mempalace_wake_up` and `_resolve_mempalace_bin` functions from `cli.py` — they were only used by the old `_handle_context`. (`nexus/load.py` has its own copy of `_resolve_mempalace_bin` from Task 3.)

- [ ] **Step 8: Run all tests to verify nothing else broke**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/pytest tests/ -v`
Expected: all green. If `test_context_assembles_docs_and_recall_hits` had been the only consumer of `_mempalace_wake_up`, removing it is clean. If anything else fails, fix the affected test to use the new shape.

- [ ] **Step 9: Commit**

```bash
cd /home/daedalus/linux/nexus
git add nexus/cli.py nexus/context.py tests/test_cli.py tests/test_context.py
git commit -m "feat(context): emit lean SessionStart baseline (no L1 dump)"
```

---

## Task 8: Manual smoke test

The hook script (`~/.claude/hooks/nexus-session-start.sh`) is unchanged — it still calls `nexus context --repo-path "$CLAUDE_PROJECT_DIR"`. Verify end-to-end.

- [ ] **Step 1: Reinstall the package (editable install picks up new modules)**

```bash
cd /home/daedalus/linux/nexus
.venv/bin/pip install -e . --quiet
```

- [ ] **Step 2: Smoke-test `nexus context` from the workspace root**

```bash
cd /home/daedalus/linux/nexus
.venv/bin/python -m nexus.cli context --repo-path /home/daedalus/linux
```

Expected output contains:
- Identity blurb (if `~/.mempalace/identity.txt` exists)
- A line: `Workspace projects available: <names>`
- The instruction line: `nexus load <project> --topic "<their message>"`
- No "Prior session context:" line.

- [ ] **Step 3: Smoke-test `nexus list-projects`**

```bash
.venv/bin/python -m nexus.cli list-projects
```

Expected: a table with one row per workspace project.

- [ ] **Step 4: Smoke-test `nexus load` against the nexus project itself**

```bash
.venv/bin/python -m nexus.cli load nexus --topic "where we left off"
```

Expected:
- `# Project policy: nexus (source: core.md)` (with bootstrap note about `projects/nexus.md`)
- `core.md` contents
- `# Recall hits for "where we left off" (wing: _home_daedalus_linux_nexus)`
- Either real mempalace hits or `(no prior recall for this topic)`.

- [ ] **Step 5: Smoke-test against an unknown project**

```bash
.venv/bin/python -m nexus.cli load ghost --topic "x"
echo "exit=$?"
```

Expected: stderr line `nexus load: project 'ghost' not found under ...`, exit 1.

- [ ] **Step 6: Start a fresh Claude Code session under `~/linux/` and confirm**

In a separate terminal:
```bash
cd /home/daedalus/linux && claude
```

In the session, observe the SessionStart wake-up text. It should match the lean baseline format (no L1 essential story dump). Then say "Let's work on nexus" and verify Claude runs `nexus load nexus --topic "..."`.

- [ ] **Step 7: No commit (this task is verification only)**

If smoke tests pass, the implementation is complete.

---

## Notes for future work (out of scope)

- **Per-project drawer counts in `list-projects`** — call `mempalace_list_wings` and join by wing name. Useful but adds a subprocess call.
- **`book.md` policy file** — the user will write this when they create the book project. The bootstrap note guides them.
- **Codex CLI integration** — Codex has no UserPromptSubmit hook (per existing project memory), but `nexus load` is portable and the user can run it manually or via an alias.
- **Auto-create new project dirs** — explicitly out of scope (spec).
- **Sticky project resume** — explicitly out of scope (spec).
