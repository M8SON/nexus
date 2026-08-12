from pathlib import Path

from nexus.projects import list_projects


def test_lists_directories_under_workspace(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / "miniclaw").mkdir(parents=True)
    (workspace / "nexus").mkdir(parents=True)
    (workspace / "not-a-dir.txt").write_text("ignore me")

    projects = list_projects(workspace)

    names = [p.name for p in projects]
    assert names == ["book", "miniclaw", "nexus"]


def test_includes_policy_presence_flag(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / "miniclaw").mkdir(parents=True)

    nexus_root = tmp_path / "nexus_repo"
    projects_policy_dir = nexus_root / "nexus" / "policies" / "projects"
    projects_policy_dir.mkdir(parents=True)
    (projects_policy_dir / "book.md").write_text("writing rules")

    projects = list_projects(workspace, nexus_root=nexus_root)

    by_name = {p.name: p for p in projects}
    assert by_name["book"].has_policy is True
    assert by_name["miniclaw"].has_policy is False
    assert by_name["book"].path == workspace / "book"


def test_returns_empty_when_workspace_missing(tmp_path):
    projects = list_projects(tmp_path / "does-not-exist")
    assert projects == []


def test_skips_hidden_and_underscore_dirs(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / ".git").mkdir()
    (workspace / "__pycache__").mkdir()

    projects = list_projects(workspace)
    assert [p.name for p in projects] == ["book"]


def test_returns_false_has_policy_when_projects_dir_missing(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    nexus_root = tmp_path / "nexus_repo"
    # Note: no policies/projects/ subdir created.

    projects = list_projects(workspace, nexus_root=nexus_root)

    assert len(projects) == 1
    assert projects[0].has_policy is False


def test_project_local_philosophy_wins_over_projects_dir(tmp_path):
    """list_projects must mirror resolve_policy's lookup order."""
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / "book" / "PHILOSOPHY.md").write_text("writing rules")

    nexus_root = tmp_path / "nexus_repo"
    projects_policy_dir = nexus_root / "nexus" / "policies" / "projects"
    projects_policy_dir.mkdir(parents=True)
    (projects_policy_dir / "book.md").write_text("shadowed")

    projects = list_projects(workspace, nexus_root=nexus_root)

    assert projects[0].policy_source == "book/PHILOSOPHY.md"
    assert projects[0].has_policy is True


def test_project_local_philosophy_detected_without_nexus_root(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    (workspace / "book" / "PHILOSOPHY.md").write_text("writing rules")

    projects = list_projects(workspace)

    assert projects[0].policy_source == "book/PHILOSOPHY.md"


def test_policy_source_is_none_when_falling_back_to_core(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "nexus").mkdir(parents=True)

    projects = list_projects(workspace)

    assert projects[0].policy_source is None
    assert projects[0].has_policy is False


def test_policy_source_reports_projects_dir_override(tmp_path):
    workspace = tmp_path / "linux"
    (workspace / "book").mkdir(parents=True)
    nexus_root = tmp_path / "nexus_repo"
    projects_policy_dir = nexus_root / "nexus" / "policies" / "projects"
    projects_policy_dir.mkdir(parents=True)
    (projects_policy_dir / "book.md").write_text("writing rules")

    projects = list_projects(workspace, nexus_root=nexus_root)

    assert projects[0].policy_source == "projects/book.md"
