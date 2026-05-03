import os
from dataclasses import dataclass
from pathlib import Path


def _discover_workspace_root() -> Path:
    """Resolve the managed workspace root.

    Order: `NEXUS_WORKSPACE_ROOT` env var, else infer from this package's
    location. Nexus lives at `<workspace>/nexus/nexus/config.py`, so
    `parents[2]` of this file is the workspace.
    """
    env = os.environ.get("NEXUS_WORKSPACE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class NexusConfig:
    workspace_root: Path

    @classmethod
    def default(cls) -> "NexusConfig":
        return cls(workspace_root=_discover_workspace_root())

    def is_managed_repo(self, repo_path: Path) -> bool:
        repo = repo_path.resolve()
        root = self.workspace_root.resolve()
        return root == repo or root in repo.parents
