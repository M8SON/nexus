from pathlib import Path
import tomllib

from nexus.config import NexusConfig


def test_project_files_exist():
    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"

    assert pyproject.exists()
    assert (root / "nexus" / "__init__.py").exists()
    assert (root / "README.md").exists()

    data = tomllib.loads(pyproject.read_text())
    assert data["project"]["name"] == "nexus"
    assert data["project"]["readme"] == "README.md"
    assert "scripts" not in data["project"]


def test_workspace_repo_is_enabled_under_linux_root(tmp_path):
    repo = tmp_path / "linux" / "demo"
    repo.mkdir(parents=True)
    cfg = NexusConfig(workspace_root=tmp_path / "linux")
    assert cfg.is_managed_repo(repo) is True


def test_repo_outside_workspace_is_not_enabled(tmp_path):
    repo = tmp_path / "other" / "demo"
    repo.mkdir(parents=True)
    cfg = NexusConfig(workspace_root=tmp_path / "linux")
    assert cfg.is_managed_repo(repo) is False


def test_policy_and_skill_docs_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "nexus" / "policies" / "core.md").exists()
    assert (root / "nexus" / "policies" / "continuity.md").exists()
    assert (root / "nexus" / "skills" / "README.md").exists()
