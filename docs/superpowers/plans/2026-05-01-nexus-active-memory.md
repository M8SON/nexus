# Nexus Active Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire MemPalace into Claude Code and Codex as nexus's memory engine, retire the BM25 layer, and codify a per-repo wing convention with storage redirected into `~/linux/nexus/data/`.

**Architecture:** Nexus becomes a small nexus that defines the cwd-to-wing convention, owns hook installation across both agents, and redirects MemPalace's bulk storage into the nexus tree. MemPalace is the engine; nexus is the conventions and wiring. The BM25 layer is removed because MemPalace's recall fully replaces it.

**Tech Stack:** Python 3.12, argparse, sqlite3 (still used for nexus config), MemPalace CLI (subprocess), bash hook scripts, Claude Code hook system, Codex CLI hook system.

**Spec:** `docs/superpowers/specs/2026-05-01-nexus-active-memory-design.md`

---

## File Structure

**Create:**
- `nexus/memory/__init__.py` — package marker
- `nexus/memory/wings.py` — `resolve_wing(cwd) -> str | None`
- `nexus/memory/env.py` — `mempalace_env(wing, repo_root) -> dict[str, str]`
- `nexus/memory/install.py` — `init()`, `install_claude_hooks()`, `install_codex_hooks()`, settings-merge helpers
- `nexus/memory/status.py` — `status_report()` for the CLI subcommand
- `tests/test_wings.py`, `tests/test_env.py`, `tests/test_install.py`, `tests/test_status.py`
- `tests/test_smoke_mempalace.py` — slow end-to-end against a real palace
- `hooks/nexus-user-prompt-submit.sh` — checked-in source for the new hook script

**Modify:**
- `nexus/cli.py` — gain `memory` subcommand group; remove `recall`/`index`/`stats`
- `nexus/context.py` — rewrite to mock-friendly subprocess call to `mempalace wake-up`
- `nexus/policies/continuity.md` — concrete recall/save triggers
- `tests/test_cli.py` — drop legacy cases, add new ones
- `tests/test_context.py` — mock `mempalace wake-up` instead of BM25
- `.gitignore` — add `data/`
- `WORKING_MEMORY.md` — phase-2 status

**Delete:**
- `nexus/db.py`, `nexus/query.py`, `nexus/indexer.py`
- `tests/test_query.py`, `tests/test_indexer.py`
- `~/.claude/tools/nexus/nexus.db` (data file, deleted at install time)

---

## Task 1: Create `nexus/memory/` package skeleton

**Files:**
- Create: `nexus/memory/__init__.py`

- [ ] **Step 1: Create the package directory and empty init**

```bash
mkdir -p /home/daedalus/linux/nexus/nexus/memory
```

Then create `/home/daedalus/linux/nexus/nexus/memory/__init__.py` with:

```python
"""Nexus memory orchestration. Wires MemPalace into both supported agents."""
```

- [ ] **Step 2: Verify the package imports**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -c "import nexus.memory"`
Expected: exits 0 with no output.

- [ ] **Step 3: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/__init__.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): scaffold nexus.memory subpackage"
```

---

## Task 2: `wings.resolve_wing` — happy path

**Files:**
- Create: `nexus/memory/wings.py`
- Test: `tests/test_wings.py`

- [ ] **Step 1: Write the failing test**

Create `/home/daedalus/linux/nexus/tests/test_wings.py`:

```python
"""Tests for cwd → wing-name resolution."""
from pathlib import Path

import pytest

from nexus.memory.wings import resolve_wing


@pytest.mark.parametrize("cwd, expected", [
    ("/home/daedalus/linux/nexus", "nexus"),
    ("/home/daedalus/linux/nexus/nexus/memory", "nexus"),
    ("/home/daedalus/linux/miniclaw", "miniclaw"),
    ("/home/daedalus/linux/miniclaw/skills/dashboard", "miniclaw"),
])
def test_managed_repo_yields_repo_name(cwd, expected):
    assert resolve_wing(Path(cwd)) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_wings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nexus.memory.wings'`.

- [ ] **Step 3: Write minimal implementation**

Create `/home/daedalus/linux/nexus/nexus/memory/wings.py`:

```python
"""Resolve a cwd to a MemPalace wing name."""
from pathlib import Path

from nexus.config import NexusConfig


def resolve_wing(cwd: Path, config: NexusConfig | None = None) -> str | None:
    """Return the wing name for `cwd`, or None if `cwd` is not managed.

    - cwd at /home/daedalus/linux/<repo>/... → wing = <repo>
    - cwd at /home/daedalus/linux             → wing = "workspace"
    - anywhere else                            → None
    """
    config = config or NexusConfig.default()
    workspace = config.workspace_root.resolve()
    cwd = Path(cwd).resolve()

    if cwd == workspace:
        return "workspace"
    if workspace not in cwd.parents:
        return None

    relative = cwd.relative_to(workspace)
    return _normalize(relative.parts[0])


def _normalize(name: str) -> str:
    """Match MemPalace's wing-name normalization: lower + collapse - and space to _."""
    return name.lower().replace(" ", "_").replace("-", "_")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_wings.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/wings.py tests/test_wings.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): resolve cwd to wing name for managed repos"
```

---

## Task 3: `wings.resolve_wing` — edge cases

**Files:**
- Modify: `tests/test_wings.py`
- Modify: `nexus/memory/wings.py` (only if tests fail)

- [ ] **Step 1: Add edge-case tests**

Append to `tests/test_wings.py`:

```python
def test_workspace_root_yields_workspace_wing():
    assert resolve_wing(Path("/home/daedalus/linux")) == "workspace"


def test_outside_workspace_yields_none():
    assert resolve_wing(Path("/tmp")) is None
    assert resolve_wing(Path("/home/daedalus")) is None


def test_repo_name_with_dashes_is_normalized(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "my-cool-repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    assert resolve_wing(repo) == "my_cool_repo"


def test_symlink_resolving_back_into_workspace_is_managed(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "real-repo"
    repo.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.symlink_to(repo)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    assert resolve_wing(elsewhere) == "real_repo"
```

- [ ] **Step 2: Run tests and verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_wings.py -v`
Expected: PASS — all cases. The implementation already handles these via `Path.resolve()` and `_normalize()`. No code change needed.

- [ ] **Step 3: Commit**

```bash
git -C /home/daedalus/linux/nexus add tests/test_wings.py
git -C /home/daedalus/linux/nexus commit -m "test(memory): cover workspace root, outside, dashes, symlinks"
```

---

## Task 4: `env.mempalace_env`

**Files:**
- Create: `nexus/memory/env.py`
- Test: `tests/test_env.py`

- [ ] **Step 1: Write the failing test**

Create `/home/daedalus/linux/nexus/tests/test_env.py`:

```python
"""Tests for MemPalace env-var assembly."""
from pathlib import Path

from nexus.memory.env import mempalace_env


def test_env_contains_palace_path_state_dir_repo_dir(tmp_path):
    repo = tmp_path / "linux" / "nexus"
    repo.mkdir(parents=True)
    env = mempalace_env(wing="nexus", repo_root=repo, nexus_root=tmp_path / "nexus_root")

    assert env["MEMPALACE_PALACE_PATH"] == str(tmp_path / "nexus_root" / "data" / "palace")
    assert env["STATE_DIR"] == str(tmp_path / "nexus_root" / "data" / "hook_state")
    assert env["MEMPAL_DIR"] == str(repo)


def test_env_returns_strings_only():
    env = mempalace_env(wing="nexus", repo_root=Path("/tmp"), nexus_root=Path("/tmp/f"))
    assert all(isinstance(v, str) for v in env.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_env.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `/home/daedalus/linux/nexus/nexus/memory/env.py`:

```python
"""Assemble env-var blocks for MemPalace invocations."""
from pathlib import Path


NEXUS_ROOT_DEFAULT = Path("/home/daedalus/linux/nexus")


def mempalace_env(
    wing: str,
    repo_root: Path,
    nexus_root: Path | None = None,
) -> dict[str, str]:
    """Env block to pass when invoking MemPalace under nexus."""
    root = Path(nexus_root or NEXUS_ROOT_DEFAULT)
    return {
        "MEMPALACE_PALACE_PATH": str(root / "data" / "palace"),
        "STATE_DIR": str(root / "data" / "hook_state"),
        "MEMPAL_DIR": str(Path(repo_root)),
    }
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_env.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/env.py tests/test_env.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): assemble MemPalace env-var block"
```

---

## Task 5: `install.merge_claude_hooks` — idempotent settings.json merge

**Files:**
- Create: `nexus/memory/install.py`
- Test: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Create `/home/daedalus/linux/nexus/tests/test_install.py`:

```python
"""Tests for hook installation into Claude/Codex settings."""
import json
from pathlib import Path

from nexus.memory.install import merge_claude_hooks


HOOK_SCRIPT = "/abs/path/mempal_save_hook.sh"
PRECOMPACT_SCRIPT = "/abs/path/mempal_precompact_hook.sh"
USERPROMPT_SCRIPT = "/abs/path/nexus-user-prompt-submit.sh"


def test_merge_into_empty_settings_adds_three_hooks(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")

    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "Stop" in data["hooks"]
    assert "PreCompact" in data["hooks"]
    assert "UserPromptSubmit" in data["hooks"]


def test_merge_is_idempotent(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")

    for _ in range(2):
        merge_claude_hooks(
            settings_path=settings,
            save_hook=HOOK_SCRIPT,
            precompact_hook=PRECOMPACT_SCRIPT,
            user_prompt_hook=USERPROMPT_SCRIPT,
        )

    data = json.loads(settings.read_text(encoding="utf-8"))
    for event in ("Stop", "PreCompact", "UserPromptSubmit"):
        entries = data["hooks"][event]
        # Each event has at most one entry containing our command.
        matching = [e for e in entries if any(
            HOOK_SCRIPT in str(h.get("command", ""))
            or PRECOMPACT_SCRIPT in str(h.get("command", ""))
            or USERPROMPT_SCRIPT in str(h.get("command", ""))
            for h in (e.get("hooks") or [e])
        )]
        assert len(matching) == 1, f"{event} duplicated on second merge"


def test_merge_preserves_existing_unrelated_hook(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "hooks": {
            "SessionStart": [{
                "matcher": "startup",
                "hooks": [{"type": "command", "command": "/keep/me.sh"}],
            }]
        }
    }), encoding="utf-8")

    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "/keep/me.sh"


def test_merge_writes_backup_before_change(tmp_path):
    settings = tmp_path / "settings.json"
    original = '{"hooks": {}}'
    settings.write_text(original, encoding="utf-8")

    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )

    backup = settings.with_suffix(settings.suffix + ".bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py -v`
Expected: FAIL — module `nexus.memory.install` not found.

- [ ] **Step 3: Write minimal implementation**

Create `/home/daedalus/linux/nexus/nexus/memory/install.py`:

```python
"""Install MemPalace + nexus hooks into Claude Code and Codex CLI configs."""
import json
import shutil
from pathlib import Path


def merge_claude_hooks(
    *,
    settings_path: Path,
    save_hook: str,
    precompact_hook: str,
    user_prompt_hook: str,
) -> None:
    """Idempotently add Stop, PreCompact, UserPromptSubmit hooks to a settings.json."""
    settings_path = Path(settings_path)
    raw = settings_path.read_text(encoding="utf-8") if settings_path.exists() else "{}"
    backup = settings_path.with_suffix(settings_path.suffix + ".bak")
    if settings_path.exists():
        shutil.copyfile(settings_path, backup)

    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}

    hooks = data.setdefault("hooks", {})
    _ensure_hook(hooks, "Stop", save_hook, matcher="*")
    _ensure_hook(hooks, "PreCompact", precompact_hook, matcher=None)
    _ensure_hook(hooks, "UserPromptSubmit", user_prompt_hook, matcher=None)

    settings_path.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def _ensure_hook(
    hooks: dict, event: str, command: str, *, matcher: str | None
) -> None:
    """Append a hook entry only if no entry already has this command for this event."""
    entries = hooks.setdefault(event, [])
    for entry in entries:
        for h in entry.get("hooks", [entry]):
            if str(h.get("command", "")) == command:
                return
    entry: dict = {
        "hooks": [{"type": "command", "command": command, "timeout": 30}],
    }
    if matcher is not None:
        entry["matcher"] = matcher
    entries.append(entry)
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/install.py tests/test_install.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): idempotent claude hooks merge with .bak"
```

---

## Task 6: `install.write_codex_hooks`

**Files:**
- Modify: `nexus/memory/install.py`
- Modify: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_install.py`:

```python
from nexus.memory.install import write_codex_hooks


def test_codex_hooks_written_with_save_and_precompact(tmp_path):
    target = tmp_path / "hooks.json"
    write_codex_hooks(
        target=target,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
    )

    data = json.loads(target.read_text(encoding="utf-8"))
    assert any(e["command"] == HOOK_SCRIPT for e in data["Stop"])
    assert any(e["command"] == PRECOMPACT_SCRIPT for e in data["PreCompact"])


def test_codex_hooks_idempotent(tmp_path):
    target = tmp_path / "hooks.json"
    for _ in range(2):
        write_codex_hooks(
            target=target,
            save_hook=HOOK_SCRIPT,
            precompact_hook=PRECOMPACT_SCRIPT,
        )

    data = json.loads(target.read_text(encoding="utf-8"))
    assert sum(1 for e in data["Stop"] if e["command"] == HOOK_SCRIPT) == 1
    assert sum(1 for e in data["PreCompact"] if e["command"] == PRECOMPACT_SCRIPT) == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py -v`
Expected: FAIL — `write_codex_hooks` not defined.

- [ ] **Step 3: Add implementation**

Append to `nexus/memory/install.py`:

```python
def write_codex_hooks(
    *, target: Path, save_hook: str, precompact_hook: str
) -> None:
    """Idempotently write/merge ~/.codex/hooks.json."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copyfile(target, backup)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    _add_codex_entry(data, "Stop", save_hook)
    _add_codex_entry(data, "PreCompact", precompact_hook)

    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _add_codex_entry(data: dict, event: str, command: str) -> None:
    entries = data.setdefault(event, [])
    for entry in entries:
        if str(entry.get("command", "")) == command:
            return
    entries.append({"type": "command", "command": command, "timeout": 30})
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/install.py tests/test_install.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): idempotent codex hooks.json writer"
```

---

## Task 7: `install.locate_mempalace_hooks`

**Files:**
- Modify: `nexus/memory/install.py`
- Modify: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_install.py`:

```python
from nexus.memory.install import locate_mempalace_hooks


def test_locate_mempalace_hooks_finds_via_python_import(tmp_path, monkeypatch):
    fake_pkg = tmp_path / "mempalace"
    fake_pkg.mkdir()
    (fake_pkg / "__init__.py").write_text("", encoding="utf-8")
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "mempal_save_hook.sh").write_text("#!/bin/bash", encoding="utf-8")
    (hooks_dir / "mempal_precompact_hook.sh").write_text("#!/bin/bash", encoding="utf-8")

    save, precompact = locate_mempalace_hooks(repo_root=tmp_path)

    assert save == hooks_dir / "mempal_save_hook.sh"
    assert precompact == hooks_dir / "mempal_precompact_hook.sh"


def test_locate_raises_when_not_found(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        locate_mempalace_hooks(repo_root=tmp_path)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py::test_locate_mempalace_hooks_finds_via_python_import tests/test_install.py::test_locate_raises_when_not_found -v`
Expected: FAIL — function not defined.

- [ ] **Step 3: Add implementation**

Append to `nexus/memory/install.py`:

```python
def locate_mempalace_hooks(*, repo_root: Path) -> tuple[Path, Path]:
    """Find MemPalace's shipped hook scripts under repo_root.

    Looks for `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh`
    relative to repo_root. Designed for when the user has cloned the MemPalace
    repo locally; supplied via --mempalace-repo on the CLI in production.
    """
    repo_root = Path(repo_root)
    save = repo_root / "hooks" / "mempal_save_hook.sh"
    precompact = repo_root / "hooks" / "mempal_precompact_hook.sh"
    if not save.exists() or not precompact.exists():
        raise FileNotFoundError(
            f"MemPalace hooks not found under {repo_root}/hooks. "
            f"Pass --mempalace-repo to nexus memory init."
        )
    return save, precompact
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/install.py tests/test_install.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): locate mempalace hook scripts under a repo root"
```

---

## Task 8: `install.init` orchestration

**Files:**
- Modify: `nexus/memory/install.py`
- Modify: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_install.py`:

```python
from nexus.memory.install import init


def test_init_creates_data_dirs_and_merges_settings(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    nexus_root = workspace / "nexus"
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    mempalace = tmp_path / "mempalace_repo"
    (mempalace / "hooks").mkdir(parents=True)
    (mempalace / "hooks" / "mempal_save_hook.sh").write_text("#!/bin/bash", encoding="utf-8")
    (mempalace / "hooks" / "mempal_precompact_hook.sh").write_text("#!/bin/bash", encoding="utf-8")

    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))
    user_prompt_hook = tmp_path / "nexus-user-prompt-submit.sh"
    user_prompt_hook.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")

    result = init(
        repo=repo,
        mempalace_repo=mempalace,
        nexus_root=nexus_root,
        user_prompt_hook=user_prompt_hook,
        skip_backfill=True,
    )

    assert result["wing"] == "nexus"
    assert (nexus_root / "data" / "palace").is_dir()
    assert (nexus_root / "data" / "hook_state").is_dir()
    assert (fake_home / ".claude" / "settings.json").exists()
    assert (fake_home / ".codex" / "hooks.json").exists()


def test_init_refuses_when_cwd_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    workspace.mkdir()
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    import pytest
    with pytest.raises(ValueError, match="not under workspace"):
        init(
            repo=tmp_path / "outside",
            mempalace_repo=tmp_path / "mempalace_repo",
            nexus_root=workspace / "nexus",
            user_prompt_hook=tmp_path / "u.sh",
            skip_backfill=True,
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py::test_init_creates_data_dirs_and_merges_settings tests/test_install.py::test_init_refuses_when_cwd_outside_workspace -v`
Expected: FAIL — `init` not defined.

- [ ] **Step 3: Add implementation**

Append to `nexus/memory/install.py`:

```python
import os

from nexus.memory.wings import resolve_wing


def init(
    *,
    repo: Path,
    mempalace_repo: Path,
    nexus_root: Path,
    user_prompt_hook: Path,
    skip_backfill: bool = False,
) -> dict:
    """Top-level install: data dirs, claude/codex hook merges, optional backfill."""
    repo = Path(repo).resolve()
    nexus_root = Path(nexus_root)
    wing = resolve_wing(repo)
    if wing is None:
        raise ValueError(f"{repo} is not under workspace")

    (nexus_root / "data" / "palace").mkdir(parents=True, exist_ok=True)
    (nexus_root / "data" / "hook_state").mkdir(parents=True, exist_ok=True)

    save, precompact = locate_mempalace_hooks(repo_root=mempalace_repo)

    home = Path(os.path.expanduser("~"))
    claude_settings = home / ".claude" / "settings.json"
    claude_settings.parent.mkdir(parents=True, exist_ok=True)
    if not claude_settings.exists():
        claude_settings.write_text("{}", encoding="utf-8")
    merge_claude_hooks(
        settings_path=claude_settings,
        save_hook=str(save),
        precompact_hook=str(precompact),
        user_prompt_hook=str(user_prompt_hook),
    )

    codex_hooks = home / ".codex" / "hooks.json"
    write_codex_hooks(
        target=codex_hooks,
        save_hook=str(save),
        precompact_hook=str(precompact),
    )

    backfill_done = False
    marker = nexus_root / "data" / "backfill_markers" / f"{wing}.done"
    if not skip_backfill and not marker.exists():
        # Backfill is best-effort; failure does not undo the install.
        marker.parent.mkdir(parents=True, exist_ok=True)
        backfill_done = _run_backfill(wing=wing, marker=marker)

    return {
        "wing": wing,
        "claude_settings": str(claude_settings),
        "codex_hooks": str(codex_hooks),
        "backfill_done": backfill_done,
    }


def _run_backfill(wing: str, marker: Path) -> bool:
    """One-time mine of past Claude + Codex transcripts into this wing."""
    import subprocess
    home = Path(os.path.expanduser("~"))
    targets = [
        home / ".claude" / "projects",
        home / ".codex" / "sessions",
    ]
    ok = True
    for target in targets:
        if not target.exists():
            continue
        try:
            subprocess.run(
                ["mempalace", "mine", str(target), "--mode", "convos", "--wing", wing],
                check=True,
                timeout=600,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            ok = False
    if ok:
        marker.write_text("done\n", encoding="utf-8")
    return ok
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS — 10 tests.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/install.py tests/test_install.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): nexus memory init orchestration"
```

---

## Task 9: UserPromptSubmit hook script

**Files:**
- Create: `hooks/nexus-user-prompt-submit.sh`

- [ ] **Step 1: Create the hook script**

Create `/home/daedalus/linux/nexus/hooks/nexus-user-prompt-submit.sh`:

```bash
#!/usr/bin/env bash
# Nexus UserPromptSubmit hook. Prepends mempalace search hits to the user's
# prompt as additional context. Best-effort: any failure produces empty
# injection, never a dropped prompt.

set -e

WING="${NEXUS_WING:-}"
[ -n "$WING" ] || exit 0

# Read the prompt from stdin (Claude Code passes it as JSON).
PAYLOAD="$(cat)"
PROMPT="$(printf '%s' "$PAYLOAD" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("user_prompt",""))' 2>/dev/null || true)"
[ -n "$PROMPT" ] || { printf '%s' "$PAYLOAD"; exit 0; }

LOG_DIR="$HOME/.cache/nexus"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="$LOG_DIR/user-prompt-hook.log"

HITS="$(timeout 5 mempalace search "$PROMPT" --wing "$WING" --results 3 2>>"$LOG" || true)"
if [ -z "$HITS" ]; then
    printf '%s' "$PAYLOAD"
    exit 0
fi

# Append hits as additional context. Claude Code's UserPromptSubmit hook
# expects the JSON payload back on stdout with optional `additional_context`.
printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
data = json.load(sys.stdin)
data['additional_context'] = '''Prior session hits:
$HITS'''
print(json.dumps(data))
" 2>>"$LOG" || printf '%s' "$PAYLOAD"
```

- [ ] **Step 2: Make the script executable**

Run: `chmod +x /home/daedalus/linux/nexus/hooks/nexus-user-prompt-submit.sh`
Expected: exits 0.

- [ ] **Step 3: Smoke-test the script in failure mode**

Run: `echo '{"user_prompt":"hello"}' | NEXUS_WING=test /home/daedalus/linux/nexus/hooks/nexus-user-prompt-submit.sh`
Expected: prints back the original JSON unchanged because `mempalace` is either missing or returns empty for an empty palace.

- [ ] **Step 4: Commit**

```bash
git -C /home/daedalus/linux/nexus add hooks/nexus-user-prompt-submit.sh
git -C /home/daedalus/linux/nexus commit -m "feat(hooks): user-prompt-submit hook injects mempalace hits"
```

---

## Task 10: `nexus memory init` CLI subcommand

**Files:**
- Modify: `nexus/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_memory_init_invokes_install(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    mempalace = tmp_path / "mempalace_repo"
    (mempalace / "hooks").mkdir(parents=True)
    (mempalace / "hooks" / "mempal_save_hook.sh").write_text("#!/bin/bash", encoding="utf-8")
    (mempalace / "hooks" / "mempal_precompact_hook.sh").write_text("#!/bin/bash", encoding="utf-8")

    user_prompt_hook = tmp_path / "u.sh"
    user_prompt_hook.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")

    code = cli_main([
        "memory", "init",
        "--mempalace-repo", str(mempalace),
        "--nexus-root", str(workspace / "nexus"),
        "--user-prompt-hook", str(user_prompt_hook),
        "--skip-backfill",
    ])
    assert code == 0
    output = capsys.readouterr().out
    assert "wing: nexus" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_cli.py::test_memory_init_invokes_install -v`
Expected: FAIL — argparse rejects unknown subcommand `memory`.

- [ ] **Step 3: Add the subcommand to `nexus/cli.py`**

Add inside `build_parser()` (after the existing parsers, before `return parser`):

```python
    memory = subparsers.add_parser("memory", help="MemPalace orchestration")
    memory_sub = memory.add_subparsers(dest="memory_command")

    mem_init = memory_sub.add_parser("init", help="Wire MemPalace into both agents")
    mem_init.add_argument("--repo", type=Path, default=None,
                          help="Repo to initialize the wing for (default: cwd)")
    mem_init.add_argument("--mempalace-repo", type=Path, required=True,
                          help="Path to a local MemPalace clone (for hook scripts)")
    mem_init.add_argument("--nexus-root", type=Path,
                          default=Path("/home/daedalus/linux/nexus"),
                          help="Root of the nexus repo (where data/ lives)")
    mem_init.add_argument("--user-prompt-hook", type=Path, required=True,
                          help="Path to the nexus UserPromptSubmit hook script")
    mem_init.add_argument("--skip-backfill", action="store_true")
    mem_init.set_defaults(handler=_handle_memory_init)
```

Also add the handler:

```python
def _handle_memory_init(args: argparse.Namespace) -> int:
    from nexus.memory.install import init as install_init

    repo = Path(args.repo) if args.repo else Path.cwd()
    try:
        result = install_init(
            repo=repo,
            mempalace_repo=Path(args.mempalace_repo),
            nexus_root=Path(args.nexus_root),
            user_prompt_hook=Path(args.user_prompt_hook),
            skip_backfill=args.skip_backfill,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"nexus memory init failed: {exc}", file=sys.stderr)
        return 1

    print(f"wing: {result['wing']}")
    print(f"claude settings: {result['claude_settings']}")
    print(f"codex hooks:     {result['codex_hooks']}")
    print(f"backfill done:   {result['backfill_done']}")
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_cli.py::test_memory_init_invokes_install -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/cli.py tests/test_cli.py
git -C /home/daedalus/linux/nexus commit -m "feat(cli): nexus memory init subcommand"
```

---

## Task 11: `nexus memory status` CLI subcommand

**Files:**
- Create: `nexus/memory/status.py`
- Modify: `nexus/cli.py`
- Create: `tests/test_status.py`

- [ ] **Step 1: Write the failing test**

Create `/home/daedalus/linux/nexus/tests/test_status.py`:

```python
"""Tests for `nexus memory status`."""
from pathlib import Path

from nexus.memory.status import status_report


def test_status_reports_palace_existence(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    nexus_root = workspace / "nexus"
    (nexus_root / "data" / "palace").mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    report = status_report(repo=repo, nexus_root=nexus_root)
    assert report["wing"] == "nexus"
    assert report["palace_exists"] is True


def test_status_handles_missing_palace(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    report = status_report(repo=repo, nexus_root=workspace / "nope")
    assert report["palace_exists"] is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_status.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `status.py`**

Create `/home/daedalus/linux/nexus/nexus/memory/status.py`:

```python
"""Read-only status report for `nexus memory status`."""
import os
import shutil
from pathlib import Path

from nexus.memory.wings import resolve_wing


def status_report(*, repo: Path, nexus_root: Path) -> dict:
    repo = Path(repo).resolve()
    nexus_root = Path(nexus_root)
    palace = nexus_root / "data" / "palace"
    home = Path(os.path.expanduser("~"))

    return {
        "wing": resolve_wing(repo),
        "palace_path": str(palace),
        "palace_exists": palace.is_dir(),
        "claude_settings": str(home / ".claude" / "settings.json"),
        "claude_settings_exists": (home / ".claude" / "settings.json").exists(),
        "codex_hooks": str(home / ".codex" / "hooks.json"),
        "codex_hooks_exists": (home / ".codex" / "hooks.json").exists(),
        "mempalace_on_path": shutil.which("mempalace") is not None,
    }
```

- [ ] **Step 4: Wire into CLI**

Add to `nexus/cli.py` inside the `memory_sub` block (after `mem_init` registration):

```python
    mem_status = memory_sub.add_parser("status", help="Report memory wiring state")
    mem_status.add_argument("--repo", type=Path, default=None)
    mem_status.add_argument("--nexus-root", type=Path,
                            default=Path("/home/daedalus/linux/nexus"))
    mem_status.set_defaults(handler=_handle_memory_status)
```

And the handler:

```python
def _handle_memory_status(args: argparse.Namespace) -> int:
    from nexus.memory.status import status_report
    repo = Path(args.repo) if args.repo else Path.cwd()
    report = status_report(repo=repo, nexus_root=Path(args.nexus_root))
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0
```

- [ ] **Step 5: Run tests and verify pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_status.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/memory/status.py nexus/cli.py tests/test_status.py
git -C /home/daedalus/linux/nexus commit -m "feat(memory): nexus memory status subcommand"
```

---

## Task 12: Rewrite `nexus context` to use `mempalace wake-up`

**Files:**
- Modify: `nexus/cli.py` (`_handle_context`)
- Modify: `tests/test_cli.py` (replace BM25-mocking cases)

- [ ] **Step 1: Update the test to expect mempalace wake-up output**

Replace the body of `test_context_assembles_docs_and_recall_hits` in `tests/test_cli.py`:

```python
def test_context_assembles_docs_and_recall_hits(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    repo = workspace / "demo"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("Wake offload overview", encoding="utf-8")
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    captured_calls = []
    def fake_wake_up(wing, env):
        captured_calls.append((wing, env))
        return "Wake offload was completed"
    monkeypatch.setattr("nexus.cli._mempalace_wake_up", fake_wake_up)

    code = cli_main(["context", "wake", "--repo-path", str(repo)])
    assert code == 0

    output = capsys.readouterr().out
    assert "Prior session context:" in output
    assert "Wake offload was completed" in output
    assert "Project docs:" in output
    assert "Wake offload overview" in output
    assert captured_calls and captured_calls[0][0] == "demo"
```

Also delete the existing `test_context_refreshes_from_transcripts_before_query` — `nexus context` no longer indexes transcripts.

- [ ] **Step 2: Run the test to verify failure**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_cli.py::test_context_assembles_docs_and_recall_hits -v`
Expected: FAIL — `_mempalace_wake_up` not defined.

- [ ] **Step 3: Rewrite `_handle_context` and add `_mempalace_wake_up`**

In `nexus/cli.py`, replace `_handle_context`:

```python
def _handle_context(args: argparse.Namespace) -> int:
    from nexus.memory.wings import resolve_wing
    from nexus.memory.env import mempalace_env

    repo_path = Path(args.repo_path).resolve()
    wing = resolve_wing(repo_path)

    recall_hits: list[str] = []
    if wing:
        env = mempalace_env(wing=wing, repo_root=repo_path)
        try:
            output = _mempalace_wake_up(wing=wing, env=env)
        except Exception:
            output = ""
        if output.strip():
            recall_hits = [output.strip()]

    doc_snippets = [_read_doc_snippet(p) for p in discover_context_docs(repo_path)]
    summary = build_context_summary(recall_hits=recall_hits, doc_snippets=doc_snippets)
    print(summary or "No local context found.")
    return 0


def _mempalace_wake_up(wing: str, env: dict[str, str]) -> str:
    """Run `mempalace wake-up --wing <wing>` with a 10s timeout. Empty on failure."""
    import subprocess
    full_env = {**os.environ, **env}
    try:
        proc = subprocess.run(
            ["mempalace", "wake-up", "--wing", wing],
            capture_output=True, text=True, timeout=10, env=full_env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout
```

Remove `update(conn, ...)` calls and the `_db()` helper from this handler. The function no longer uses sqlite.

- [ ] **Step 4: Run the test to verify pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS — `test_context_assembles_docs_and_recall_hits` passes; the deleted test is gone; the rest still pass.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/cli.py tests/test_cli.py
git -C /home/daedalus/linux/nexus commit -m "feat(context): use mempalace wake-up instead of BM25"
```

---

## Task 13: Rewrite `nexus/policies/continuity.md`

**Files:**
- Modify: `nexus/policies/continuity.md`

- [ ] **Step 1: Replace the file body**

Overwrite `/home/daedalus/linux/nexus/nexus/policies/continuity.md` with:

```markdown
# Continuity Policy

Memory is a tool you reach for, not a passive store. These rules govern when to recall and when to save.

## Recall

At session start, the SessionStart hook injects `mempalace wake-up --wing <wing>` for the active repo, plus local-doc snippets. You start every substantive session with that context in front of you. Read it before you act.

When the user references prior work, when you are about to make a design decision, when the task looks like a continuation, or when you find yourself stuck or repeating yourself: call `mempalace_search` scoped to the active wing first. Do this before re-reading files you have read this session, and before asking the user a question that prior context might already answer.

If a search returns nothing useful, broaden once: drop the wing scope or rephrase the query. Do not loop indefinitely.

## Save

The Save hook auto-mines transcripts and asks you to confirm topics, decisions, and direct quotes every 15 messages. Comply. The PreCompact hook fires the same path right before context compaction; comply there too without arguing about it being unnecessary.

Save durable facts: decisions made and their reasons, constraints the user cares about, user preferences expressed firmly, project state changes that outlast this session. Do not save ephemeral state: which files you just edited, what tests passed, the current cwd.

If you discover a fact mid-task that meets the durable bar — call the appropriate save tool yourself rather than waiting for the next hook fire.

## Wing scoping

Always pass the active repo's wing in `mempalace_search` and `mempalace_wake_up` calls unless you are explicitly broadening. Cross-wing search is for when the user names another project, or when you suspect prior context lives elsewhere.
```

- [ ] **Step 2: Verify the existing tests still pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest -q`
Expected: PASS — no test reads `continuity.md` directly.

- [ ] **Step 3: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/policies/continuity.md
git -C /home/daedalus/linux/nexus commit -m "docs(policy): concrete recall and save triggers in continuity.md"
```

---

## Task 14: Smoke test against a real palace

**Files:**
- Create: `tests/test_smoke_mempalace.py`

- [ ] **Step 1: Write the smoke test**

Create `/home/daedalus/linux/nexus/tests/test_smoke_mempalace.py`:

```python
"""End-to-end smoke test against a real MemPalace install. Slow; opt-in."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("mempalace") is None,
    reason="mempalace CLI not on PATH",
)


def test_wake_up_returns_text_after_mining_a_fixture(tmp_path):
    palace = tmp_path / "palace"
    state = tmp_path / "state"
    palace.mkdir()
    state.mkdir()

    fixture = tmp_path / "fixture.jsonl"
    fixture.write_text(
        '{"type":"user","sessionId":"s1","cwd":"/x","gitBranch":"main",'
        '"timestamp":"2026-04-30T00:00:00Z","uuid":"u1","parentUuid":null,'
        '"message":{"role":"user","content":"the wake offload is on the hailo"}}'
        "\n", encoding="utf-8",
    )

    env = {**os.environ,
           "MEMPALACE_PALACE_PATH": str(palace),
           "STATE_DIR": str(state)}

    subprocess.run(
        ["mempalace", "mine", str(tmp_path), "--mode", "convos", "--wing", "smoke"],
        env=env, check=True, timeout=120,
    )

    proc = subprocess.run(
        ["mempalace", "wake-up", "--wing", "smoke"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert "wake offload" in proc.stdout.lower() or proc.stdout.strip()
```

- [ ] **Step 2: Run the smoke test**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_smoke_mempalace.py -v`
Expected: PASS if `mempalace` is on PATH; skipped otherwise.

- [ ] **Step 3: Commit**

```bash
git -C /home/daedalus/linux/nexus add tests/test_smoke_mempalace.py
git -C /home/daedalus/linux/nexus commit -m "test: smoke test mempalace wake-up against real palace"
```

---

## Task 15: Add `data/` to .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append to `.gitignore`**

Append a single line to `/home/daedalus/linux/nexus/.gitignore`:

```
data/
```

- [ ] **Step 2: Verify git ignores the path**

Run: `mkdir -p /home/daedalus/linux/nexus/data && touch /home/daedalus/linux/nexus/data/dummy && git -C /home/daedalus/linux/nexus status --short`
Expected: `data/dummy` is not listed.

- [ ] **Step 3: Clean up the dummy and commit**

```bash
rm /home/daedalus/linux/nexus/data/dummy
git -C /home/daedalus/linux/nexus add .gitignore
git -C /home/daedalus/linux/nexus commit -m "chore: gitignore nexus data dir"
```

---

## Task 16: Run install on this repo and validate end-to-end

**Files:** none (manual validation)

- [ ] **Step 1: Clone MemPalace next to nexus for the hook scripts**

Run:

```bash
cd /home/daedalus/linux
git clone https://github.com/MemPalace/mempalace.git mempalace-upstream
```

Expected: clone succeeds.

- [ ] **Step 2: Install MemPalace into nexus's venv**

Run: `/home/daedalus/linux/nexus/.venv/bin/pip install mempalace`
Expected: install succeeds; the `mempalace` CLI ends up under `.venv/bin/`.

- [ ] **Step 3: Run `nexus memory init` for the nexus wing**

Run:

```bash
cd /home/daedalus/linux/nexus && .venv/bin/python -m nexus.cli memory init \
  --mempalace-repo /home/daedalus/linux/mempalace-upstream \
  --nexus-root /home/daedalus/linux/nexus \
  --user-prompt-hook /home/daedalus/linux/nexus/hooks/nexus-user-prompt-submit.sh \
  --skip-backfill
```

Expected: prints `wing: nexus`, paths to settings/hooks, `backfill done: False`.

- [ ] **Step 4: Inspect the resulting settings**

Run: `cat ~/.claude/settings.json | python3 -m json.tool | head -40`
Expected: JSON contains `Stop`, `PreCompact`, `UserPromptSubmit` entries with paths into `mempalace-upstream/hooks/` and `nexus/hooks/`.

Run: `cat ~/.codex/hooks.json | python3 -m json.tool`
Expected: contains `Stop` and `PreCompact` entries.

- [ ] **Step 5: Run `nexus memory status`**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m nexus.cli memory status`
Expected: `wing: nexus`, `palace_exists: True`, `mempalace_on_path: True`.

- [ ] **Step 6: Run a real backfill (small scope to keep it quick)**

Run:

```bash
.venv/bin/python -m nexus.cli memory init \
  --mempalace-repo /home/daedalus/linux/mempalace-upstream \
  --nexus-root /home/daedalus/linux/nexus \
  --user-prompt-hook /home/daedalus/linux/nexus/hooks/nexus-user-prompt-submit.sh
```

(without `--skip-backfill`). Expected: prints `backfill done: True` after a few minutes; `data/backfill_markers/nexus.done` exists.

- [ ] **Step 7: Open a fresh Claude Code session in `~/linux/nexus`**

Manual check. Confirm SessionStart output now contains both `Project docs:` and `Prior session context:` blocks. Type a prompt referencing prior phase-1 work; confirm the agent has the relevant context.

This step has no commit — it is a validation gate.

---

## Task 17: Remove the BM25 layer

**Files:**
- Delete: `nexus/db.py`, `nexus/query.py`, `nexus/indexer.py`
- Delete: `tests/test_query.py`, `tests/test_indexer.py`
- Modify: `nexus/cli.py` (drop `recall`/`index`/`stats` parsers and handlers)
- Delete: `~/.claude/tools/nexus/nexus.db`

- [ ] **Step 1: Drop the legacy CLI subcommands and helpers from `nexus/cli.py`**

Remove these entries from `build_parser()`:

- `recall = subparsers.add_parser("recall", ...)` and all its arguments
- `index = subparsers.add_parser("index", ...)` and all its arguments
- `stats = subparsers.add_parser("stats", ...)` and all its arguments

Remove these handler functions:

- `_handle_recall`
- `_handle_index`
- `_handle_stats`

Remove `from nexus.indexer import update`, `from nexus.query import search`, `from nexus.db import open_db` and `_db` helper. Also remove `_resolved_db_path`, `_default_db_path` if no longer referenced.

- [ ] **Step 2: Delete BM25 modules and tests**

Run:

```bash
cd /home/daedalus/linux/nexus
git rm nexus/db.py nexus/query.py nexus/indexer.py
git rm tests/test_query.py tests/test_indexer.py
```

- [ ] **Step 3: Delete the runtime DB file**

Run: `rm -f ~/.claude/tools/nexus/nexus.db ~/.claude/tools/nexus/nexus.db-wal ~/.claude/tools/nexus/nexus.db-shm`
Expected: gone, no error.

- [ ] **Step 4: Run the full test suite**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest -v`
Expected: PASS — only the new and updated tests run; nothing imports the deleted modules.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add -A
git -C /home/daedalus/linux/nexus commit -m "refactor: retire BM25 layer in favor of mempalace"
```

---

## Task 18: Extend `nexus doctor` with memory checks

**Files:**
- Modify: `nexus/cli.py` (`_handle_doctor`)
- Modify: `tests/test_cli.py` (existing doctor tests must still pass)

- [ ] **Step 1: Add the new test**

Append to `tests/test_cli.py`:

```python
def test_doctor_reports_palace_state(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    nexus_root = workspace / "nexus"
    (nexus_root / "data" / "palace").mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    db_path = tmp_path / "nexus.db"

    code = cli_main([
        "doctor",
        "--repo-path", str(repo),
        "--workspace-root", str(workspace),
        "--db-path", str(db_path),
        "--nexus-root", str(nexus_root),
    ])
    assert code == 0
    output = capsys.readouterr().out
    assert "palace path exists: yes" in output
    assert "mempalace on path:" in output
```

- [ ] **Step 2: Run the test to verify failure**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_cli.py::test_doctor_reports_palace_state -v`
Expected: FAIL — `--nexus-root` flag rejected, or output lacks the new lines.

- [ ] **Step 3: Extend `_handle_doctor` in `nexus/cli.py`**

Add `--nexus-root` argument to the doctor parser:

```python
    doctor.add_argument(
        "--nexus-root",
        type=Path,
        default=Path("/home/daedalus/linux/nexus"),
    )
```

Then extend `_handle_doctor` to add three more checks after the existing ones:

```python
    import shutil
    palace_dir = Path(args.nexus_root) / "data" / "palace"
    checks.append(("palace path exists", palace_dir.is_dir()))
    checks.append(("mempalace on path", shutil.which("mempalace") is not None))
    home = Path(os.path.expanduser("~"))
    checks.append((
        "claude hooks installed",
        (home / ".claude" / "settings.json").exists(),
    ))
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `cd /home/daedalus/linux/nexus && .venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS — new and existing doctor tests both pass.

- [ ] **Step 5: Commit**

```bash
git -C /home/daedalus/linux/nexus add nexus/cli.py tests/test_cli.py
git -C /home/daedalus/linux/nexus commit -m "feat(doctor): report palace, mempalace, and hook installation state"
```

---

## Task 19: Update WORKING_MEMORY.md and project memory

**Files:**
- Modify: `WORKING_MEMORY.md`
- Modify: `~/.claude/projects/-home-daedalus-linux/memory/project_nexus.md`
- Modify: `~/.claude/projects/-home-daedalus-linux/memory/MEMORY.md` if needed

- [ ] **Step 1: Update `WORKING_MEMORY.md`**

In `/home/daedalus/linux/nexus/WORKING_MEMORY.md`:
- Set `Updated: 2026-05-01`
- Move "Phase 2 (active memory, token telemetry) remains documented in the spec but intentionally deferred." → "Phase 2 active memory shipped 2026-05-01 (token telemetry dropped from scope)."
- Replace the four "Active follow-ups" with: phase 2 done; future work is closing the Codex prompt-injection gap when upstream supports it.
- Drop the BM25-related items under "Current Limitations".

- [ ] **Step 2: Update the user-side memory entry**

Edit `/home/daedalus/.claude/projects/-home-daedalus-linux/memory/project_nexus.md`:
- Mark follow-up (4) as done.
- Add a sentence: "Phase 2 (active memory) shipped 2026-05-01: MemPalace wired into Claude/Codex with per-repo wing convention and storage under `~/linux/nexus/data/`. BM25 layer retired."
- Change "How to apply" — there are no more open follow-ups in the original list; flag the Codex hook gap as something to revisit when upstream changes.

- [ ] **Step 3: Commit**

```bash
git -C /home/daedalus/linux/nexus add WORKING_MEMORY.md
git -C /home/daedalus/linux/nexus commit -m "docs(memory): nexus phase 2 active memory shipped"
```

The user-memory file lives outside any repo; no commit there.

---

## Self-review notes

- All spec sections trace to a task: wings (Task 2-3), env (Task 4), install (Tasks 5-8), UserPromptSubmit hook (Task 9), CLI subcommands (Tasks 10-11), context rewrite (Task 12), policy rewrite (Task 13), smoke test (Task 14), gitignore (Task 15), end-to-end validation (Task 16), BM25 removal (Task 17), doctor extension (Task 18), memory updates (Task 19).
- No placeholders, no "TODO", no "similar to Task N".
- Type/method names consistent across tasks: `resolve_wing`, `mempalace_env`, `merge_claude_hooks`, `write_codex_hooks`, `locate_mempalace_hooks`, `init`, `status_report`, `_mempalace_wake_up`.
- BM25 removal lands in Task 17 — after the replacement is proven by Task 16's manual validation gate.
