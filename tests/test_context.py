from pathlib import Path

from nexus.context import build_context_summary


def test_builds_combined_summary_from_hits_and_docs():
    summary = build_context_summary(
        recall_hits=["Wake offload was completed", "Use hailo tiny for wake"],
        doc_snippets=["README says wake offload is shipped"],
    )

    assert "Prior session context:" in summary
    assert "Project docs:" in summary
    assert "Wake offload was completed" in summary
    assert "Use hailo tiny for wake" in summary
    assert "README says wake offload is shipped" in summary


def test_collapses_multiline_entries_and_drops_blank_items():
    summary = build_context_summary(
        recall_hits=["  First line\nsecond line  ", "   "],
        doc_snippets=["Doc line one\n\nDoc line two", "\t"],
    )

    assert "First line second line" in summary
    assert "Doc line one Doc line two" in summary
    assert "second line" in summary
    assert "Doc line two" in summary
    assert "   " not in summary
    assert "\n- \n" not in summary


def test_agent_adapters_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "nexus" / "adapters" / "claude" / "CLAUDE.md").exists()
    assert (root / "nexus" / "adapters" / "codex" / "AGENTS.md").exists()
