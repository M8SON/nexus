"""Project loading: policy resolution + targeted recall."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from nexus.memory.wings import path_to_wing
from nexus.projects import list_projects


@dataclass(frozen=True)
class PolicyResolution:
    """Result of resolving a project's policy file."""

    text: str
    source: str
    bootstrap_note: str | None


def resolve_policy(project: str, nexus_root: Path) -> PolicyResolution:
    """Return the policy text for `project`.

    Prefers `<nexus_root>/nexus/policies/projects/<project>.md`. Falls back
    to `<nexus_root>/nexus/policies/core.md` with a bootstrap note. Raises
    FileNotFoundError if core.md is also missing (broken repo state).
    """
    if not project or "/" in project or project.startswith("."):
        raise ValueError(f"invalid project name: {project!r}")

    policies = Path(nexus_root) / "nexus" / "policies"
    project_md = policies / "projects" / f"{project}.md"
    core_md = policies / "core.md"

    if project_md.is_file():
        return PolicyResolution(
            text=project_md.read_text(encoding="utf-8"),
            source=f"projects/{project}.md",
            bootstrap_note=None,
        )

    if not core_md.is_file():
        raise FileNotFoundError(
            f"neither projects/{project}.md nor core.md exists under {policies}"
        )

    note = (
        f"note: no project policy at projects/{project}.md — using core.md. "
        "Create the file to customize."
    )
    return PolicyResolution(
        text=core_md.read_text(encoding="utf-8"),
        source="core.md",
        bootstrap_note=note,
    )


def _resolve_mempalace_bin() -> str:
    """Locate the mempalace binary.

    Prefers the binary co-located with sys.executable (Claude Code may strip
    PATH so bare lookups fail). Falls back to bare `mempalace`.
    """
    venv_bin = Path(sys.executable).parent / "mempalace"
    if venv_bin.is_file() and os.access(venv_bin, os.X_OK):
        return str(venv_bin)
    return "mempalace"


def mempalace_search(query: str, *, wing: str, limit: int) -> str:
    """Run `mempalace search` and return stdout. Empty on failure
    except missing binary (raises FileNotFoundError so caller can
    distinguish 'unavailable' from 'no hits')."""
    cmd = [
        _resolve_mempalace_bin(),
        "search",
        query,
        "--wing",
        wing,
        "--results",
        str(limit),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


@dataclass(frozen=True)
class LoadResult:
    project: str
    wing: str
    policy: PolicyResolution
    recall: str
    memory_unavailable: bool


def load_project(
    *,
    project: str,
    topic: str,
    workspace_root: Path,
    nexus_root: Path,
    limit: int = 5,
) -> LoadResult:
    """Validate project, resolve policy, run targeted recall.

    Raises ValueError when `project` doesn't exist under `workspace_root`.
    Never raises for missing/timed-out mempalace — surfaces that via
    `memory_unavailable`.
    """
    project_dir = Path(workspace_root) / project
    if not project_dir.is_dir():
        available = ", ".join(p.name for p in list_projects(workspace_root)) or "(none)"
        raise ValueError(
            f"project '{project}' not found under {workspace_root}. "
            f"Available: {available}"
        )

    wing = path_to_wing(project_dir)
    policy = resolve_policy(project, nexus_root)

    memory_unavailable = False
    try:
        recall = mempalace_search(topic, wing=wing, limit=limit)
    except FileNotFoundError:
        recall = ""
        memory_unavailable = True

    return LoadResult(
        project=project,
        wing=wing,
        policy=policy,
        recall=recall,
        memory_unavailable=memory_unavailable,
    )
