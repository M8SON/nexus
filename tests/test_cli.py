from pathlib import Path

from forge.cli import main
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
    db_path = tmp_path / "forge.db"
    conn = open_db(db_path)
    conn.execute(
        "INSERT INTO turns (session_id, file_path, turn_index, uuid, ts, role, content) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "/tmp/demo.jsonl", 0, "u1", "2026-04-26T10:00:00Z", "user", "wake offload is enabled"),
    )
    conn.commit()
    conn.close()

    assert main(["recall", "wake", "--db-path", str(db_path)]) == 0

    output = capsys.readouterr().out
    assert "wake offload is enabled" in output


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
