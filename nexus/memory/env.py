"""Assemble env-var blocks for MemPalace invocations."""
from pathlib import Path


NEXUS_ROOT_DEFAULT = Path("/home/daedalus/linux/nexus")


def mempalace_env(
    wing: str,
    repo_root: Path,
    nexus_root: Path | None = None,
) -> dict[str, str]:
    """Env block to pass when invoking MemPalace under nexus."""
    root = Path(nexus_root or NEXUS_ROOT_DEFAULT)
    return {
        "MEMPALACE_PALACE_PATH": str(root / "data" / "palace"),
        "STATE_DIR": str(root / "data" / "hook_state"),
        "MEMPAL_DIR": str(Path(repo_root)),
    }
