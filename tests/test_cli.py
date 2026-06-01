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
    from nexus.memory.wings import path_to_wing
    assert captured_calls == [path_to_wing(repo)]


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
    from nexus.memory.wings import path_to_wing
    assert f"wing: {path_to_wing(repo)}" in output


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
