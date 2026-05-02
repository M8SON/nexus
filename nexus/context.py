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
