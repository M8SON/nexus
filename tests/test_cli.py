from pathlib import Path

from nexus.cli import main


def test_help_without_args_returns_error(capsys):
    assert main([]) == 1

    captured = capsys.readouterr()
    assert "usage:" in captured.err


def test_context_subcommand_exists(capsys):
    code = main(["context", "--help"])

    assert code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out


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
    def fake_wake_up(wing):
        captured_calls.append(wing)
        return "Wake offload was completed"
    monkeypatch.setattr("nexus.cli._mempalace_wake_up", fake_wake_up)

    code = cli_main(["context", "wake", "--repo-path", str(repo)])
    assert code == 0

    output = capsys.readouterr().out
    assert "Prior session context:" in output
    assert "Wake offload was completed" in output
    assert "Project docs:" in output
    assert "Wake offload overview" in output
    assert captured_calls == ["demo"]


def test_doctor_fails_when_repo_is_outside_workspace(tmp_path, capsys):
    repo = tmp_path / "other" / "demo"
    repo.mkdir(parents=True)

    assert (
        main(
            [
                "doctor",
                "--repo-path",
                str(repo),
                "--workspace-root",
                str(tmp_path / "linux"),
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "managed repo: no" in output


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


def test_context_warns_when_mempalace_missing(tmp_path, monkeypatch, capsys):
    """FileNotFoundError from wake-up should surface a visible warning."""
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    repo = workspace / "demo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    def fake_wake_up(wing):
        raise FileNotFoundError("mempalace binary missing")
    monkeypatch.setattr("nexus.cli._mempalace_wake_up", fake_wake_up)

    code = cli_main(["context", "--repo-path", str(repo)])
    assert code == 0

    output = capsys.readouterr().out
    assert "mempalace binary not found" in output
    assert "recall.log" in output


def test_resolve_mempalace_bin_prefers_sibling(tmp_path, monkeypatch):
    """When a mempalace binary sits next to sys.executable, return that path."""
    import sys
    from nexus.cli import _resolve_mempalace_bin

    fake_python = tmp_path / "python"
    fake_python.write_text("", encoding="utf-8")
    sibling = tmp_path / "mempalace"
    sibling.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sibling.chmod(0o755)

    monkeypatch.setattr(sys, "executable", str(fake_python))
    assert _resolve_mempalace_bin() == str(sibling)


def test_resolve_mempalace_bin_falls_back_to_path(tmp_path, monkeypatch):
    """When no sibling exists, return bare 'mempalace' for PATH lookup."""
    import sys
    from nexus.cli import _resolve_mempalace_bin

    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    assert _resolve_mempalace_bin() == "mempalace"


def test_doctor_reports_palace_state(tmp_path, monkeypatch, capsys):
    from nexus.cli import main as cli_main

    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    fake_home = tmp_path / "home"
    (fake_home / ".mempalace" / "palace").mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    monkeypatch.setenv("HOME", str(fake_home))

    code = cli_main([
        "doctor",
        "--repo-path", str(repo),
        "--workspace-root", str(workspace),
    ])
    assert code == 0
    output = capsys.readouterr().out
    assert "palace path exists: yes" in output
    assert "mempalace on path:" in output
    assert "claude hooks installed:" in output
