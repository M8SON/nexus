"""Tests for cwd → wing-name resolution."""
from pathlib import Path

import pytest

from nexus.memory.wings import resolve_wing


@pytest.mark.parametrize("cwd, expected", [
    ("/home/daedalus/linux/nexus", "nexus"),
    ("/home/daedalus/linux/nexus/nexus/memory", "nexus"),
    ("/home/daedalus/linux/miniclaw", "miniclaw"),
    ("/home/daedalus/linux/miniclaw/skills/dashboard", "miniclaw"),
])
def test_managed_repo_yields_repo_name(cwd, expected):
    assert resolve_wing(Path(cwd)) == expected


def test_workspace_root_yields_workspace_wing():
    assert resolve_wing(Path("/home/daedalus/linux")) == "workspace"


def test_outside_workspace_yields_none():
    assert resolve_wing(Path("/tmp")) is None
    assert resolve_wing(Path("/home/daedalus")) is None


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
