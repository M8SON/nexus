"""Wing-rename utilities.

When a workspace path changes (for example, you move ``~/linux/`` to
``~/projects/``), every wing's name shifts because nexus derives wings
from the absolute path. This module rewrites the ``wing`` metadata field
on existing drawers so prior memories keep working under the new path.
"""
from __future__ import annotations


def _is_unsanitizable_wing_error(error: str) -> bool:
    """True when the read side rejected the wing NAME rather than failing."""
    return "invalid characters" in str(error)


def _scan_drawer_ids(wing: str) -> list[str]:
    """Read drawer ids for `wing` straight from the backend, read-only.

    `tool_list_drawers` sanitizes its wing argument, so a wing whose name
    `sanitize_name` rejects cannot be enumerated through it. This bypasses the
    tool layer for the READ only — nothing here mutates the palace.
    """
    from mempalace.config import MempalaceConfig
    from mempalace.palace import get_collection

    collection = get_collection(MempalaceConfig().palace_path, read_only=True)
    return list(collection.get(where={"wing": wing}, include=[]).get("ids", []))


def _rename_unsanitizable_wing(old: str, new: str, tool_update_drawer) -> dict:
    """Move drawers out of a wing whose name the read tools refuse to accept.

    Writes still go through `tool_update_drawer` so indexes and metadata stay
    consistent; only the enumeration is done directly. `new` must be a valid
    name — `tool_update_drawer` sanitizes it, which is what makes this a
    one-way repair out of the broken namespace.
    """
    moved = 0
    for drawer_id in _scan_drawer_ids(old):
        update = tool_update_drawer(drawer_id=drawer_id, wing=new)
        if not update.get("success"):
            raise RuntimeError(
                f"tool_update_drawer failed for {drawer_id}: "
                f"{update.get('error', 'unknown')}"
            )
        moved += 1
    return {"moved": moved, "from": old, "to": new, "via": "direct-scan"}


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
            if _is_unsanitizable_wing_error(result["error"]):
                return _rename_unsanitizable_wing(old, new, tool_update_drawer)
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
