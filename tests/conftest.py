import pytest


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Run every test in an empty directory so a real .env in the project root is never loaded."""
    monkeypatch.chdir(tmp_path)
