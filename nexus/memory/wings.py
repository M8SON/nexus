"""Resolve a cwd to a MemPalace wing name."""
from pathlib import Path

from nexus.config import NexusConfig


def resolve_wing(cwd: Path, config: NexusConfig | None = None) -> str | None:
    """Return the wing name for `cwd`, or None if `cwd` is not managed.

    - cwd at <workspace>/<repo>/... → wing = <repo>
    - cwd at <workspace>            → wing = "workspace"
    - anywhere else                 → None

    Symlinks are resolved before matching, so a symlink that points back
    into the workspace is treated as managed.
    """
    config = config or NexusConfig.default()
    workspace = config.workspace_root.resolve()
    cwd = Path(cwd).resolve()

    if cwd == workspace:
        return "workspace"
    if workspace not in cwd.parents:
        return None

    relative = cwd.relative_to(workspace)
    return _normalize(relative.parts[0])


def _normalize(name: str) -> str:
    """Match MemPalace's wing-name normalization: lower + collapse - and space to _."""
    return name.lower().replace(" ", "_").replace("-", "_")
