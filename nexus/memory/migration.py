"""Wing-rename utilities.

When a workspace path changes (for example, you move ``~/linux/`` to
``~/projects/``), every wing's name shifts because nexus derives wings
from the absolute path. This module rewrites the ``wing`` metadata field
on existing drawers so prior memories keep working under the new path.
"""
from __future__ import annotations


def rename_wing(old: str, new: str, *, batch_size: int = 100) -> dict:
    """Rewrite every drawer in wing ``old`` to wing ``new``.

    Walks ``tool_list_drawers(wing=old)`` in batches, calling
    ``tool_update_drawer`` per drawer to mutate the wing field. Drawers
    leave the old wing as they're updated, so polling with
    ``offset=0`` until the page is empty drains it correctly.

    Returns ``{"moved": N, "from": old, "to": new}``.
    Raises ``RuntimeError`` if mempalace is not importable.
    """
    if not old or not new:
        raise ValueError("rename_wing requires non-empty old and new wing names")
    if old == new:
        return {"moved": 0, "from": old, "to": new, "noop": True}

    try:
        from mempalace.mcp_server import tool_list_drawers, tool_update_drawer
    except ImportError as exc:
        raise RuntimeError(
            "mempalace is not installed in this Python environment"
        ) from exc

    moved = 0
    while True:
        result = tool_list_drawers(wing=old, limit=batch_size, offset=0)
        if "error" in result:
            raise RuntimeError(f"tool_list_drawers failed: {result['error']}")
        drawers = result.get("drawers", [])
        if not drawers:
            break
        for drawer in drawers:
            update = tool_update_drawer(drawer_id=drawer["drawer_id"], wing=new)
            if not update.get("success"):
                raise RuntimeError(
                    f"tool_update_drawer failed for {drawer['drawer_id']}: "
                    f"{update.get('error', 'unknown')}"
                )
            moved += 1

    return {"moved": moved, "from": old, "to": new}
