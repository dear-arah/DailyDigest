import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def sh(script, *args):
    return subprocess.run(["sh", str(SCRIPTS / script), *args], capture_output=True, text=True, env=ENV)


def git_remote(remote, *args):
    return subprocess.run(
        ["git", f"--git-dir={remote.path}", *args], capture_output=True, text=True, env=ENV
    )


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(path)], check=True, env=ENV)
    return SimpleNamespace(path=path, url=path.as_uri())


def load_and_save(tmp_path, remote, name, content):
    state = tmp_path / name
    assert sh("load-state.sh", remote.url, str(state)).returncode == 0
    (state / "news.json").write_text(content)
    result = sh("save-state.sh", remote.url, str(state))
    assert result.returncode == 0, result.stderr
    return state


def test_load_starts_fresh_state_when_branch_missing(tmp_path, remote):
    result = sh("load-state.sh", remote.url, str(tmp_path / "state"))

    assert result.returncode == 0
    assert (tmp_path / "state" / ".git").exists()


def test_load_aborts_when_remote_unreachable(tmp_path):
    result = sh("load-state.sh", (tmp_path / "missing.git").as_uri(), str(tmp_path / "state"))

    assert result.returncode != 0
    assert "cannot read state branch" in result.stderr
    assert not (tmp_path / "state").exists()


def test_load_clones_existing_state_branch(tmp_path, remote):
    load_and_save(tmp_path, remote, "first", '{"records": {}}')

    assert sh("load-state.sh", remote.url, str(tmp_path / "second")).returncode == 0

    assert (tmp_path / "second" / "news.json").read_text() == '{"records": {}}'


def test_save_publishes_a_single_commit_and_keeps_it_single(tmp_path, remote):
    state = load_and_save(tmp_path, remote, "first", "one")
    assert git_remote(remote, "rev-list", "--count", "state").stdout.strip() == "1"
    assert git_remote(remote, "log", "-1", "--format=%an", "state").stdout.strip() == "github-actions[bot]"

    again = tmp_path / "again"
    assert sh("load-state.sh", remote.url, str(again)).returncode == 0
    (again / "news.json").write_text("two")
    assert sh("save-state.sh", remote.url, str(again)).returncode == 0

    assert git_remote(remote, "rev-list", "--count", "state").stdout.strip() == "1"
    assert git_remote(remote, "show", "state:news.json").stdout == "two"


def test_save_does_nothing_when_unchanged(tmp_path, remote):
    load_and_save(tmp_path, remote, "first", "one")
    before = git_remote(remote, "rev-parse", "state").stdout

    again = tmp_path / "again"
    assert sh("load-state.sh", remote.url, str(again)).returncode == 0
    assert sh("save-state.sh", remote.url, str(again)).returncode == 0

    assert git_remote(remote, "rev-parse", "state").stdout == before


def test_save_does_nothing_for_empty_fresh_state(tmp_path, remote):
    state = tmp_path / "fresh"
    assert sh("load-state.sh", remote.url, str(state)).returncode == 0

    assert sh("save-state.sh", remote.url, str(state)).returncode == 0

    assert git_remote(remote, "rev-parse", "--verify", "state").returncode != 0
