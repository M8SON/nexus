# Nexus Policies

Shared agent-agnostic policies that any nexus-aware assistant should follow when working inside the configured workspace. These are a **core feature** of nexus — adapters point at them rather than inlining their own rules.

- `core.md` — the Karpathy-derived behavioral baseline (think before coding, simplicity, surgical changes, goal-driven execution). Sourced from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (MIT).
- `continuity.md` — recall and local-doc usage rules so context carries across sessions.

Adapter files in `nexus/adapters/<agent>/` should point at these policies, not duplicate them.
