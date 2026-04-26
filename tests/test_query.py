"""Tests for BM25 search, filters, context expansion, and --since parsing."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from forge.db import open_db
from forge.query import parse_since, search


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "index.db"


@pytest.fixture
def fixtures_dir():
    return Path(__file__).resolve().parent / "fixtures"


def _seed(conn: sqlite3.Connection, rows: list[dict]) -> None:
    for r in rows:
        conn.execute(
            "INSERT INTO turns "
            "(session_id, file_path, turn_index, uuid, ts, role, content) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                r["session_id"],
                "/x",
                r["turn_index"],
                r["uuid"],
                r["ts"],
                r["role"],
                r["content"],
            ),
        )
    conn.commit()


@pytest.fixture
def seeded_db(tmp_db_path):
    conn = open_db(tmp_db_path)
    _seed(
        conn,
        [
            {
                "session_id": "s1",
                "turn_index": 0,
                "uuid": "u1",
                "ts": "2026-04-20T10:00:00Z",
                "role": "user",
                "content": "we should index session transcripts with FTS5",
            },
            {
                "session_id": "s1",
                "turn_index": 1,
                "uuid": "u2",
                "ts": "2026-04-20T10:00:01Z",
                "role": "assistant",
                "content": "yes a sqlite plus FTS5 index would be cheap",
            },
            {
                "session_id": "s1",
                "turn_index": 2,
                "uuid": "u3",
                "ts": "2026-04-20T10:00:02Z",
                "role": "user",
                "content": "let's also handle pagination",
            },
            {
                "session_id": "s2",
                "turn_index": 0,
                "uuid": "u4",
                "ts": "2026-04-21T11:00:00Z",
                "role": "user",
                "content": "completely unrelated lunch plans",
            },
        ],
    )
    yield conn
    conn.close()


def test_basic_match(seeded_db):
    hits = search(seeded_db, "FTS5")
    contents = [h.content for h in hits]
    assert any("FTS5" in c for c in contents)


def test_session_filter(seeded_db):
    hits = search(seeded_db, "lunch", session="s1")
    assert hits == []


def test_role_filter(seeded_db):
    hits = search(seeded_db, "FTS5", roles=["assistant"])
    assert all(h.role == "assistant" for h in hits)


def test_since_filter(seeded_db):
    hits = search(seeded_db, "lunch", since="2026-04-20T15:00:00")
    assert len(hits) == 1
    assert "lunch" in hits[0].content


def test_context_expansion_returns_neighbors(seeded_db):
    hits = search(seeded_db, "FTS5", limit=1, context=1)
    assert len(hits) == 1
    h = hits[0]
    indices = sorted([c.turn_index for c in h.context] + [h.turn_index])
    if h.turn_index == 0:
        assert indices == [0, 1]
    else:
        assert indices == [h.turn_index - 1, h.turn_index, h.turn_index + 1]


def test_zero_context_returns_no_neighbors(seeded_db):
    hits = search(seeded_db, "FTS5", limit=1, context=0)
    assert hits[0].context == []


def test_parse_since_iso():
    assert parse_since("2026-04-20") == "2026-04-20T00:00:00"


def test_parse_since_today():
    out = parse_since("today")
    assert out is not None
    assert "T00:00:00" in out


def test_parse_since_n_days_ago():
    out = parse_since("3 days ago")
    expected = (datetime.now() - timedelta(days=3)).isoformat(timespec="seconds")
    assert out is not None
    assert abs(
        (datetime.fromisoformat(out) - datetime.fromisoformat(expected)).total_seconds()
    ) < 5


def test_parse_since_unknown_returns_none():
    assert parse_since("blooberry") is None
