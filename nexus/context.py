"""Context assembly for recall hits and local docs."""


def build_context_summary(*, recall_hits: list[str], doc_snippets: list[str]) -> str:
    recall_hits = _clean_entries(recall_hits)
    doc_snippets = _clean_entries(doc_snippets)
    sections: list[str] = []
    if recall_hits:
        sections.append("Prior session context:\n- " + "\n- ".join(recall_hits))
    if doc_snippets:
        sections.append("Project docs:\n- " + "\n- ".join(doc_snippets))
    return "\n\n".join(sections).strip()


def _clean_entries(entries: list[str]) -> list[str]:
    cleaned: list[str] = []
    for entry in entries:
        text = " ".join(entry.split())
        if text:
            cleaned.append(text)
    return cleaned


def build_lean_baseline(
    *,
    identity: str | None,
    project_names: list[str],
    doc_snippets: list[str],
) -> str:
    """Lean SessionStart context: identity + project list + load instruction + docs.

    No L1 essential story. The caller (e.g. SessionStart hook) is expected
    to wait for the user's first message and then run `nexus load`.
    """
    doc_snippets = _clean_entries(doc_snippets)
    sections: list[str] = []

    if identity:
        sections.append(identity.strip())

    if project_names:
        sections.append(
            "Workspace projects available: " + ", ".join(project_names) + "\n"
            "When the user states what they want to work on today, run:\n"
            "  nexus load <project> --topic \"<their message>\"\n"
            "Do not pre-load anything else."
        )
    else:
        sections.append("(no projects found under workspace; nothing to load)")

    if doc_snippets:
        sections.append("Project docs:\n- " + "\n- ".join(doc_snippets))

    return "\n\n".join(sections).strip()
