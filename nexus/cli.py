from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from nexus.config import NexusConfig
from nexus.doc_recall import discover_context_docs


def _default_nexus_root() -> Path:
    """Resolve the path to this nexus repo for CLI default values.

    Order: `NEXUS_ROOT` env var, else infer from this file's location
    (`<repo>/nexus/cli.py`, so `parents[1]` is the repo root).
    """
    env = os.environ.get("NEXUS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus")
    subparsers = parser.add_subparsers(dest="command")

    context = subparsers.add_parser(
        "context", help="Emit lean SessionStart baseline"
    )
    context.add_argument(
        "--repo-path",
        type=Path,
        default=Path.cwd(),
        help="Repository path used for document discovery",
    )
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
    doctor.set_defaults(handler=_handle_doctor)

    memory = subparsers.add_parser("memory", help="MemPalace orchestration")
    memory_sub = memory.add_subparsers(dest="memory_command")

    default_nexus_root = _default_nexus_root()

    mem_init = memory_sub.add_parser("init", help="Wire MemPalace into both agents")
    mem_init.add_argument("--repo", type=Path, default=None,
                          help="Repo to initialize the wing for (default: cwd)")
    mem_init.add_argument("--mempalace-repo", type=Path, required=True,
                          help="Path to a local MemPalace clone (for hook scripts)")
    mem_init.add_argument("--nexus-root", type=Path,
                          default=default_nexus_root,
                          help="Root of the nexus repo (where data/ lives). "
                               "Defaults to $NEXUS_ROOT or auto-detection.")
    mem_init.add_argument("--user-prompt-hook", type=Path, required=True,
                          help="Path to the nexus UserPromptSubmit hook script")
    mem_init.add_argument("--skip-backfill", action="store_true")
    mem_init.set_defaults(handler=_handle_memory_init)

    mem_status = memory_sub.add_parser("status", help="Report memory wiring state")
    mem_status.add_argument("--repo", type=Path, default=None)
    mem_status.add_argument("--nexus-root", type=Path,
                            default=default_nexus_root)
    mem_status.set_defaults(handler=_handle_memory_status)

    mem_rename = memory_sub.add_parser(
        "rename-wing",
        help="Rewrite the wing metadata field on every drawer "
             "in --from to --to (use after moving your workspace path).",
    )
    mem_rename.add_argument("--from", dest="from_wing", required=True,
                            help="Source wing name")
    mem_rename.add_argument("--to", dest="to_wing", required=True,
                            help="Destination wing name")
    mem_rename.set_defaults(handler=_handle_memory_rename)

    load_p = subparsers.add_parser(
        "load",
        help="Load per-project policy + targeted recall by topic",
    )
    load_p.add_argument("project", help="Project name (folder under workspace)")
    load_p.add_argument("--topic", required=True, help="Topic query for recall")
    load_p.add_argument("--limit", type=int, default=5)
    load_p.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Workspace root (default: NEXUS_WORKSPACE_ROOT env or auto)",
    )
    load_p.add_argument(
        "--nexus-root",
        type=Path,
        default=default_nexus_root,
    )
    load_p.set_defaults(handler=_handle_load)

    lp = subparsers.add_parser("list-projects", help="List workspace projects")
    lp.add_argument("--workspace-root", type=Path, default=None)
    lp.add_argument("--nexus-root", type=Path, default=default_nexus_root)
    lp.set_defaults(handler=_handle_list_projects)

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


def _read_identity_blurb() -> str | None:
    """Read `~/.mempalace/identity.txt` if it exists. Empty file → None."""
    path = Path(os.path.expanduser("~")) / ".mempalace" / "identity.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _handle_context(args: argparse.Namespace) -> int:
    from nexus.context import build_lean_baseline
    from nexus.projects import list_projects

    repo_path = Path(args.repo_path).resolve()
    workspace_root = NexusConfig.default().workspace_root.resolve()

    if workspace_root != repo_path and workspace_root not in repo_path.parents:
        # cwd is outside the managed workspace — silent no-op.
        return 0

    projects = list_projects(workspace_root)
    doc_snippets = [_read_doc_snippet(p) for p in discover_context_docs(repo_path)]
    identity = _read_identity_blurb()

    out = build_lean_baseline(
        identity=identity,
        project_names=[p.name for p in projects],
        doc_snippets=doc_snippets,
    )
    print(out or "No local context found.")
    return 0


def _handle_load(args: argparse.Namespace) -> int:
    from nexus.load import load_project

    workspace_root = (
        Path(args.workspace_root)
        if args.workspace_root is not None
        else NexusConfig.default().workspace_root
    )

    try:
        result = load_project(
            project=args.project,
            topic=args.topic,
            workspace_root=workspace_root,
            nexus_root=Path(args.nexus_root),
            limit=args.limit,
        )
    except ValueError as exc:
        print(f"nexus load: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"nexus load: {exc}", file=sys.stderr)
        return 1

    print(f"# Project policy: {result.project} (source: {result.policy.source})")
    if result.policy.bootstrap_note:
        print(result.policy.bootstrap_note)
    print()
    print(result.policy.text.rstrip())
    print()
    print(f'# Recall hits for "{args.topic}" (wing: {result.wing})')
    if result.memory_unavailable:
        print("(memory unavailable — mempalace binary not found)")
    elif result.recall.strip():
        print(result.recall.rstrip())
    else:
        print("(no prior recall for this topic)")
    return 0


def _handle_list_projects(args: argparse.Namespace) -> int:
    from nexus.memory.wings import path_to_wing
    from nexus.projects import list_projects

    workspace_root = (
        Path(args.workspace_root)
        if args.workspace_root is not None
        else NexusConfig.default().workspace_root
    )

    projects = list_projects(workspace_root, nexus_root=Path(args.nexus_root))
    if not projects:
        print("(no projects found)")
        return 0

    rows = [("project", "wing", "policy")]
    for p in projects:
        policy_label = f"projects/{p.name}.md" if p.has_policy else "core (default)"
        rows.append((p.name, path_to_wing(p.path), policy_label))

    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    for r in rows:
        print(f"{r[0]:<{widths[0]}}  {r[1]:<{widths[1]}}  {r[2]:<{widths[2]}}")
    return 0



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

    home = Path(os.path.expanduser("~"))
    palace_dir = home / ".mempalace" / "palace"
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
    if result.get("claude_mcp_registered"):
        print("claude mcp:      registered (mempalace, scope=user)")
    else:
        reason = result.get("claude_mcp_reason") or "unknown"
        print(f"claude mcp:      NOT registered ({reason}); in-session recall unavailable")
    print(f"backfill done:   {result['backfill_done']}")
    return 0


def _handle_memory_rename(args: argparse.Namespace) -> int:
    from nexus.memory.migration import rename_wing

    try:
        result = rename_wing(args.from_wing, args.to_wing)
    except (ValueError, RuntimeError) as exc:
        print(f"rename-wing failed: {exc}", file=sys.stderr)
        return 1

    if result.get("noop"):
        print(f"noop: --from and --to are both {args.from_wing!r}")
    else:
        print(f"moved {result['moved']} drawers: {result['from']} -> {result['to']}")
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
