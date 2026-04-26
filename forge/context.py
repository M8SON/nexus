"""Context assembly for recall hits and local docs."""


def build_context_summary(*, recall_hits: list[str], doc_snippets: list[str]) -> str:
    sections: list[str] = []
    if recall_hits:
        sections.append("Prior session context:\n- " + "\n- ".join(recall_hits))
    if doc_snippets:
        sections.append("Project docs:\n- " + "\n- ".join(doc_snippets))
    return "\n\n".join(sections).strip()
