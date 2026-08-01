"""Tests for the git-based update checker (gui/update_check.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gui.update_check import check_for_updates, pull_update

_ENV_AUTHOR = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *_ENV_AUTHOR, *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


def _commit(repo: Path, filename: str, message: str) -> str:
    (repo / filename).write_text(message, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def repo_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Set up a bare "remote", a working push clone, and a checkout under test."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    repo_root = tmp_path / "checkout"

    _git(tmp_path, "init", "--bare", "-b", "main", str(remote))

    work.mkdir()
    _git(work, "init", "-b", "main")
    _commit(work, "README.md", "initial commit")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-u", "origin", "main")

    _git(tmp_path, "clone", str(remote), str(repo_root))
    _git(repo_root, "config", "user.name", "Test")
    _git(repo_root, "config", "user.email", "test@example.com")

    return work, repo_root


def test_reports_up_to_date_when_no_new_commits(repo_pair):
    _work, repo_root = repo_pair
    status = check_for_updates(repo_root)

    assert status.error is None
    assert status.behind == 0
    assert status.available is False
    assert status.commits == []


def test_reports_behind_with_commit_subjects(repo_pair):
    work, repo_root = repo_pair
    _commit(work, "feature.txt", "Add feature A")
    _commit(work, "feature2.txt", "Add feature B")
    _git(work, "push", "origin", "main")

    status = check_for_updates(repo_root)

    assert status.error is None
    assert status.behind == 2
    assert status.ahead == 0
    assert status.available is True
    assert status.commits == ["Add feature B", "Add feature A"]
    assert status.can_pull is True


def test_dirty_tree_blocks_pull_but_not_detection(repo_pair):
    work, repo_root = repo_pair
    _commit(work, "feature.txt", "Add feature A")
    _git(work, "push", "origin", "main")

    (repo_root / "local_edit.txt").write_text("uncommitted", encoding="utf-8")

    status = check_for_updates(repo_root)

    assert status.available is True
    assert status.dirty is True
    assert status.can_pull is False


def test_local_commits_ahead_block_pull(repo_pair):
    work, repo_root = repo_pair
    _commit(work, "feature.txt", "Add feature A")
    _git(work, "push", "origin", "main")
    _commit(repo_root, "local_only.txt", "local commit")

    status = check_for_updates(repo_root)

    assert status.behind == 1
    assert status.ahead == 1
    assert status.available is True
    assert status.can_pull is False


def test_not_a_git_repo_returns_error(tmp_path):
    plain_dir = tmp_path / "not_a_repo"
    plain_dir.mkdir()

    status = check_for_updates(plain_dir)

    assert status.error is not None
    assert status.available is False


def test_pull_update_fast_forwards_cleanly(repo_pair):
    work, repo_root = repo_pair
    new_sha = _commit(work, "feature.txt", "Add feature A")
    _git(work, "push", "origin", "main")

    result = pull_update(repo_root)

    assert result.ok is True
    assert result.new_sha == new_sha
    status_after = check_for_updates(repo_root)
    assert status_after.available is False


def test_pull_update_refuses_when_dirty(repo_pair):
    work, repo_root = repo_pair
    _commit(work, "feature.txt", "Add feature A")
    _git(work, "push", "origin", "main")
    (repo_root / "local_edit.txt").write_text("uncommitted", encoding="utf-8")

    result = pull_update(repo_root)

    assert result.ok is False
    assert "changes" in result.message.lower()


def test_pull_update_refuses_when_ahead(repo_pair):
    work, repo_root = repo_pair
    _commit(work, "feature.txt", "Add feature A")
    _git(work, "push", "origin", "main")
    _commit(repo_root, "local_only.txt", "local commit")

    result = pull_update(repo_root)

    assert result.ok is False
    assert "ahead" in result.message.lower()


def test_pull_update_is_noop_when_already_up_to_date(repo_pair):
    _work, repo_root = repo_pair

    result = pull_update(repo_root)

    assert result.ok is True
    assert "up to date" in result.message.lower()
