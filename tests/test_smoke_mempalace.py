"""End-to-end smoke test against a real MemPalace install. Slow; opt-in."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("mempalace") is None,
    reason="mempalace CLI not on PATH",
)


def test_wake_up_returns_text_after_mining_a_fixture(tmp_path):
    palace = tmp_path / "palace"
    state = tmp_path / "state"
    palace.mkdir()
    state.mkdir()

    fixture = tmp_path / "fixture.jsonl"
    fixture.write_text(
        '{"type":"user","sessionId":"s1","cwd":"/x","gitBranch":"main",'
        '"timestamp":"2026-04-30T00:00:00Z","uuid":"u1","parentUuid":null,'
        '"message":{"role":"user","content":"the wake offload is on the hailo"}}'
        "\n", encoding="utf-8",
    )

    env = {**os.environ,
           "MEMPALACE_PALACE_PATH": str(palace),
           "STATE_DIR": str(state)}

    subprocess.run(
        ["mempalace", "mine", str(tmp_path), "--mode", "convos", "--wing", "smoke"],
        env=env, check=True, timeout=120,
    )

    proc = subprocess.run(
        ["mempalace", "wake-up", "--wing", "smoke"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert "wake offload" in proc.stdout.lower() or proc.stdout.strip()
