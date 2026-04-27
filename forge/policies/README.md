# Forge Policies

Shared agent-agnostic policies that any forge-aware assistant should follow when working under `/home/daedalus/linux`.

- `core.md` — baseline working principles for any task.
- `continuity.md` — recall and local-doc usage rules so context carries across sessions.

Adapter files in `forge/adapters/<agent>/` should point at these policies, not duplicate them.
