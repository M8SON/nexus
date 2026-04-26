"""
JSONL ingestion for forge.

route_record() is a pure function that turns one parsed Claude Code transcript
record into zero or more Turn objects. update() drives incremental indexing
across all *.jsonl files in a projects directory.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


TOOL_USE_INPUT_MAX = 300
TOOL_RESULT_CONTENT_MAX = 500


@dataclass
class Turn:
    session_id: str
    uuid: str
    parent_uuid: str | None
    ts: str
    role: str
    content: str
    tool_name: str | None = None
    cwd: str | None = None
    git_branch: str | None = None


def route_record(record: dict) -> list[Turn]:
    """Turn one Claude Code transcript record into zero or more Turn rows."""
    rtype = record.get("type")
    if rtype not in ("user", "assistant"):
        return []

    msg = record.get("message") or {}
    content = msg.get("content")

    base_uuid = record.get("uuid", "")
    session_id = record.get("sessionId", "")
    parent_uuid = record.get("parentUuid")
    ts = record.get("timestamp", "")
    cwd = record.get("cwd")
    git_branch = record.get("gitBranch")

    if not base_uuid or not session_id or not ts:
        return []

    common = dict(
        session_id=session_id,
        parent_uuid=parent_uuid,
        ts=ts,
        cwd=cwd,
        git_branch=git_branch,
    )

    if rtype == "user" and isinstance(content, str):
        return [Turn(uuid=base_uuid, role="user", content=content, **common)]

    if isinstance(content, list):
        out: list[Turn] = []
        for i, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            block_uuid = f"{base_uuid}:{i}"
            if btype == "text" and rtype == "assistant":
                text = block.get("text") or ""
                if text:
                    out.append(Turn(uuid=block_uuid, role="assistant", content=text, **common))
            elif btype == "tool_use" and rtype == "assistant":
                name = block.get("name") or ""
                input_json = json.dumps(block.get("input") or {}, sort_keys=True)
                trimmed = input_json[:TOOL_USE_INPUT_MAX]
                out.append(
                    Turn(
                        uuid=block_uuid,
                        role="tool_use",
                        content=f"{name} {trimmed}".strip(),
                        tool_name=name or None,
                        **common,
                    )
                )
            elif btype == "tool_result" and rtype == "user":
                raw = block.get("content")
                if isinstance(raw, list):
                    raw_str = json.dumps(raw)
                else:
                    raw_str = str(raw or "")
                trimmed = raw_str[:TOOL_RESULT_CONTENT_MAX]
                out.append(Turn(uuid=block_uuid, role="tool_result", content=trimmed, **common))
        return out

    return []


def update(conn: sqlite3.Connection, projects_dir: Path) -> int:
    """Incrementally index every *.jsonl in projects_dir."""
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return 0

    inserted_total = 0
    for jsonl in sorted(projects_dir.glob("*.jsonl")):
        inserted_total += _ingest_file(conn, jsonl)
    return inserted_total


def _ingest_file(conn: sqlite3.Connection, path: Path) -> int:
    """Ingest one JSONL file. Returns count of newly inserted turns."""
    try:
        st = path.stat()
    except OSError as e:
        logger.warning("cannot stat %s: %s", path, e)
        return 0

    cur = conn.execute(
        "SELECT mtime_ns, size_bytes, last_offset, records_total "
        "FROM files WHERE path = ?",
        (str(path),),
    )
    existing = cur.fetchone()

    affected_sessions: set[str] = set()

    if existing is None:
        start_offset = 0
        records_total = 0
        reindex_from_scratch = False
    else:
        prev_mtime, prev_size, prev_offset, _ = existing
        if st.st_mtime_ns == prev_mtime and st.st_size == prev_size:
            return 0
        can_resume = st.st_size > prev_size and _is_safe_append(conn, path, prev_offset)
        if can_resume:
            start_offset = prev_offset
            records_total = existing[3]
            reindex_from_scratch = False
        else:
            start_offset = 0
            records_total = 0
            reindex_from_scratch = True
            affected_sessions.update(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT session_id FROM turns WHERE file_path = ?",
                    (str(path),),
                ).fetchall()
            )

    inserted = 0
    new_offset = start_offset

    try:
        with open(path, "rb") as f:
            if reindex_from_scratch:
                # Any on-disk rewrite can invalidate the saved offset, so rebuild the file.
                conn.execute("DELETE FROM turns WHERE file_path = ?", (str(path),))
            f.seek(start_offset)
            while True:
                line_start = f.tell()
                raw = f.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    new_offset = f.tell()
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("malformed JSON at %s offset %d", path, line_start)
                    new_offset = f.tell()
                    continue
                turns = route_record(record)
                for turn in turns:
                    affected_sessions.add(turn.session_id)
                    if _insert_turn(conn, turn, str(path)):
                        inserted += 1
                records_total += len(turns)
                new_offset = f.tell()
    except OSError as e:
        logger.warning("error reading %s: %s", path, e)

    conn.execute(
        "INSERT INTO files (path, mtime_ns, size_bytes, last_offset, records_total) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "  mtime_ns = excluded.mtime_ns, "
        "  size_bytes = excluded.size_bytes, "
        "  last_offset = excluded.last_offset, "
        "  records_total = excluded.records_total",
        (str(path), st.st_mtime_ns, st.st_size, new_offset, records_total),
    )

    if reindex_from_scratch:
        for session_id in sorted(affected_sessions):
            _rebuild_session_turn_indices(conn, session_id)

    conn.commit()
    return inserted


def _insert_turn(conn: sqlite3.Connection, turn: Turn, file_path: str) -> bool:
    """Insert a Turn, computing its turn_index. Returns True iff a new row was added."""
    row = conn.execute(
        "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM turns WHERE session_id = ?",
        (turn.session_id,),
    ).fetchone()
    next_index = row[0] if row else 0
    try:
        conn.execute(
            "INSERT INTO turns "
            "(session_id, file_path, turn_index, uuid, parent_uuid, ts, role, "
            " tool_name, content, cwd, git_branch) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                turn.session_id,
                file_path,
                next_index,
                turn.uuid,
                turn.parent_uuid,
                turn.ts,
                turn.role,
                turn.tool_name,
                turn.content,
                turn.cwd,
                turn.git_branch,
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def _rebuild_session_turn_indices(conn: sqlite3.Connection, session_id: str) -> None:
    rows = conn.execute(
        "SELECT id FROM turns WHERE session_id = ? ORDER BY ts, id",
        (session_id,),
    ).fetchall()
    for turn_index, row in enumerate(rows):
        conn.execute(
            "UPDATE turns SET turn_index = ? WHERE id = ?",
            (turn_index, row[0]),
        )


def _is_safe_append(conn: sqlite3.Connection, path: Path, prev_offset: int) -> bool:
    expected = conn.execute(
        "SELECT session_id, uuid, parent_uuid, ts, role, tool_name, content, cwd, git_branch "
        "FROM turns WHERE file_path = ? ORDER BY id",
        (str(path),),
    ).fetchall()
    actual: list[tuple[str, str, str | None, str, str, str | None, str, str | None, str | None]] = []

    try:
        with open(path, "rb") as f:
            while f.tell() < prev_offset:
                raw = f.readline()
                if not raw:
                    return False
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                actual.extend(_turn_key(turn) for turn in route_record(record))
    except OSError:
        return False

    return actual == expected and prev_offset <= path.stat().st_size


def _turn_key(turn: Turn) -> tuple[str, str, str | None, str, str, str | None, str, str | None, str | None]:
    return (
        turn.session_id,
        turn.uuid,
        turn.parent_uuid,
        turn.ts,
        turn.role,
        turn.tool_name,
        turn.content,
        turn.cwd,
        turn.git_branch,
    )
