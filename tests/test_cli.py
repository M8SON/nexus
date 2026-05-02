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
