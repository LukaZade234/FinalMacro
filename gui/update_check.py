"""Git-based update checking: fetch, compare to the remote, pull when safe.

Uses ``git`` directly rather than the GitHub API. The repo remote is SSH, so
this reuses whatever auth already lets the user clone/pull — no token or API
rate limit to manage, and it works the same for a private repo.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

_FETCH_TIMEOUT_SEC = 15.0
_PULL_TIMEOUT_SEC = 30.0
_GIT_TIMEOUT_SEC = 5.0
# Commit subjects shown in the banner before it collapses to "+N more".
MAX_COMMIT_SUMMARY = 12


@dataclass
class UpdateStatus:
    checked_at: float = field(default_factory=time.time)
    error: str | None = None
    branch: str | None = None
    current_sha: str | None = None
    remote_sha: str | None = None
    behind: int = 0
    ahead: int = 0
    dirty: bool = False
    commits: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return (
            self.error is None
            and self.behind > 0
            and self.current_sha != self.remote_sha
        )

    @property
    def can_pull(self) -> bool:
        """Safe to fast-forward: no local commits or edits in the way."""
        return self.available and not self.dirty and self.ahead == 0

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "error": self.error,
            "branch": self.branch,
            "current_sha": self.current_sha,
            "remote_sha": self.remote_sha,
            "behind": self.behind,
            "ahead": self.ahead,
            "dirty": self.dirty,
            "commits": self.commits,
            "available": self.available,
            "can_pull": self.can_pull,
        }


@dataclass
class PullResult:
    ok: bool
    message: str
    new_sha: str | None = None


def _run(
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def is_git_repo(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _current_branch(repo_root: Path) -> str | None:
    result = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        timeout=_GIT_TIMEOUT_SEC,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None


def _rev_parse(repo_root: Path, ref: str) -> str | None:
    result = _run(["git", "rev-parse", ref], cwd=repo_root, timeout=_GIT_TIMEOUT_SEC)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _is_dirty(repo_root: Path) -> bool:
    result = _run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        timeout=_GIT_TIMEOUT_SEC,
    )
    return bool(result.stdout.strip())


def check_for_updates(repo_root: Path, *, branch: str | None = None) -> UpdateStatus:
    """Fetch the remote and compare it to the checked-out branch.

    Never raises: network failures, a missing ``git`` binary, or running
    outside a repo all come back as ``UpdateStatus(error=...)`` so the caller
    can show "can't check" instead of crashing a background thread.
    """
    if not is_git_repo(repo_root):
        return UpdateStatus(error="Not a git checkout")

    active_branch = branch or _current_branch(repo_root)
    if not active_branch:
        return UpdateStatus(error="Not on a branch (detached HEAD)")

    try:
        fetch = _run(
            ["git", "fetch", "--quiet", "origin", active_branch],
            cwd=repo_root,
            timeout=_FETCH_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return UpdateStatus(error=f"Could not reach the remote ({exc})")
    if fetch.returncode != 0:
        detail = fetch.stderr.strip() or "git fetch failed"
        return UpdateStatus(error=detail, branch=active_branch)

    remote_ref = f"origin/{active_branch}"
    current_sha = _rev_parse(repo_root, "HEAD")
    remote_sha = _rev_parse(repo_root, remote_ref)
    if not current_sha or not remote_sha:
        return UpdateStatus(error="Could not resolve local/remote commit", branch=active_branch)

    counts = _run(
        ["git", "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"],
        cwd=repo_root,
        timeout=_GIT_TIMEOUT_SEC,
    )
    ahead, behind = 0, 0
    if counts.returncode == 0:
        parts = counts.stdout.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])

    commits: list[str] = []
    if behind > 0:
        log = _run(
            ["git", "log", f"HEAD..{remote_ref}", "--pretty=%s"],
            cwd=repo_root,
            timeout=_GIT_TIMEOUT_SEC,
        )
        if log.returncode == 0:
            commits = [line for line in log.stdout.splitlines() if line.strip()]

    return UpdateStatus(
        branch=active_branch,
        current_sha=current_sha,
        remote_sha=remote_sha,
        behind=behind,
        ahead=ahead,
        dirty=_is_dirty(repo_root),
        commits=commits,
    )


def pull_update(repo_root: Path, *, branch: str | None = None) -> PullResult:
    """Fast-forward onto the remote. Refuses anything that isn't a clean fast-forward."""
    status = check_for_updates(repo_root, branch=branch)
    if status.error:
        return PullResult(ok=False, message=status.error)
    if status.dirty:
        return PullResult(ok=False, message="Local changes present — commit or discard them first")
    if status.ahead > 0:
        return PullResult(ok=False, message="Local commits ahead of the remote — pull manually")
    if not status.available:
        return PullResult(ok=True, message="Already up to date", new_sha=status.current_sha)

    try:
        result = _run(
            ["git", "pull", "--ff-only", "origin", status.branch or "main"],
            cwd=repo_root,
            timeout=_PULL_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return PullResult(ok=False, message=f"Pull failed ({exc})")
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git pull failed"
        return PullResult(ok=False, message=detail)

    new_sha = _rev_parse(repo_root, "HEAD")
    return PullResult(ok=True, message="Updated — restart FinalMacro to apply", new_sha=new_sha)
