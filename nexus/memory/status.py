"""Read-only status report for `nexus memory status`."""
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from nexus.memory.wings import resolve_wing

_LOG_LINE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+)$")


def default_hook_log() -> Path:
    return Path(os.path.expanduser("~")) / ".cache" / "nexus" / "user-prompt-hook.log"


def hook_log_summary(
    *,
    log_path: Path | None = None,
    window_hours: int = 24,
    now: datetime | None = None,
) -> dict:
    """Count prompt-hook outcomes in the recent window.

    The hook writes one timestamped line per fire: `injected N chars ...` on
    success, `search timed out ...` when the search overran its budget (the
    cold-start case), or `mempalace binary not found ...`. Untimestamped
    lines are stray stderr from mempalace and are ignored.
    """
    log_path = log_path or default_hook_log()
    now = now or datetime.now()
    cutoff = now - timedelta(hours=window_hours)

    summary = {
        "log_path": str(log_path),
        "exists": log_path.is_file(),
        "window_hours": window_hours,
        "injected": 0,
        "timed_out": 0,
        "errors": 0,
        "last_fire": None,
    }
    if not summary["exists"]:
        return summary

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return summary

    for line in lines:
        match = _LOG_LINE.match(line)
        if not match:
            continue
        try:
            stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if stamp < cutoff:
            continue

        message = match.group(2)
        if message.startswith("injected"):
            summary["injected"] += 1
        elif message.startswith("search timed out"):
            summary["timed_out"] += 1
        else:
            summary["errors"] += 1

        if summary["last_fire"] is None or stamp > summary["last_fire"]:
            summary["last_fire"] = stamp

    return summary


def status_report(*, repo: Path, nexus_root: Path) -> dict:
    """Diagnostic snapshot. `nexus_root` is used only to locate the
    backfill marker — palace data lives at mempalace's default path."""
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
