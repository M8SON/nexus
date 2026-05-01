from pathlib import Path

from forge.cli import _default_projects_path, _workspace_projects_slug, main
from forge.db import open_db


def test_help_without_args_returns_error(capsys):
    assert main([]) == 1

    captured = capsys.readouterr()
    assert "usage:" in captured.err


def test_context_subcommand_exists(capsys):
    code = main(["context", "--help"])

    assert code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out


def test_index_then_stats_reports_indexed_content(tmp_path, capsys):
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    fixture = Path(__file__).resolve().parent / "fixtures" / "minimal.jsonl"
    (transcripts / "minimal.jsonl").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    db_path = tmp_path / "forge.db"

    assert main(["index", "--project-dir", str(transcripts), "--db-path", str(db_path)]) == 0

    index_output = capsys.readouterr().out
    assert "Indexed" in index_output

    assert main(["stats", "--db-path", str(db_path)]) == 0
    stats_output = capsys.readouterr().out
    assert "turns:" in stats_output
    assert "files:" in stats_output


def test_recall_returns_matching_hit(tmp_path, capsys):
    repo = tmp_path / "linux" / "demo"
    repo.mkdir(parents=True)
    db_path = tmp_path / "forge.db"
    conn = open_db(db_path)
    conn.execute(
        "INSERT INTO turns (session_id, file_path, turn_index, uuid, ts, role, content, cwd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "/tmp/demo.jsonl", 0, "u1", "2026-04-26T10:00:00Z", "user", "wake offload is enabled", str(repo)),
    )
    conn.commit()
    conn.close()

    assert main(["recall", "wake", "--db-path", str(db_path), "--repo", str(repo)]) == 0

    output = capsys.readouterr().out
    assert "wake offload is enabled" in output


def test_recall_refreshes_from_default_transcript_dir(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    transcripts = home / ".claude" / "projects" / "-home-daedalus-linux"
    transcripts.mkdir(parents=True)
    fixture = Path(__file__).resolve().parent / "fixtures" / "minimal.jsonl"
    (transcripts / "minimal.jsonl").write_text(
        fixture.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    assert main(["recall", "hello"]) == 0

    output = capsys.readouterr().out
    assert "hello world" in output


def test_context_assembles_docs_and_recall_hits(tmp_path, capsys):
    repo = tmp_path / "linux" / "demo"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("Wake offload overview", encoding="utf-8")
    db_path = tmp_path / "forge.db"
    conn = open_db(db_path)
    conn.execute(
        "INSERT INTO turns (session_id, file_path, turn_index, uuid, ts, role, content, cwd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "/tmp/demo.jsonl", 0, "u1", "2026-04-26T10:00:00Z", "assistant", "Wake offload was completed", str(repo)),
    )
    conn.commit()
    conn.close()

    assert (
        main(
            [
                "context",
                "wake",
                "--repo-path",
                str(repo),
                "--db-path",
                str(db_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Prior session context:" in output
    assert "Project docs:" in output
    assert "Wake offload was completed" in output
    assert "Wake offload overview" in output


def test_context_refreshes_from_transcripts_before_query(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    transcripts = home / ".claude" / "projects" / "-home-daedalus-linux"
    transcripts.mkdir(parents=True)
    repo = tmp_path / "linux" / "demo"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("Project readme context", encoding="utf-8")

    fixture_text = (
        Path(__file__).resolve().parent / "fixtures" / "minimal.jsonl"
    ).read_text(encoding="utf-8")
    (transcripts / "minimal.jsonl").write_text(
        fixture_text.replace('"cwd":"/x"', f'"cwd":"{repo}"'),
        encoding="utf-8",
    )

    assert main(["context", "hello", "--repo-path", str(repo)]) == 0

    output = capsys.readouterr().out
    assert "Prior session context:" in output
    assert "hello world" in output
    assert "Project docs:" in output
    assert "Project readme context" in output


def test_index_defaults_to_transcript_projects_path(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    transcripts = _default_projects_path()
    transcripts.mkdir(parents=True)
    fixture = Path(__file__).resolve().parent / "fixtures" / "minimal.jsonl"
    (transcripts / "minimal.jsonl").write_text(
        fixture.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    assert main(["index"]) == 0

    output = capsys.readouterr().out
    assert f"Indexed 4 turns from {transcripts}" in output


def test_workspace_projects_slug_is_derived_from_workspace_root():
    assert _workspace_projects_slug(Path("/home/daedalus/linux")) == "-home-daedalus-linux"
    assert _workspace_projects_slug(Path("/tmp/demo space")) == "-tmp-demo space"


def test_default_projects_path_uses_workspace_root_slug(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("forge.cli.ForgeConfig.default", classmethod(lambda cls: cls(workspace_root=Path("/tmp/custom/workspace"))))

    assert _default_projects_path() == (
        home / ".claude" / "projects" / "-tmp-custom-workspace"
    )


def test_doctor_fails_when_repo_is_outside_workspace(tmp_path, capsys):
    repo = tmp_path / "other" / "demo"
    repo.mkdir(parents=True)
    db_path = tmp_path / "forge.db"

    assert (
        main(
            [
                "doctor",
                "--repo-path",
                str(repo),
                "--workspace-root",
                str(tmp_path / "linux"),
                "--db-path",
                str(db_path),
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "managed repo: no" in output


def test_doctor_uses_default_db_path_when_omitted(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "linux"
    repo = workspace / "demo"
    repo.mkdir(parents=True)

    assert (
        main(
            [
                "doctor",
                "--repo-path",
                str(repo),
                "--workspace-root",
                str(workspace),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert f"db path: {home / '.claude' / 'tools' / 'forge' / 'forge.db'}" in output
    assert "db path usable: yes" in output
