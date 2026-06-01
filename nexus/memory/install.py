"""Install MemPalace + nexus hooks into Claude Code and Codex CLI configs."""
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from nexus.memory.wings import resolve_wing

log = logging.getLogger(__name__)


def _resolve_mempalace_mcp_bin() -> str:
    """Locate the mempalace-mcp server binary.

    Prefer the binary co-located with the current interpreter (the venv that
    has nexus installed also has mempalace-mcp), fall back to bare PATH lookup.
    """
    venv_bin = Path(sys.executable).parent / "mempalace-mcp"
    if venv_bin.is_file() and os.access(venv_bin, os.X_OK):
        return str(venv_bin)
    return "mempalace-mcp"


def register_claude_mcp_server(
    *,
    mempalace_mcp_bin: str | None = None,
    name: str = "mempalace",
    scope: str = "user",
) -> dict:
    """Register the MemPalace MCP server with Claude Code.

    Without this, agents only get MemPalace via Stop/PreCompact/UserPromptSubmit
    hooks (auto-save + wake-up context), and have no in-session way to call
    `mempalace_search` or related tools — the proactive-recall side of the
    `continuity.md` policy is dead-on-arrival.

    Idempotent: removes any prior registration with this name before adding,
    so a re-run with a different binary path picks up the new one cleanly.
    User scope is the default because MemPalace currently does NOT honor
    `MEMPALACE_DEFAULT_WING`, so per-repo `.mcp.json` files (the original
    spec design) wouldn't auto-scope wings anyway — agents pass `wing=`
    per call regardless. Revisit if upstream MemPalace adds env-var
    wing defaulting.

    Falls back gracefully if the `claude` CLI isn't on PATH — the hooks-only
    flow still produces a working setup; only proactive in-session recall
    is degraded.
    """
    if not shutil.which("claude"):
        return {"registered": False, "reason": "claude CLI not on PATH"}

    bin_path = mempalace_mcp_bin or _resolve_mempalace_mcp_bin()

    # Idempotent: ignore exit code from remove (it's expected to fail
    # when no prior registration exists).
    subprocess.run(
        ["claude", "mcp", "remove", name, "--scope", scope],
        capture_output=True,
        timeout=15,
    )
    try:
        subprocess.run(
            ["claude", "mcp", "add", "--scope", scope, name, bin_path],
            capture_output=True,
            timeout=15,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="replace")[:200]
        return {"registered": False, "reason": f"claude mcp add failed: {stderr}"}
    except subprocess.TimeoutExpired:
        return {"registered": False, "reason": "claude mcp add timed out"}
    except FileNotFoundError:
        return {"registered": False, "reason": "claude CLI not on PATH"}

    return {"registered": True, "reason": None, "bin_path": bin_path, "name": name, "scope": scope}


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


def init(
    *,
    repo: Path,
    mempalace_repo: Path,
    nexus_root: Path,
    user_prompt_hook: Path,
    skip_backfill: bool = False,
) -> dict:
    """Top-level install: data dirs, claude/codex hook merges, optional backfill."""
    repo = Path(repo).resolve()
    nexus_root = Path(nexus_root)
    wing = resolve_wing(repo)
    if wing is None:
        raise ValueError(f"{repo} is not under workspace")

    save, precompact = locate_mempalace_hooks(repo_root=mempalace_repo)

    home = Path(os.path.expanduser("~"))
    claude_settings = home / ".claude" / "settings.json"
    claude_settings.parent.mkdir(parents=True, exist_ok=True)
    if not claude_settings.exists():
        claude_settings.write_text("{}", encoding="utf-8")
    merge_claude_hooks(
        settings_path=claude_settings,
        save_hook=str(save),
        precompact_hook=str(precompact),
        user_prompt_hook=str(user_prompt_hook),
    )

    codex_hooks = home / ".codex" / "hooks.json"
    write_codex_hooks(
        target=codex_hooks,
        save_hook=str(save),
        precompact_hook=str(precompact),
    )

    # Hooks alone wire automatic save / wake-up context, but the proactive
    # in-session recall side of continuity.md needs the MCP tool surface
    # (mempalace_search, mempalace_status, etc.) — register the MCP server
    # with Claude Code at user scope. Failures here don't break the broader
    # install; the hooks-only flow still works.
    mcp_registration = register_claude_mcp_server()
    if not mcp_registration.get("registered"):
        log.warning(
            "MemPalace MCP server not registered with Claude Code: %s. "
            "Proactive in-session recall will be unavailable; auto-save still works.",
            mcp_registration.get("reason"),
        )

    backfill_done = False
    marker = nexus_root / "data" / "backfill_markers" / f"{wing}.done"
    if not skip_backfill and not marker.exists():
        marker.parent.mkdir(parents=True, exist_ok=True)
        backfill_done = _run_backfill(wing=wing, marker=marker)

    return {
        "wing": wing,
        "claude_settings": str(claude_settings),
        "codex_hooks": str(codex_hooks),
        "claude_mcp_registered": mcp_registration.get("registered", False),
        "claude_mcp_reason": mcp_registration.get("reason"),
        "backfill_done": backfill_done,
    }


def _run_backfill(wing: str, marker: Path) -> bool:
    """One-time mine of past Claude transcripts that map to this wing.

    Earlier versions mined the entire `~/.claude/projects/` tree into a
    single wing, which dumped every project's history into whatever wing
    happened to be initialized first. Now we only mine the Claude project
    subdir whose name maps to this wing, keeping wings cleanly per-project.

    Codex sessions are not date-ish per-project, so we skip them here and
    let mempalace's auto-mine hooks pick up new content during sessions.
    """
    def _resolve_mempalace_bin() -> str:
        venv_bin = Path(sys.executable).parent / "mempalace"
        if venv_bin.is_file() and os.access(venv_bin, os.X_OK):
            return str(venv_bin)
        return "mempalace"

    home = Path(os.path.expanduser("~"))
    claude_projects = home / ".claude" / "projects"
    if not claude_projects.is_dir():
        marker.write_text("done\n", encoding="utf-8")
        return True

    matching_subdir = _find_claude_project_dir(claude_projects, wing)
    if matching_subdir is None:
        # No Claude project history for this wing yet. Mark the wing
        # backfilled so we don't retry; ongoing sessions populate via the
        # mempalace auto-mine hooks.
        marker.write_text("done\n", encoding="utf-8")
        return True

    try:
        subprocess.run(
            [
                _resolve_mempalace_bin(),
                "mine", str(matching_subdir),
                "--mode", "convos",
                "--wing", wing,
            ],
            check=True,
            timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log.warning("mempalace mine failed for %s: %s", matching_subdir, exc)
        return False
    except FileNotFoundError:
        log.warning("mempalace binary not found; skipping backfill")
        return False
    except OSError as exc:
        log.warning("OS error mining %s: %s", matching_subdir, exc)
        return False

    marker.write_text("done\n", encoding="utf-8")
    return True


def _find_claude_project_dir(projects_root: Path, wing: str) -> Path | None:
    """Return the Claude project subdir whose normalized name matches ``wing``.

    Claude Code names project dirs by encoding the source path with ``-``
    separators, e.g. ``-home-user-linux-nexus``. After mempalace's
    `normalize_wing_name` (lower + dash/space → underscore), that becomes
    ``_home_user_linux_nexus`` — which is the wing name nexus also uses.
    """
    if not projects_root.is_dir():
        return None
    for entry in projects_root.iterdir():
        if not entry.is_dir():
            continue
        normalized = entry.name.lower().replace(" ", "_").replace("-", "_")
        if normalized == wing:
            return entry
    return None
