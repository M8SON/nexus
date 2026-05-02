"""Tests for MemPalace env-var assembly."""
from pathlib import Path

from nexus.memory.env import mempalace_env


def test_env_contains_palace_path_state_dir_repo_dir(tmp_path):
    repo = tmp_path / "linux" / "nexus"
    repo.mkdir(parents=True)
    env = mempalace_env(wing="nexus", repo_root=repo, nexus_root=tmp_path / "nexus_root")

    assert env["MEMPALACE_PALACE_PATH"] == str(tmp_path / "nexus_root" / "data" / "palace")
    assert env["STATE_DIR"] == str(tmp_path / "nexus_root" / "data" / "hook_state")
    assert env["MEMPAL_DIR"] == str(repo)


def test_env_returns_strings_only():
    env = mempalace_env(wing="nexus", repo_root=Path("/tmp"), nexus_root=Path("/tmp/f"))
    assert all(isinstance(v, str) for v in env.values())
