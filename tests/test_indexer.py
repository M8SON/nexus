"""Tests for record routing and incremental file ingest."""

import shutil
from pathlib import Path

import pytest

from forge.db import open_db
from forge.indexer import route_record, update


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "index.db"


@pytest.fixture
def fixtures_dir():
    return Path(__file__).resolve().parent / "fixtures"


def _single_user_record(content: str, *, session_id: str = "sess-2") -> str:
    return (
        '{"type":"user","sessionId":"'
        + session_id
        + '","uuid":"u-fresh-1","parentUuid":null,'
        '"timestamp":"2026-04-24T01:00:00Z",'
        '"message":{"role":"user","content":"'
        + content
        + '"}}\n'
    )


def test_user_text_routed():
    record = {
        "type": "user",
        "sessionId": "s1",
        "uuid": "u1",
        "parentUuid": None,
        "timestamp": "2026-04-24T00:00:00Z",
        "cwd": "/x",
        "gitBranch": "main",
        "message": {"role": "user", "content": "hello"},
    }
    turns = route_record(record)
    assert len(turns) == 1
    t = turns[0]
    assert t.role == "user"
    assert t.content == "hello"
    assert t.uuid == "u1"
    assert t.session_id == "s1"
    assert t.cwd == "/x"
    assert t.git_branch == "main"
    assert t.tool_name is None


def test_assistant_text_and_tool_use_split():
    record = {
        "type": "assistant",
        "sessionId": "s1",
        "uuid": "u2",
        "parentUuid": "u1",
        "timestamp": "2026-04-24T00:00:01Z",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "ok"},
                {
                    "type": "tool_use",
                    "id": "tu1",
                    "name": "Bash",
                    "input": {"command": "ls", "description": "list"},
                },
            ],
        },
    }
    turns = route_record(record)
    assert len(turns) == 2
    assert turns[0].role == "assistant"
    assert turns[0].content == "ok"
    assert turns[0].uuid == "u2:0"
    assert turns[1].role == "tool_use"
    assert turns[1].tool_name == "Bash"
    assert turns[1].uuid == "u2:1"
    assert "ls" in turns[1].content


def test_tool_use_input_truncated_at_300():
    big_input = {"text": "x" * 1000}
    record = {
        "type": "assistant",
        "sessionId": "s1",
        "uuid": "u3",
        "timestamp": "2026-04-24T00:00:02Z",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Bash", "input": big_input}],
        },
    }
    turns = route_record(record)
    assert len(turns) == 1
    assert len(turns[0].content) <= 305


def test_tool_result_truncated_at_500():
    big_content = "y" * 2000
    record = {
        "type": "user",
        "sessionId": "s1",
        "uuid": "u4",
        "timestamp": "2026-04-24T00:00:03Z",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu1", "content": big_content}
            ],
        },
    }
    turns = route_record(record)
    assert len(turns) == 1
    assert turns[0].role == "tool_result"
    assert len(turns[0].content) == 500


def test_attachment_skipped():
    record = {
        "type": "attachment",
        "uuid": "u5",
        "sessionId": "s1",
        "timestamp": "2026-04-24T00:00:04Z",
        "attachment": {},
    }
    assert route_record(record) == []


def test_permission_mode_skipped():
    record = {"type": "permission-mode", "sessionId": "s1", "permissionMode": "default"}
    assert route_record(record) == []


def test_file_history_snapshot_skipped():
    record = {
        "type": "file-history-snapshot",
        "sessionId": "s1",
        "timestamp": "2026-04-24T00:00:05Z",
    }
    assert route_record(record) == []


def test_update_indexes_minimal_fixture(tmp_db_path, fixtures_dir, tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    shutil.copy(fixtures_dir / "minimal.jsonl", projects / "minimal.jsonl")

    conn = open_db(tmp_db_path)
    try:
        n = update(conn, projects)
    finally:
        conn.close()
    assert n == 4

    conn = open_db(tmp_db_path)
    try:
        roles = [r[0] for r in conn.execute("SELECT role FROM turns ORDER BY ts").fetchall()]
    finally:
        conn.close()
    assert roles == ["user", "assistant", "tool_use", "tool_result"]


def test_update_is_idempotent(tmp_db_path, fixtures_dir, tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    shutil.copy(fixtures_dir / "minimal.jsonl", projects / "minimal.jsonl")

    conn = open_db(tmp_db_path)
    try:
        n1 = update(conn, projects)
        n2 = update(conn, projects)
    finally:
        conn.close()
    assert n1 == 4
    assert n2 == 0


def test_update_resumes_on_append(tmp_db_path, fixtures_dir, tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    target = projects / "minimal.jsonl"
    shutil.copy(fixtures_dir / "minimal.jsonl", target)

    conn = open_db(tmp_db_path)
    try:
        update(conn, projects)
        with open(target, "a") as f:
            f.write(
                '{"type":"user","sessionId":"sess-1","uuid":"u-user-2",'
                '"parentUuid":null,"timestamp":"2026-04-24T00:01:00Z",'
                '"message":{"role":"user","content":"second"}}\n'
            )
        n2 = update(conn, projects)
    finally:
        conn.close()
    assert n2 == 1


def test_update_full_reindex_on_shrink(tmp_db_path, fixtures_dir, tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    target = projects / "minimal.jsonl"
    shutil.copy(fixtures_dir / "minimal.jsonl", target)

    conn = open_db(tmp_db_path)
    try:
        update(conn, projects)
        target.write_text(_single_user_record("new-content"))
        n2 = update(conn, projects)
        rows = conn.execute(
            "SELECT session_id, content FROM turns WHERE file_path = ? ORDER BY id",
            (str(target),),
        ).fetchall()
    finally:
        conn.close()
    assert n2 == 1
    assert rows == [("sess-2", "new-content")]


def test_update_reindexes_same_size_rewrite(tmp_db_path, fixtures_dir, tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    target = projects / "minimal.jsonl"
    shutil.copy(fixtures_dir / "minimal.jsonl", target)
    original_size = target.stat().st_size

    replacement_base = _single_user_record("")
    replacement = _single_user_record("x" * (original_size - len(replacement_base)))
    assert len(replacement) == original_size

    conn = open_db(tmp_db_path)
    try:
        update(conn, projects)
        target.write_text(replacement)
        n2 = update(conn, projects)
        rows = conn.execute(
            "SELECT session_id, content FROM turns WHERE file_path = ? ORDER BY id",
            (str(target),),
        ).fetchall()
    finally:
        conn.close()
    assert n2 == 1
    assert rows == [("sess-2", "x" * (original_size - len(replacement_base)))]


def test_update_reindexes_growing_rewrite(tmp_db_path, fixtures_dir, tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    target = projects / "minimal.jsonl"
    shutil.copy(fixtures_dir / "minimal.jsonl", target)
    original_size = target.stat().st_size

    replacement = _single_user_record("y" * (original_size + 25))

    conn = open_db(tmp_db_path)
    try:
        update(conn, projects)
        target.write_text(replacement)
        n2 = update(conn, projects)
        rows = conn.execute(
            "SELECT session_id, content FROM turns WHERE file_path = ? ORDER BY id",
            (str(target),),
        ).fetchall()
    finally:
        conn.close()
    assert n2 == 1
    assert rows == [("sess-2", "y" * (original_size + 25))]


def test_turn_index_monotonic_per_session_across_files(
    tmp_db_path, fixtures_dir, tmp_path
):
    projects = tmp_path / "projects"
    projects.mkdir()
    shutil.copy(fixtures_dir / "split_a.jsonl", projects / "split_a.jsonl")
    shutil.copy(fixtures_dir / "split_b.jsonl", projects / "split_b.jsonl")

    conn = open_db(tmp_db_path)
    try:
        update(conn, projects)
        rows = conn.execute(
            "SELECT turn_index, content FROM turns "
            "WHERE session_id = 'sX' ORDER BY ts"
        ).fetchall()
    finally:
        conn.close()
    indices = [r[0] for r in rows]
    assert indices == [0, 1, 2, 3]


def test_malformed_line_warns_but_does_not_abort(
    tmp_db_path, fixtures_dir, tmp_path, caplog
):
    projects = tmp_path / "projects"
    projects.mkdir()
    shutil.copy(fixtures_dir / "minimal.jsonl", projects / "minimal.jsonl")

    conn = open_db(tmp_db_path)
    try:
        with caplog.at_level("WARNING", logger="forge.indexer"):
            n = update(conn, projects)
    finally:
        conn.close()
    assert n == 4
    assert any("malformed" in r.message.lower() for r in caplog.records)
