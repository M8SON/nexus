"""Tests for `nexus memory status`."""
from pathlib import Path

from nexus.memory.status import status_report


def test_status_reports_palace_existence(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    nexus_root = workspace / "nexus"
    fake_home = tmp_path / "home"
    (fake_home / ".mempalace" / "palace").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    report = status_report(repo=repo, nexus_root=nexus_root)
    from nexus.memory.wings import path_to_wing
    assert report["wing"] == path_to_wing(repo)
    assert report["palace_exists"] is True


def test_status_handles_missing_palace(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    report = status_report(repo=repo, nexus_root=workspace / "nope")
    assert report["palace_exists"] is False
