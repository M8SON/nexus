from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from nexus.config import NexusConfig
from nexus.context import build_context_summary
from nexus.db import open_db
from nexus.doc_recall import discover_context_docs
from nexus.indexer import update
from nexus.query import search


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus")
    subparsers = parser.add_subparsers(dest="command")

    recall = subparsers.add_parser("recall", help="Search indexed session history")
    recall.add_argument("query")
    _add_db_path_arg(recall)
    _add_project_dir_arg(recall)
    recall.add_argument("--limit", type=int, default=3)
    recall.add_argument("--context", type=int, default=0)
    recall.add_argument("--since")
    recall.add_argument("--session")
    recall.add_argument("--role", action="append", dest="roles")
    recall.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Scope hits to turns whose cwd is this path or a subpath",
    )
    recall.set_defaults(handler=_handle_recall)

    index = subparsers.add_parser("index", help="Index transcript JSONL files")
    _add_db_path_arg(index)
    _add_project_dir_arg(index)
    index.set_defaults(handler=_handle_index)

    stats = subparsers.add_parser("stats", help="Show index statistics")
    _add_db_path_arg(stats)
    stats.set_defaults(handler=_handle_stats)

    context = subparsers.add_parser(
        "context", help="Assemble local docs and prior session context"
    )
    context.add_argument("query", nargs="?", default="")
    _add_db_path_arg(context)
    _add_project_dir_arg(context)
    context.add_argument(
        "--repo-path",
        type=Path,
        default=Path.cwd(),
        help="Repository path used for document discovery",
    )
    context.add_argument("--limit", type=int, default=3)
    context.set_defaults(handler=_handle_context)

    doctor = subparsers.add_parser("doctor", help="Check workspace and DB assumptions")
    _add_db_path_arg(doctor)
    doctor.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Workspace root that should contain managed repos",
    )
    doctor.add_argument(
        "--repo-path",
        type=Path,
        default=Path.cwd(),
        help="Repository path to validate",
    )
    doctor.set_defaults(handler=_handle_doctor)

    memory = subparsers.add_parser("memory", help="MemPalace orchestration")
    memory_sub = memory.add_subparsers(dest="memory_command")

    mem_init = memory_sub.add_parser("init", help="Wire MemPalace into both agents")
    mem_init.add_argument("--repo", type=Path, default=None,
                          help="Repo to initialize the wing for (default: cwd)")
    mem_init.add_argument("--mempalace-repo", type=Path, required=True,
                          help="Path to a local MemPalace clone (for hook scripts)")
    mem_init.add_argument("--nexus-root", type=Path,
                          default=Path("/home/daedalus/linux/nexus"),
                          help="Root of the nexus repo (where data/ lives)")
    mem_init.add_argument("--user-prompt-hook", type=Path, required=True,
                          help="Path to the nexus UserPromptSubmit hook script")
    mem_init.add_argument("--skip-backfill", action="store_true")
    mem_init.set_defaults(handler=_handle_memory_init)

    mem_status = memory_sub.add_parser("status", help="Report memory wiring state")
    mem_status.add_argument("--repo", type=Path, default=None)
    mem_status.add_argument("--nexus-root", type=Path,
                            default=Path("/home/daedalus/linux/nexus"))
    mem_status.set_defaults(handler=_handle_memory_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        parser.print_help(sys.stderr)
        return 1

    try:
        args = parser.parse_args(args_list)
    except SystemExit as exc:
        return int(exc.code)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 1
    return int(handler(args))


def _handle_recall(args: argparse.Namespace) -> int:
    with _db(args.db_path) as conn:
        update(conn, _projects_path(args.project_dir))
        hits = search(
            conn,
            args.query,
            limit=args.limit,
            context=args.context,
            since=args.since,
            session=args.session,
            roles=args.roles,
            cwd=str(args.repo) if args.repo else None,
        )

    if not hits:
        print("No recall hits found.")
        return 0

    for hit in hits:
        print(f"[{hit.session_id} #{hit.turn_index} {hit.role}] {hit.content}")
        for turn in hit.context:
            print(f"  [{turn.turn_index} {turn.role}] {turn.content}")
    return 0


def _handle_index(args: argparse.Namespace) -> int:
    project_dir = _projects_path(args.project_dir)
    with _db(args.db_path) as conn:
        inserted = update(conn, project_dir)
    print(f"Indexed {inserted} turns from {project_dir}")
    return 0


def _handle_stats(args: argparse.Namespace) -> int:
    with _db(args.db_path) as conn:
        files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        turns = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM turns").fetchone()[0]
    print(f"db: {args.db_path}")
    print(f"files: {files}")
    print(f"turns: {turns}")
    print(f"sessions: {sessions}")
    return 0


def _handle_context(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo_path)
    with _db(args.db_path) as conn:
        update(conn, _projects_path(args.project_dir))
        hits = (
            search(conn, args.query, limit=args.limit, cwd=str(repo_path))
            if args.query
            else []
        )

    recall_hits = [hit.content for hit in hits]
    doc_snippets = [_read_doc_snippet(path) for path in discover_context_docs(repo_path)]
    summary = build_context_summary(recall_hits=recall_hits, doc_snippets=doc_snippets)
    if summary:
        print(summary)
    else:
        print("No local context found.")
    return 0


def _handle_doctor(args: argparse.Namespace) -> int:
    workspace_root = (
        Path(args.workspace_root)
        if args.workspace_root is not None
        else NexusConfig.default().workspace_root
    )
    config = NexusConfig(workspace_root=workspace_root)
    repo_path = Path(args.repo_path)
    db_path = _resolved_db_path(args.db_path)
    db_parent_ready = db_path.parent.exists() or _parent_path_is_creatable(db_path)

    checks = [
        ("workspace exists", workspace_root.exists()),
        ("repo exists", repo_path.exists()),
        ("managed repo", config.is_managed_repo(repo_path) if repo_path.exists() else False),
        ("db parent ready", db_parent_ready),
    ]

    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("SELECT 1")
            db_ok = True
        except sqlite3.Error:
            db_ok = False
    else:
        db_ok = True
    checks.append(("db path usable", db_ok))

    for label, ok in checks:
        print(f"{label}: {'yes' if ok else 'no'}")
    print(f"workspace root: {workspace_root}")
    print(f"repo path: {repo_path}")
    print(f"db path: {db_path}")
    return 0 if all(ok for _, ok in checks) else 1


def _add_db_path_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite index path",
    )


def _add_project_dir_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Directory containing transcript JSONL files",
    )


def _default_db_path() -> Path:
    return Path(os.path.expanduser("~")) / ".claude" / "tools" / "nexus" / "nexus.db"


def _default_projects_path() -> Path:
    workspace_root = NexusConfig.default().workspace_root
    return (
        Path(os.path.expanduser("~"))
        / ".claude"
        / "projects"
        / _workspace_projects_slug(workspace_root)
    )


def _workspace_projects_slug(workspace_root: Path) -> str:
    return str(Path(workspace_root)).replace("/", "-")


def _resolved_db_path(db_path: Path | None) -> Path:
    return _default_db_path() if db_path is None else Path(db_path)


def _projects_path(project_dir: Path | None) -> Path:
    return _default_projects_path() if project_dir is None else Path(project_dir)


def _db(db_path: Path | None):
    return open_db(_resolved_db_path(db_path))


def _parent_path_is_creatable(path: Path) -> bool:
    parent = path.parent
    for candidate in (parent, *parent.parents):
        if candidate.exists():
            return candidate.is_dir() and os.access(candidate, os.W_OK | os.X_OK)
    return False


def _read_doc_snippet(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    for line in text.splitlines():
        snippet = " ".join(line.split())
        if snippet:
            return f"{path.name}: {snippet}"
    return path.name


def _handle_memory_init(args: argparse.Namespace) -> int:
    from nexus.memory.install import init as install_init

    repo = Path(args.repo) if args.repo else Path.cwd()
    try:
        result = install_init(
            repo=repo,
            mempalace_repo=Path(args.mempalace_repo),
            nexus_root=Path(args.nexus_root),
            user_prompt_hook=Path(args.user_prompt_hook),
            skip_backfill=args.skip_backfill,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"nexus memory init failed: {exc}", file=sys.stderr)
        return 1

    print(f"wing: {result['wing']}")
    print(f"claude settings: {result['claude_settings']}")
    print(f"codex hooks:     {result['codex_hooks']}")
    print(f"backfill done:   {result['backfill_done']}")
    return 0


def _handle_memory_status(args: argparse.Namespace) -> int:
    from nexus.memory.status import status_report

    repo = Path(args.repo) if args.repo else Path.cwd()
    report = status_report(repo=repo, nexus_root=Path(args.nexus_root))
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
