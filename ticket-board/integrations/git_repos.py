"""Read-only git access for the configured repos.

Only these git commands are ever run: fetch (no --prune), symbolic-ref, rev-parse, log -1,
and ls-remote (read-only network call). Nothing here changes the checked-out branch, the
index or the working tree. The one write is fetch updating remote-tracking refs.

Any failure yields a snapshot with error="not searched: <reason>" so callers never
fall back silently to stale local files. Reasons are short and never include stderr,
so remote URLs or tokens cannot leak.
"""
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import FETCH_TIMEOUT_SECONDS, RepoConfig


class RepoError(Exception):
    """A repo cannot be searched. The message is the short, safe reason."""


@dataclass(frozen=True)
class RepoSnapshot:
    path: Path
    ref: str | None
    sha: str | None
    committed_at: datetime | None
    error: str | None


def _git(repo_path: Path, *args: str) -> str:
    # List args, no shell. GIT_TERMINAL_PROMPT=0 makes missing credentials fail fast.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run(["git", "-C", str(repo_path), *args], capture_output=True,
                              text=True, timeout=FETCH_TIMEOUT_SECONDS, env=env)
    except subprocess.TimeoutExpired:
        raise RepoError(f"git {args[0]} timed out after {FETCH_TIMEOUT_SECONDS}s") from None
    except OSError:
        raise RepoError("git could not be run") from None
    if proc.returncode != 0:
        raise RepoError(f"git {args[0]} failed (exit {proc.returncode})")
    return proc.stdout.strip()


def default_ref(repo: RepoConfig) -> str:
    """Return the remote default ref, e.g. "origin/main".

    Order: the configured override, then refs/remotes/origin/HEAD, then a read-only
    `git ls-remote --symref origin HEAD`. Raises RepoError if none is available.
    """
    if repo.default_branch_override:
        return f"origin/{repo.default_branch_override}"
    try:
        return _git(repo.path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    except RepoError:
        pass
    # origin/HEAD can be missing in clones; ask the remote without modifying the repo.
    out = _git(repo.path, "ls-remote", "--symref", "origin", "HEAD")
    for line in out.splitlines():
        if line.startswith("ref: refs/heads/"):
            return "origin/" + line.split("\t")[0].removeprefix("ref: refs/heads/")
    raise RepoError("no default branch (origin/HEAD unset and no override)")


def fetch_and_snapshot(repo: RepoConfig) -> RepoSnapshot:
    """Fetch origin (no prune) and report the remote default branch tip."""
    try:
        if not (repo.path / ".git").exists():
            raise RepoError("path missing or not a git repo")
        _git(repo.path, "fetch", "origin")
        ref = default_ref(repo)
        sha = _git(repo.path, "rev-parse", "--verify", f"{ref}^{{commit}}")
        committed = _git(repo.path, "log", "-1", "--format=%cI", sha)
        return RepoSnapshot(repo.path, ref, sha, datetime.fromisoformat(committed), None)
    except (RepoError, ValueError) as exc:
        return RepoSnapshot(repo.path, None, None, None, f"not searched: {exc}")


def describe(snapshot: RepoSnapshot) -> str:
    name = snapshot.path.name
    if snapshot.error or snapshot.committed_at is None:
        return f"{name}: {snapshot.error or 'not searched'}"
    d = snapshot.committed_at
    return f"{name} @ {snapshot.ref}, {d.day} {d.strftime('%b')}"
