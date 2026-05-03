"""Tests for cwd → wing-name resolution."""
from pathlib import Path

import pytest

from nexus.memory.wings import path_to_wing, resolve_wing


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    return workspace


@pytest.mark.parametrize("relative_cwd, repo_name", [
    ("nexus", "nexus"),
    ("nexus/nexus/memory", "nexus"),
    ("miniclaw", "miniclaw"),
    ("miniclaw/skills/dashboard", "miniclaw"),
])
def test_managed_repo_yields_path_derived_wing(workspace, relative_cwd, repo_name):
    """Wing is the resolved repo path, with /, -, and ' ' all → _, lowercased."""
    cwd = workspace / relative_cwd
    cwd.mkdir(parents=True)
    expected = path_to_wing(workspace / repo_name)
    assert resolve_wing(cwd) == expected
    # Sanity-check the actual format on a known shape.
    assert expected.endswith(f"_{repo_name}")
    assert expected.startswith("_")


def test_workspace_root_yields_workspace_wing(workspace):
    assert resolve_wing(workspace) == path_to_wing(workspace)


def test_outside_workspace_yields_none(workspace, tmp_path):
    assert resolve_wing(tmp_path / "elsewhere") is None
    assert resolve_wing(tmp_path) is None


def test_repo_name_with_dashes_collapses_to_underscores(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "my-cool-repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    wing = resolve_wing(repo)
    assert wing == path_to_wing(repo)
    assert wing.endswith("_my_cool_repo")


def test_symlink_resolving_back_into_workspace_is_managed(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "real-repo"
    repo.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.symlink_to(repo)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    assert resolve_wing(elsewhere) == path_to_wing(repo)


def test_path_to_wing_replaces_separators_and_lowers():
    assert path_to_wing(Path("/home/user/linux/nexus")) == "_home_user_linux_nexus"
    assert path_to_wing(Path("/Home/USER/My-Repo")) == "_home_user_my_repo"
    # Match mempalace's normalize_wing_name on Claude Code's path-encoded
    # project dir basename: spaces also collapse to underscores.
    assert path_to_wing(Path("/Users/foo bar/app")) == "_users_foo_bar_app"
