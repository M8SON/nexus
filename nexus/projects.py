"""Workspace project introspection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    has_policy: bool


def list_projects(workspace_root: Path, nexus_root: Path | None = None) -> list[Project]:
    """List directories directly under `workspace_root` as projects.

    Skips hidden dirs (starting with `.`) and dunder dirs (starting with `_`).
    If `nexus_root` is provided, flags whether each project has a policy file at
    `<nexus_root>/nexus/policies/projects/<name>.md`.
    """
    workspace_root = Path(workspace_root)
    if not workspace_root.is_dir():
        return []

    policy_dir: Path | None = None
    if nexus_root is not None:
        policy_dir = Path(nexus_root) / "nexus" / "policies" / "projects"

    projects: list[Project] = []
    for child in sorted(workspace_root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith(".") or name.startswith("_"):
            continue
        has_policy = bool(policy_dir and (policy_dir / f"{name}.md").is_file())
        projects.append(Project(name=name, path=child, has_policy=has_policy))
    return projects
