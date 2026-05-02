"""
Sqlite schema and connection helpers for nexus.

Two relational tables (files, turns) plus an FTS5 virtual table mirroring
turns.content for BM25 search. INSERT/DELETE triggers keep the FTS5 table
in sync automatically.

migrate() is idempotent - safe to call on every connection open.
"""

import sqlite3
from pathlib import Path


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS files (
        path          TEXT PRIMARY KEY,
        mtime_ns      INTEGER NOT NULL,
        size_bytes    INTEGER NOT NULL,
        last_offset   INTEGER NOT NULL,
        records_total INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS turns (
        id             INTEGER PRIMARY KEY,
        session_id     TEXT NOT NULL,
        file_path      TEXT NOT NULL,
        turn_index     INTEGER NOT NULL,
        uuid           TEXT NOT NULL,
        parent_uuid    TEXT,
        ts             TEXT NOT NULL,
        role           TEXT NOT NULL,
        tool_name      TEXT,
        content        TEXT NOT NULL,
        cwd            TEXT,
        git_branch     TEXT
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_uuid ON turns(uuid)",
    "CREATE INDEX IF NOT EXISTS idx_turns_session_ts ON turns(session_id, turn_index)",
    "CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
        content,
        tool_name,
        content=turns,
        content_rowid=id,
        tokenize='porter unicode61'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS turns_ai AFTER INSERT ON turns BEGIN
        INSERT INTO turns_fts(rowid, content, tool_name)
        VALUES (new.id, new.content, new.tool_name);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS turns_ad AFTER DELETE ON turns BEGIN
        INSERT INTO turns_fts(turns_fts, rowid, content, tool_name)
        VALUES ('delete', old.id, old.content, old.tool_name);
    END
    """,
]


def open_db(path: Path) -> sqlite3.Connection:
    """Open a sqlite connection at `path`, ensuring the schema exists."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Apply schema statements. Safe to call repeatedly."""
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)
    conn.commit()
