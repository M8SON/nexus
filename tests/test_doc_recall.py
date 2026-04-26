from forge.doc_recall import discover_context_docs


def test_discovers_priority_project_docs(tmp_path):
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    (tmp_path / "WORKING_MEMORY.md").write_text("memory", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    docs = discover_context_docs(tmp_path)
    assert [doc.name for doc in docs][:4] == [
        "WORKING_MEMORY.md",
        "CLAUDE.md",
        "AGENTS.md",
        "README.md",
    ]


def test_includes_specs_and_plans_when_present(tmp_path):
    specs = tmp_path / "docs" / "superpowers" / "specs"
    plans = tmp_path / "docs" / "superpowers" / "plans"
    nested_specs = specs / "nested"
    nested_plans = plans / "deeper"
    nested_specs.mkdir(parents=True)
    nested_plans.mkdir(parents=True)
    (nested_specs / "a.md").write_text("spec", encoding="utf-8")
    (nested_plans / "b.md").write_text("plan", encoding="utf-8")
    docs = discover_context_docs(tmp_path)
    names = {doc.name for doc in docs}
    assert "a.md" in names
    assert "b.md" in names
