"""Tests for nexus.memory.migration."""
import pytest

from nexus.memory.migration import rename_wing


def test_rename_wing_rejects_empty_args():
    with pytest.raises(ValueError):
        rename_wing("", "new")
    with pytest.raises(ValueError):
        rename_wing("old", "")


def test_rename_wing_noop_when_old_equals_new():
    result = rename_wing("same", "same")
    assert result == {"moved": 0, "from": "same", "to": "same", "noop": True}


def test_rename_wing_iterates_until_drained(monkeypatch):
    """list_drawers is polled at offset=0 because each update removes drawers
    from the source wing, so the next page is just a fresh offset=0 read."""
    pages = [
        {"drawers": [{"drawer_id": "d1"}, {"drawer_id": "d2"}]},
        {"drawers": [{"drawer_id": "d3"}]},
        {"drawers": []},
    ]
    list_calls = []
    update_calls = []

    def fake_list(wing, limit, offset):
        list_calls.append((wing, limit, offset))
        return pages.pop(0)

    def fake_update(drawer_id, wing):
        update_calls.append((drawer_id, wing))
        return {"success": True}

    import nexus.memory.migration as mod
    monkeypatch.setattr(mod, "rename_wing", rename_wing)  # ensure fresh
    fake_module = type("M", (), {
        "tool_list_drawers": fake_list,
        "tool_update_drawer": fake_update,
    })
    monkeypatch.setitem(__import__("sys").modules, "mempalace.mcp_server", fake_module)

    result = rename_wing("old_wing", "new_wing")

    assert result["moved"] == 3
    assert result["from"] == "old_wing"
    assert result["to"] == "new_wing"
    assert update_calls == [
        ("d1", "new_wing"),
        ("d2", "new_wing"),
        ("d3", "new_wing"),
    ]
    # All polls were at offset=0 — the source wing drains as updates run.
    assert {offset for _, _, offset in list_calls} == {0}


def test_rename_wing_raises_on_update_failure(monkeypatch):
    pages = [
        {"drawers": [{"drawer_id": "d1"}]},
        {"drawers": []},
    ]

    def fake_list(wing, limit, offset):
        return pages.pop(0)

    def fake_update(drawer_id, wing):
        return {"success": False, "error": "drawer locked"}

    fake_module = type("M", (), {
        "tool_list_drawers": fake_list,
        "tool_update_drawer": fake_update,
    })
    monkeypatch.setitem(__import__("sys").modules, "mempalace.mcp_server", fake_module)

    with pytest.raises(RuntimeError, match="drawer locked"):
        rename_wing("old", "new")


def test_rename_wing_raises_on_list_error(monkeypatch):
    def fake_list(wing, limit, offset):
        return {"error": "palace not found"}

    fake_module = type("M", (), {
        "tool_list_drawers": fake_list,
        "tool_update_drawer": lambda **kw: {"success": True},
    })
    monkeypatch.setitem(__import__("sys").modules, "mempalace.mcp_server", fake_module)

    with pytest.raises(RuntimeError, match="palace not found"):
        rename_wing("old", "new")
