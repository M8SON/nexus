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
