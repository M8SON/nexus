from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ForgeConfig:
    workspace_root: Path

    @classmethod
    def default(cls) -> "ForgeConfig":
        return cls(workspace_root=Path("/home/daedalus/linux"))

    def is_managed_repo(self, repo_path: Path) -> bool:
        repo = repo_path.resolve()
        root = self.workspace_root.resolve()
        return root == repo or root in repo.parents
