"""Tests for `nexus memory status`."""
from datetime import datetime
from pathlib import Path

from nexus.memory.status import hook_log_summary, status_report


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


def _write_log(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_hook_log_summary_counts_outcomes_in_window(tmp_path):
    log = tmp_path / "hook.log"
    now = datetime(2026, 8, 11, 12, 0, 0)
    _write_log(log, [
        "[2026-08-11 11:59:00] injected 100 chars for wing w",
        "[2026-08-11 11:58:00] injected 200 chars for wing w",
        "[2026-08-11 11:57:00] search timed out after 15s for wing w",
        "[2026-08-11 11:56:00] mempalace binary not found (set MEMPALACE_BIN to override)",
    ])

    s = hook_log_summary(log_path=log, now=now)

    assert (s["injected"], s["timed_out"], s["errors"]) == (2, 1, 1)
    assert s["last_fire"] == datetime(2026, 8, 11, 11, 59, 0)


def test_hook_log_summary_excludes_entries_outside_window(tmp_path):
    log = tmp_path / "hook.log"
    now = datetime(2026, 8, 11, 12, 0, 0)
    _write_log(log, [
        "[2026-08-09 12:00:00] injected 100 chars for wing w",
        "[2026-08-11 11:00:00] injected 100 chars for wing w",
    ])

    s = hook_log_summary(log_path=log, window_hours=24, now=now)

    assert s["injected"] == 1


def test_hook_log_summary_ignores_untimestamped_stderr(tmp_path):
    log = tmp_path / "hook.log"
    now = datetime(2026, 8, 11, 12, 0, 0)
    _write_log(log, [
        "EmbedderIdentityUnknownWarning: palace collection has no identity",
        "  _enforce_embedder_identity(collection, palace_path)",
        "[2026-08-11 11:00:00] injected 100 chars for wing w",
    ])

    s = hook_log_summary(log_path=log, now=now)

    assert (s["injected"], s["timed_out"], s["errors"]) == (1, 0, 0)


def test_hook_log_summary_reports_missing_log(tmp_path):
    s = hook_log_summary(log_path=tmp_path / "nope.log")

    assert s["exists"] is False
    assert s["injected"] == 0
    assert s["last_fire"] is None
