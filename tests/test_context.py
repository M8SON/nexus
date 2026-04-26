from forge.context import build_context_summary


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
