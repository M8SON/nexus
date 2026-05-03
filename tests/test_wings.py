"""Tests for cwd → wing-name resolution."""
from pathlib import Path

import pytest

from nexus.memory.wings import resolve_wing


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    return workspace


@pytest.mark.parametrize("relative_cwd, expected", [
    ("nexus", "nexus"),
    ("nexus/nexus/memory", "nexus"),
    ("miniclaw", "miniclaw"),
    ("miniclaw/skills/dashboard", "miniclaw"),
])
def test_managed_repo_yields_repo_name(workspace, relative_cwd, expected):
    cwd = workspace / relative_cwd
    cwd.mkdir(parents=True)
    assert resolve_wing(cwd) == expected


def test_workspace_root_yields_workspace_wing(workspace):
    assert resolve_wing(workspace) == "workspace"


def test_outside_workspace_yields_none(workspace, tmp_path):
    assert resolve_wing(tmp_path / "elsewhere") is None
    assert resolve_wing(tmp_path) is None


def test_repo_name_with_dashes_is_normalized(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "my-cool-repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )
    assert resolve_wing(repo) == "my_cool_repo"


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
    assert resolve_wing(elsewhere) == "real_repo"
