"""Tests for `nexus memory status`."""
from pathlib import Path

from nexus.memory.status import status_report


def test_status_reports_palace_existence(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    nexus_root = workspace / "nexus"
    (nexus_root / "data" / "palace").mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    report = status_report(repo=repo, nexus_root=nexus_root)
    assert report["wing"] == "nexus"
    assert report["palace_exists"] is True


def test_status_handles_missing_palace(tmp_path, monkeypatch):
    workspace = tmp_path / "linux"
    repo = workspace / "nexus"
    repo.mkdir(parents=True)
    monkeypatch.setattr(
        "nexus.memory.wings.NexusConfig.default",
        classmethod(lambda cls: cls(workspace_root=workspace)),
    )

    report = status_report(repo=repo, nexus_root=workspace / "nope")
    assert report["palace_exists"] is False
