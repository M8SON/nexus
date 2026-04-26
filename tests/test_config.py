from pathlib import Path
import tomllib


def test_project_files_exist():
    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"

    assert pyproject.exists()
    assert (root / "forge" / "__init__.py").exists()
    assert (root / "README.md").exists()

    data = tomllib.loads(pyproject.read_text())
    assert data["project"]["name"] == "forge"
    assert data["project"]["readme"] == "README.md"
    assert "scripts" not in data["project"]
