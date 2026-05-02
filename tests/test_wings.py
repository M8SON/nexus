"""Tests for cwd → wing-name resolution."""
from pathlib import Path

import pytest

from nexus.memory.wings import resolve_wing


@pytest.mark.parametrize("cwd, expected", [
    ("/home/daedalus/linux/nexus", "nexus"),
    ("/home/daedalus/linux/nexus/nexus/memory", "nexus"),
    ("/home/daedalus/linux/miniclaw", "miniclaw"),
    ("/home/daedalus/linux/miniclaw/skills/dashboard", "miniclaw"),
])
def test_managed_repo_yields_repo_name(cwd, expected):
    assert resolve_wing(Path(cwd)) == expected
