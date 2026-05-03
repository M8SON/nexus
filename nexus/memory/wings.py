"""Resolve a cwd to a MemPalace wing name."""
from pathlib import Path

from nexus.config import NexusConfig


def resolve_wing(cwd: Path, config: NexusConfig | None = None) -> str | None:
    """Return the wing name for `cwd`, or None if `cwd` is not managed.

    - cwd at <workspace>/<repo>/... → wing derived from `<workspace>/<repo>`
    - cwd at <workspace>            → wing derived from `<workspace>`
    - anywhere else                 → None

    Wing names match what MemPalace's auto-mining produces when no
    `--wing` is passed: the absolute path with `/`, `-`, and ` ` all
    collapsed to `_`, lowercased. So `/home/daedalus/linux/nexus`
    becomes `_home_daedalus_linux_nexus`. This aligns nexus's read-side
    queries with mempalace's write-side hooks without forking either.

    Symlinks are resolved before matching.
    """
    config = config or NexusConfig.default()
    workspace = config.workspace_root.resolve()
    cwd = Path(cwd).resolve()

    if cwd == workspace:
        return path_to_wing(workspace)
    if workspace not in cwd.parents:
        return None

    relative = cwd.relative_to(workspace)
    repo_path = workspace / relative.parts[0]
    return path_to_wing(repo_path)


def path_to_wing(path: Path) -> str:
    """Convert an absolute path to mempalace's auto-derived wing name.

    Mempalace's `normalize_wing_name` lowercases and collapses dashes and
    spaces to underscores, applied to the basename of Claude Code's
    path-encoded project dir (e.g. `-home-user-linux-nexus`). The same
    output comes from converting the logical path: `/`, `-`, and ` ` all
    become `_`.
    """
    s = str(path).replace("/", "_").replace(" ", "_").replace("-", "_")
    return s.lower()
