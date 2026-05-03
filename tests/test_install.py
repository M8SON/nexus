"""Tests for hook installation into Claude/Codex settings."""
import json
from pathlib import Path

from nexus.memory.install import locate_mempalace_hooks, merge_claude_hooks, write_codex_hooks


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


def test_backup_is_written_once_and_preserves_original(tmp_path):
    settings = tmp_path / "settings.json"
    original = '{"hooks": {}}'
    settings.write_text(original, encoding="utf-8")

    # First run captures original.
    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )
    backup = settings.with_suffix(settings.suffix + ".bak")
    assert backup.read_text(encoding="utf-8") == original

    # Second run must NOT overwrite the backup with the now-modified settings.
    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )
    assert backup.read_text(encoding="utf-8") == original


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
    assert (fake_home / ".claude" / "settings.json").exists()
    assert (fake_home / ".codex" / "hooks.json").exists()


def test_find_claude_project_dir_matches_last_token(tmp_path):
    from nexus.memory.install import _find_claude_project_dir

    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "-home-user-linux-nexus").mkdir()
    (projects / "-home-user-linux-miniclaw").mkdir()
    (projects / "-home-user-other").mkdir()

    found = _find_claude_project_dir(projects, "nexus")
    assert found == projects / "-home-user-linux-nexus"

    found = _find_claude_project_dir(projects, "miniclaw")
    assert found == projects / "-home-user-linux-miniclaw"

    assert _find_claude_project_dir(projects, "ghost") is None


def test_find_claude_project_dir_normalizes_case(tmp_path):
    from nexus.memory.install import _find_claude_project_dir

    projects = tmp_path / "projects"
    projects.mkdir()
    # Last token is treated case-insensitively to match nexus's wing naming.
    (projects / "-home-user-NEXUS").mkdir()
    assert _find_claude_project_dir(projects, "nexus") == projects / "-home-user-NEXUS"


def test_find_claude_project_dir_does_not_match_dashed_names(tmp_path):
    """Projects whose basename contains a dash cannot be matched by last-token
    alone — Claude Code's path encoding loses the boundary. This is a known
    limitation; the test pins it so we notice if we ever fix it."""
    from nexus.memory.install import _find_claude_project_dir

    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "-home-user-MY-Project").mkdir()

    # Last token is "Project", not "MY-Project" — so wing "my_project" misses.
    assert _find_claude_project_dir(projects, "my_project") is None
    assert _find_claude_project_dir(projects, "project") == projects / "-home-user-MY-Project"


def test_run_backfill_skips_when_no_matching_subdir(tmp_path, monkeypatch):
    """No-matching-subdir is not an error — mark done and move on."""
    from nexus.memory.install import _run_backfill

    fake_home = tmp_path / "home"
    (fake_home / ".claude" / "projects" / "-home-user-other").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))

    called = []
    def fake_run(*args, **kwargs):
        called.append(args)
        raise AssertionError("subprocess.run should not be invoked when no subdir matches")
    monkeypatch.setattr("nexus.memory.install.subprocess.run", fake_run)

    marker = tmp_path / "marker.done"
    assert _run_backfill(wing="nexus", marker=marker) is True
    assert marker.exists()
    assert called == []


def test_run_backfill_mines_only_matching_subdir(tmp_path, monkeypatch):
    from nexus.memory.install import _run_backfill

    fake_home = tmp_path / "home"
    nexus_dir = fake_home / ".claude" / "projects" / "-home-user-linux-nexus"
    miniclaw_dir = fake_home / ".claude" / "projects" / "-home-user-linux-miniclaw"
    nexus_dir.mkdir(parents=True)
    miniclaw_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))

    captured_cmds = []
    def fake_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        class R: returncode = 0
        return R()
    monkeypatch.setattr("nexus.memory.install.subprocess.run", fake_run)

    marker = tmp_path / "marker.done"
    assert _run_backfill(wing="nexus", marker=marker) is True

    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert str(nexus_dir) in cmd
    assert str(miniclaw_dir) not in cmd
    assert "--wing" in cmd and "nexus" in cmd


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
