"""Workspace project introspection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_POLICY_FILENAME = "PHILOSOPHY.md"


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    has_policy: bool
    policy_source: str | None = None


def list_projects(workspace_root: Path, nexus_root: Path | None = None) -> list[Project]:
    """List directories directly under `workspace_root` as projects.

    Skips hidden dirs (starting with `.`) and dunder dirs (starting with `_`).
    Reports which policy file each project resolves to, mirroring
    `load.resolve_policy`'s lookup order: a project-local `PHILOSOPHY.md`
    wins, then `<nexus_root>/nexus/policies/projects/<name>.md` when
    `nexus_root` is given, else None (meaning the core.md fallback).
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
        if (child / PROJECT_POLICY_FILENAME).is_file():
            policy_source = f"{name}/{PROJECT_POLICY_FILENAME}"
        elif policy_dir and (policy_dir / f"{name}.md").is_file():
            policy_source = f"projects/{name}.md"
        else:
            policy_source = None
        projects.append(
            Project(
                name=name,
                path=child,
                has_policy=policy_source is not None,
                policy_source=policy_source,
            )
        )
    return projects
