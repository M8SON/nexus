"""Install MemPalace + nexus hooks into Claude Code and Codex CLI configs."""
import json
import shutil
from pathlib import Path


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
    backup = settings_path.with_suffix(settings_path.suffix + ".bak")
    if settings_path.exists():
        shutil.copyfile(settings_path, backup)

    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}

    hooks = data.setdefault("hooks", {})
    _ensure_hook(hooks, "Stop", save_hook, matcher="*")
    _ensure_hook(hooks, "PreCompact", precompact_hook, matcher=None)
    _ensure_hook(hooks, "UserPromptSubmit", user_prompt_hook, matcher=None)

    settings_path.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def _ensure_hook(
    hooks: dict, event: str, command: str, *, matcher: str | None
) -> None:
    """Append a hook entry only if no entry already has this command for this event."""
    entries = hooks.setdefault(event, [])
    for entry in entries:
        for h in entry.get("hooks", [entry]):
            if str(h.get("command", "")) == command:
                return
    entry: dict = {
        "hooks": [{"type": "command", "command": command, "timeout": 30}],
    }
    if matcher is not None:
        entry["matcher"] = matcher
    entries.append(entry)
