"""Tests for hook installation into Claude/Codex settings."""
import json
from pathlib import Path

from nexus.memory.install import merge_claude_hooks


HOOK_SCRIPT = "/abs/path/mempal_save_hook.sh"
PRECOMPACT_SCRIPT = "/abs/path/mempal_precompact_hook.sh"
USERPROMPT_SCRIPT = "/abs/path/nexus-user-prompt-submit.sh"


def test_merge_into_empty_settings_adds_three_hooks(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")

    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "Stop" in data["hooks"]
    assert "PreCompact" in data["hooks"]
    assert "UserPromptSubmit" in data["hooks"]


def test_merge_is_idempotent(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")

    for _ in range(2):
        merge_claude_hooks(
            settings_path=settings,
            save_hook=HOOK_SCRIPT,
            precompact_hook=PRECOMPACT_SCRIPT,
            user_prompt_hook=USERPROMPT_SCRIPT,
        )

    data = json.loads(settings.read_text(encoding="utf-8"))
    for event in ("Stop", "PreCompact", "UserPromptSubmit"):
        entries = data["hooks"][event]
        # Each event has at most one entry containing our command.
        matching = [e for e in entries if any(
            HOOK_SCRIPT in str(h.get("command", ""))
            or PRECOMPACT_SCRIPT in str(h.get("command", ""))
            or USERPROMPT_SCRIPT in str(h.get("command", ""))
            for h in (e.get("hooks") or [e])
        )]
        assert len(matching) == 1, f"{event} duplicated on second merge"


def test_merge_preserves_existing_unrelated_hook(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "hooks": {
            "SessionStart": [{
                "matcher": "startup",
                "hooks": [{"type": "command", "command": "/keep/me.sh"}],
            }]
        }
    }), encoding="utf-8")

    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "/keep/me.sh"


def test_merge_writes_backup_before_change(tmp_path):
    settings = tmp_path / "settings.json"
    original = '{"hooks": {}}'
    settings.write_text(original, encoding="utf-8")

    merge_claude_hooks(
        settings_path=settings,
        save_hook=HOOK_SCRIPT,
        precompact_hook=PRECOMPACT_SCRIPT,
        user_prompt_hook=USERPROMPT_SCRIPT,
    )

    backup = settings.with_suffix(settings.suffix + ".bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original
