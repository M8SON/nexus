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


def test_register_claude_mcp_server_calls_remove_then_add(monkeypatch):
    """Idempotent registration: remove first, then add."""
    from unittest.mock import MagicMock
    from nexus.memory import install

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(install.subprocess, "run", fake_run)

    result = install.register_claude_mcp_server(mempalace_mcp_bin="/path/to/mempalace-mcp")

    assert result["registered"] is True
    assert calls[0][:3] == ["claude", "mcp", "remove"]
    assert calls[1][:3] == ["claude", "mcp", "add"]
    assert "/path/to/mempalace-mcp" in calls[1]
    assert "--scope" in calls[1] and "user" in calls[1]


def test_register_claude_mcp_server_no_cli_falls_back_gracefully(monkeypatch):
    """Without the claude CLI on PATH, registration reports the reason and continues."""
    from nexus.memory import install
    monkeypatch.setattr(install.shutil, "which", lambda _: None)

    result = install.register_claude_mcp_server()

    assert result["registered"] is False
    assert "claude CLI not on PATH" in result["reason"]


def test_register_claude_mcp_server_propagates_add_failure(monkeypatch):
    """When `claude mcp add` exits non-zero, the reason is captured (not raised)."""
    import subprocess as sp
    from nexus.memory import install

    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/claude")

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["claude", "mcp", "remove"]:
            class _R:
                returncode = 0
                stderr = b""
            return _R()
        # add fails
        raise sp.CalledProcessError(returncode=1, cmd=cmd, stderr=b"server already exists")

    monkeypatch.setattr(install.subprocess, "run", fake_run)

    result = install.register_claude_mcp_server(mempalace_mcp_bin="/path/to/mempalace-mcp")

    assert result["registered"] is False
    assert "server already exists" in result["reason"]


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

    # Skip touching the real claude CLI: fake "not on PATH" so the MCP
    # registration step exercises the graceful-fallback branch.
    from nexus.memory import install as install_module
    monkeypatch.setattr(install_module.shutil, "which", lambda _: None)

    result = init(
        repo=repo,
        mempalace_repo=mempalace,
        nexus_root=nexus_root,
        user_prompt_hook=user_prompt_hook,
        skip_backfill=True,
    )

    from nexus.memory.wings import path_to_wing
    assert result["wing"] == path_to_wing(repo)
    assert (fake_home / ".claude" / "settings.json").exists()
    assert (fake_home / ".codex" / "hooks.json").exists()
    # MCP registration ran but couldn't find the CLI in this test env;
    # the reason should be captured and init() should not have raised.
    assert result["claude_mcp_registered"] is False
    assert "claude CLI" in (result["claude_mcp_reason"] or "")


def test_find_claude_project_dir_matches_full_normalized_name(tmp_path):
    from nexus.memory.install import _find_claude_project_dir

    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "-home-user-linux-nexus").mkdir()
    (projects / "-home-user-linux-miniclaw").mkdir()
    (projects / "-home-user-other").mkdir()

    # Wings are now full path-derived (matching what mempalace auto-derives).
    found = _find_claude_project_dir(projects, "_home_user_linux_nexus")
    assert found == projects / "-home-user-linux-nexus"

    found = _find_claude_project_dir(projects, "_home_user_linux_miniclaw")
    assert found == projects / "-home-user-linux-miniclaw"

    assert _find_claude_project_dir(projects, "ghost") is None


def test_find_claude_project_dir_is_case_insensitive(tmp_path):
    from nexus.memory.install import _find_claude_project_dir

    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "-Home-USER-NEXUS").mkdir()
    assert _find_claude_project_dir(projects, "_home_user_nexus") == projects / "-Home-USER-NEXUS"


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
    assert _run_backfill(wing="_home_user_linux_nexus", marker=marker) is True
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
    assert _run_backfill(wing="_home_user_linux_nexus", marker=marker) is True

    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert str(nexus_dir) in cmd
    assert str(miniclaw_dir) not in cmd
    assert "--wing" in cmd and "_home_user_linux_nexus" in cmd


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
