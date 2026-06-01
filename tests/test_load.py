from pathlib import Path

import pytest

from nexus.load import PolicyResolution, resolve_policy


def _make_nexus_root(tmp_path: Path) -> Path:
    nexus_root = tmp_path / "nexus_repo"
    policies = nexus_root / "nexus" / "policies"
    (policies / "projects").mkdir(parents=True)
    (policies / "core.md").write_text("# Karpathy core policy\nThink before coding.")
    return nexus_root


def test_returns_project_policy_when_file_exists(tmp_path):
    nexus_root = _make_nexus_root(tmp_path)
    project_md = nexus_root / "nexus" / "policies" / "projects" / "book.md"
    project_md.write_text("# Writing policy\nShow, don't tell.")

    result = resolve_policy("book", nexus_root)

    assert result.source == "projects/book.md"
    assert "Show, don't tell." in result.text
    assert result.bootstrap_note is None


def test_falls_back_to_core_with_bootstrap_note(tmp_path):
    nexus_root = _make_nexus_root(tmp_path)

    result = resolve_policy("book", nexus_root)

    assert result.source == "core.md"
    assert "Karpathy core policy" in result.text
    assert result.bootstrap_note is not None
    assert "projects/book.md" in result.bootstrap_note


def test_raises_when_core_missing(tmp_path):
    nexus_root = tmp_path / "nexus_repo"
    (nexus_root / "nexus" / "policies" / "projects").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="core.md"):
        resolve_policy("book", nexus_root)


def test_rejects_invalid_project_names(tmp_path):
    nexus_root = _make_nexus_root(tmp_path)

    for bad in ["../secret", "a/b", ".hidden", ""]:
        with pytest.raises(ValueError, match="invalid project name"):
            resolve_policy(bad, nexus_root)


from unittest.mock import patch

from nexus.load import mempalace_search


def test_search_returns_stdout_on_success():
    fake_completed = type("R", (), {"returncode": 0, "stdout": "hit one\nhit two\n", "stderr": ""})()
    with patch("nexus.load.subprocess.run", return_value=fake_completed) as run:
        out = mempalace_search("chapter 3", wing="_x_book", limit=5)

    assert out == "hit one\nhit two\n"
    cmd = run.call_args.args[0]
    assert cmd[1:] == ["search", "chapter 3", "--wing", "_x_book", "--results", "5"]


def test_search_returns_empty_on_nonzero_exit():
    fake = type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()
    with patch("nexus.load.subprocess.run", return_value=fake):
        out = mempalace_search("q", wing="_x", limit=3)
    assert out == ""


def test_search_returns_empty_on_timeout():
    import subprocess
    with patch(
        "nexus.load.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="mempalace", timeout=10),
    ):
        out = mempalace_search("q", wing="_x", limit=3)
    assert out == ""


def test_search_raises_when_binary_missing(monkeypatch):
    monkeypatch.setattr("nexus.load._resolve_mempalace_bin", lambda: "/no/such/mempalace")
    with patch(
        "nexus.load.subprocess.run",
        side_effect=FileNotFoundError("not there"),
    ):
        with pytest.raises(FileNotFoundError):
            mempalace_search("q", wing="_x", limit=3)
