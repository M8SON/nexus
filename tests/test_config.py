from pathlib import Path


def test_project_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "pyproject.toml").exists()
    assert (root / "forge" / "__init__.py").exists()
    assert (root / "README.md").exists()
