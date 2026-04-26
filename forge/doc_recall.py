from pathlib import Path


PRIORITY_FILES = ["WORKING_MEMORY.md", "README.md", "CLAUDE.md", "AGENTS.md"]


def discover_context_docs(repo_root: Path) -> list[Path]:
    repo_root = Path(repo_root)
    docs: list[Path] = []
    seen: set[Path] = set()

    for name in PRIORITY_FILES:
        path = repo_root / name
        if path.is_file() and path not in seen:
            docs.append(path)
            seen.add(path)

    for subdir in ("docs/superpowers/specs", "docs/superpowers/plans"):
        base = repo_root / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            if path.is_file() and path not in seen:
                docs.append(path)
                seen.add(path)

    return docs
