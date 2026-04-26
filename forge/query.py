"""
BM25 search + context expansion + --since parsing.

search() runs FTS5 MATCH against turns_fts, applies optional filters
(--since, --session, --role), then for each hit expands +/-N surrounding
turns from the same session.
"""

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class ContextTurn:
    turn_index: int
    role: str
    tool_name: str | None
    content: str
    ts: str


@dataclass
class Hit:
    score: float
    session_id: str
    turn_index: int
    uuid: str
    ts: str
    role: str
    tool_name: str | None
    content: str
    context: list[ContextTurn] = field(default_factory=list)


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 3,
    context: int = 0,
    since: str | None = None,
    session: str | None = None,
    roles: list[str] | None = None,
) -> list[Hit]:
    """BM25 search with optional filters and +/-context expansion."""
    sql = (
        "SELECT t.id, t.session_id, t.turn_index, t.uuid, t.ts, t.role, "
        "       t.tool_name, t.content, bm25(turns_fts) AS score "
        "FROM turns t JOIN turns_fts f ON f.rowid = t.id "
        "WHERE turns_fts MATCH ?"
    )
    params: list[object] = [query]
    if since:
        sql += " AND t.ts >= ?"
        params.append(since)
    if session:
        sql += " AND t.session_id = ?"
        params.append(session)
    if roles:
        sql += " AND t.role IN (" + ",".join("?" * len(roles)) + ")"
        params.extend(roles)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)

    rows = _run_search(conn, sql, params)

    hits: list[Hit] = []
    for row in rows:
        _, session_id, turn_index, uuid, ts, role, tool_name, content, score = row
        hit = Hit(
            score=score,
            session_id=session_id,
            turn_index=turn_index,
            uuid=uuid,
            ts=ts,
            role=role,
            tool_name=tool_name,
            content=content,
        )
        if context > 0:
            hit.context = _expand_context(conn, session_id, turn_index, context)
        hits.append(hit)
    return hits


def _expand_context(
    conn: sqlite3.Connection, session_id: str, hit_index: int, span: int
) -> list[ContextTurn]:
    rows = conn.execute(
        "SELECT turn_index, role, tool_name, content, ts FROM turns "
        "WHERE session_id = ? AND turn_index >= ? AND turn_index <= ? "
        "  AND turn_index != ? "
        "ORDER BY turn_index",
        (session_id, hit_index - span, hit_index + span, hit_index),
    ).fetchall()
    return [
        ContextTurn(turn_index=r[0], role=r[1], tool_name=r[2], content=r[3], ts=r[4])
        for r in rows
    ]


_SINCE_N_DAYS_AGO_RE = re.compile(r"^(\d+)\s*days?\s*ago$")
_LITERAL_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_FIELD_QUERY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:.+$")
_UNSAFE_LITERAL_TOKEN_RE = re.compile(r"\w[-+./#]\w|\w[+/#]+")
_MATCH_SYNTAX_ERROR_PATTERNS = (
    "unterminated string",
    "syntax error",
    "malformed match expression",
    "fts5: syntax error",
)


def parse_since(value: str | None) -> str | None:
    """Parse a --since spec to an ISO datetime string, or None on failure."""
    if not value:
        return None
    s = str(value).strip().lower()
    if not s:
        return None

    now = datetime.now()

    try:
        return datetime.fromisoformat(s).isoformat(timespec="seconds")
    except ValueError:
        pass

    if s == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(
            timespec="seconds"
        )
    if s == "yesterday":
        return (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat(timespec="seconds")
    if s in ("last week", "past week"):
        return (now - timedelta(days=7)).isoformat(timespec="seconds")

    match = _SINCE_N_DAYS_AGO_RE.match(s)
    if match:
        return (now - timedelta(days=int(match.group(1)))).isoformat(
            timespec="seconds"
        )

    return None


def _run_search(
    conn: sqlite3.Connection, sql: str, params: list[object]
) -> list[tuple]:
    raw_query = str(params[0])
    if _should_use_literal_query(raw_query):
        literal_query = _literalize_query(raw_query)
        if not literal_query:
            return []
        return conn.execute(sql, [literal_query, *params[1:]]).fetchall()
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        if not _is_match_syntax_error(exc):
            raise
        literal_query = _literalize_query(raw_query)
        if not literal_query:
            return []
        fallback_params = [literal_query, *params[1:]]
        try:
            return conn.execute(sql, fallback_params).fetchall()
        except sqlite3.OperationalError as fallback_exc:
            if not _is_match_syntax_error(fallback_exc):
                raise
            return []


def _literalize_query(query: str) -> str:
    chunks: list[str] = []
    for part in query.split():
        tokens = _LITERAL_TOKEN_RE.findall(part)
        if tokens:
            chunks.append(f"\"{' '.join(tokens)}\"")
    return " AND ".join(chunks)


def _should_use_literal_query(query: str) -> bool:
    if query.count('"') % 2 == 1:
        return True
    for part in query.split():
        if _FIELD_QUERY_RE.match(part):
            continue
        if _UNSAFE_LITERAL_TOKEN_RE.search(part):
            return True
    return False


def _is_match_syntax_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return any(pattern in message for pattern in _MATCH_SYNTAX_ERROR_PATTERNS)
