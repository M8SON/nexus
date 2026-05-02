"""Read-only status report for `nexus memory status`."""
import os
import shutil
from pathlib import Path

from nexus.memory.wings import resolve_wing


def status_report(*, repo: Path, nexus_root: Path) -> dict:
    repo = Path(repo).resolve()
    nexus_root = Path(nexus_root)
    home = Path(os.path.expanduser("~"))
    palace = home / ".mempalace" / "palace"

    return {
        "wing": resolve_wing(repo),
        "palace_path": str(palace),
        "palace_exists": palace.is_dir(),
        "claude_settings": str(home / ".claude" / "settings.json"),
        "claude_settings_exists": (home / ".claude" / "settings.json").exists(),
        "codex_hooks": str(home / ".codex" / "hooks.json"),
        "codex_hooks_exists": (home / ".codex" / "hooks.json").exists(),
        "mempalace_on_path": shutil.which("mempalace") is not None,
        "backfill_marker": str(nexus_root / "data" / "backfill_markers" / f"{resolve_wing(repo) or 'unknown'}.done"),
        "backfill_done": (
            nexus_root / "data" / "backfill_markers" / f"{resolve_wing(repo) or 'unknown'}.done"
        ).exists(),
    }
