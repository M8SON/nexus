"""Project loading: policy resolution + targeted recall."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
