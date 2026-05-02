from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from nexus.config import NexusConfig
from nexus.context import build_context_summary
from nexus.doc_recall import discover_context_docs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus")
    subparsers = parser.add_subparsers(dest="command")

    context = subparsers.add_parser(
        "context", help="Assemble local docs and prior session context"
    )
    context.add_argument("query", nargs="?", default="")
    _add_project_dir_arg(context)
    context.add_argument(
        "--repo-path",
        type=Path,
        default=Path.cwd(),
        help="Repository path used for document discovery",
    )
    context.add_argument("--limit", type=int, default=3)
    context.set_defaults(handler=_handle_context)

    doctor = subparsers.add_parser("doctor", help="Check workspace and memory wiring")
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
    doctor.add_argument(
        "--nexus-root",
        type=Path,
        default=Path("/home/daedalus/linux/nexus"),
        help="Root of the nexus repo (where data/palace lives)",
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


def _handle_context(args: argparse.Namespace) -> int:
    from nexus.memory.wings import resolve_wing
    from nexus.memory.env import mempalace_env

    repo_path = Path(args.repo_path).resolve()
    wing = resolve_wing(repo_path)

    recall_hits: list[str] = []
    if wing:
        env = mempalace_env(wing=wing, repo_root=repo_path)
        try:
            output = _mempalace_wake_up(wing=wing, env=env)
        except Exception:
            output = ""
        if output.strip():
            recall_hits = [output.strip()]

    doc_snippets = [_read_doc_snippet(p) for p in discover_context_docs(repo_path)]
    summary = build_context_summary(recall_hits=recall_hits, doc_snippets=doc_snippets)
    print(summary or "No local context found.")
    return 0


def _mempalace_wake_up(wing: str, env: dict[str, str]) -> str:
    """Run `mempalace wake-up --wing <wing>` with a 10s timeout. Empty on failure."""
    import subprocess
    full_env = {**os.environ, **env}
    try:
        proc = subprocess.run(
            ["mempalace", "wake-up", "--wing", wing],
            capture_output=True, text=True, timeout=10, env=full_env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _handle_doctor(args: argparse.Namespace) -> int:
    workspace_root = (
        Path(args.workspace_root)
        if args.workspace_root is not None
        else NexusConfig.default().workspace_root
    )
    config = NexusConfig(workspace_root=workspace_root)
    repo_path = Path(args.repo_path)

    fatal_checks = [
        ("workspace exists", workspace_root.exists()),
        ("repo exists", repo_path.exists()),
        ("managed repo", config.is_managed_repo(repo_path) if repo_path.exists() else False),
    ]

    palace_dir = Path(args.nexus_root) / "data" / "palace"
    home = Path(os.path.expanduser("~"))
    info_checks = [
        ("palace path exists", palace_dir.is_dir()),
        ("mempalace on path", shutil.which("mempalace") is not None),
        ("claude hooks installed", (home / ".claude" / "settings.json").exists()),
    ]

    for label, ok in fatal_checks + info_checks:
        print(f"{label}: {'yes' if ok else 'no'}")
    print(f"workspace root: {workspace_root}")
    print(f"repo path: {repo_path}")
    return 0 if all(ok for _, ok in fatal_checks) else 1


def _add_project_dir_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Directory containing transcript JSONL files",
    )


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
