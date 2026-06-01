from pathlib import Path

from nexus.context import build_context_summary, build_lean_baseline


def test_builds_combined_summary_from_hits_and_docs():
    summary = build_context_summary(
        recall_hits=["Wake offload was completed", "Use hailo tiny for wake"],
        doc_snippets=["README says wake offload is shipped"],
    )
    assert "Prior session context:" in summary
    assert "Project docs:" in summary
    assert "Wake offload was completed" in summary


def test_collapses_multiline_entries_and_drops_blank_items():
    summary = build_context_summary(
        recall_hits=["  First line\nsecond line  ", "   "],
        doc_snippets=["Doc line one\n\nDoc line two", "\t"],
    )
    assert "First line second line" in summary
    assert "Doc line one Doc line two" in summary


def test_lean_baseline_includes_projects_and_instruction():
    out = build_lean_baseline(
        identity="Mason Misch (M8SON). Builds MiniClaw and Nexus.",
        project_names=["book", "miniclaw", "nexus"],
        doc_snippets=["CLAUDE.md: Nexus-managed workspace"],
    )
    assert "Mason Misch" in out
    assert "Workspace projects available: book, miniclaw, nexus" in out
    assert "nexus load <project> --topic" in out
    assert "Project docs:" in out
    assert "CLAUDE.md" in out


def test_lean_baseline_omits_identity_when_absent():
    out = build_lean_baseline(
        identity=None,
        project_names=["book"],
        doc_snippets=[],
    )
    assert "Mason" not in out
    assert "Workspace projects available: book" in out


def test_lean_baseline_handles_empty_projects():
    out = build_lean_baseline(identity=None, project_names=[], doc_snippets=[])
    assert "no projects found" in out.lower()


def test_agent_adapters_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "nexus" / "adapters" / "claude" / "CLAUDE.md").exists()
    assert (root / "nexus" / "adapters" / "codex" / "AGENTS.md").exists()
