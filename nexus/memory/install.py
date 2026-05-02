"""Install MemPalace + nexus hooks into Claude Code and Codex CLI configs."""
import json
import os
import shutil
from pathlib import Path


def _safe_write_json(path: Path, data: dict) -> None:
    """Atomically write `data` as JSON to `path`, with a once-only `.bak` of the original.

    - Writes a `.bak` sibling on the very first call only (preserves the
      true pre-nexus state across re-runs).
    - Writes via `<path>.tmp` + `os.replace()` so a crash mid-write never
      leaves a torn or truncated config file.
    """
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists() and not backup.exists():
        shutil.copyfile(path, backup)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge_claude_hooks(
    *,
    settings_path: Path,
    save_hook: str,
    precompact_hook: str,
    user_prompt_hook: str,
) -> None:
    """Idempotently add Stop, PreCompact, UserPromptSubmit hooks to a settings.json."""
    settings_path = Path(settings_path)
    raw = settings_path.read_text(encoding="utf-8") if settings_path.exists() else "{}"

    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}

    hooks = data.setdefault("hooks", {})
    _ensure_hook(hooks, "Stop", save_hook, matcher="*")
    _ensure_hook(hooks, "PreCompact", precompact_hook, matcher=None)
    _ensure_hook(hooks, "UserPromptSubmit", user_prompt_hook, matcher=None)

    _safe_write_json(settings_path, data)


def _ensure_hook(
    hooks: dict, event: str, command: str, *, matcher: str | None
) -> None:
    """Append a hook entry only if no entry already has this command for this event."""
    entries = hooks.setdefault(event, [])
    for existing in entries:
        for h in existing.get("hooks", [existing]):
            if str(h.get("command", "")) == command:
                return
    entry: dict = {
        "hooks": [{"type": "command", "command": command, "timeout": 30}],
    }
    if matcher is not None:
        entry["matcher"] = matcher
    entries.append(entry)


def write_codex_hooks(
    *, target: Path, save_hook: str, precompact_hook: str
) -> None:
    """Idempotently write/merge ~/.codex/hooks.json."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    raw = target.read_text(encoding="utf-8") if target.exists() else "{}"
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}

    _add_codex_entry(data, "Stop", save_hook)
    _add_codex_entry(data, "PreCompact", precompact_hook)

    _safe_write_json(target, data)


def _add_codex_entry(data: dict, event: str, command: str) -> None:
    entries = data.setdefault(event, [])
    for entry in entries:
        if str(entry.get("command", "")) == command:
            return
    entries.append({"type": "command", "command": command, "timeout": 30})


def locate_mempalace_hooks(*, repo_root: Path) -> tuple[Path, Path]:
    """Find MemPalace's shipped hook scripts under repo_root.

    Looks for `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh`
    relative to repo_root. Designed for when the user has cloned the MemPalace
    repo locally; supplied via --mempalace-repo on the CLI in production.
    """
    repo_root = Path(repo_root)
    save = repo_root / "hooks" / "mempal_save_hook.sh"
    precompact = repo_root / "hooks" / "mempal_precompact_hook.sh"
    if not save.exists() or not precompact.exists():
        raise FileNotFoundError(
            f"MemPalace hooks not found under {repo_root}/hooks. "
            f"Pass --mempalace-repo to nexus memory init."
        )
    return save, precompact
