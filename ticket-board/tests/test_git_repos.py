"""Tests build throwaway git repos (a bare "origin" plus a local clone) under tmp_path.
No network, and nothing depends on the machine's global git config."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config import RepoConfig
from integrations.git_repos import RepoSnapshot, default_ref, describe, fetch_and_snapshot

GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "init.defaultBranch=trunk",
       "-c", "commit.gpgsign=false"]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run([*GIT, *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(repo: Path, name: str, body: str = "x") -> str:
    (repo / name).write_text(body)
    git(repo, "add", name)
    git(repo, "commit", "-m", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def world(tmp_path):
    """origin.git (default branch trunk), work (pushes to origin), local (clone of origin)."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "trunk", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "init", "-b", "trunk", str(work))
    commit(work, "a.txt")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "origin", "trunk")
    local = tmp_path / "local"
    git(tmp_path, "clone", str(origin), str(local))
    return origin, work, local


def test_snapshot_reports_remote_main_not_stale_local(world):
    origin, work, local = world
    stale = git(local, "rev-parse", "HEAD")
    new = commit(work, "b.txt")
    git(work, "push", "origin", "trunk")
    snap = fetch_and_snapshot(RepoConfig(local))
    assert snap.error is None
    assert snap.ref == "origin/trunk"
    assert snap.sha == new != stale
    assert isinstance(snap.committed_at, datetime)


def test_fetch_does_not_touch_checked_out_branch_or_dirty_files(world):
    origin, work, local = world
    git(local, "checkout", "-b", "my-feature")
    (local / "a.txt").write_text("dirty edit")
    (local / "untracked.txt").write_text("u")
    commit(work, "b.txt")
    git(work, "push", "origin", "trunk")

    def state():
        return (git(local, "rev-parse", "HEAD"), git(local, "branch", "--show-current"),
                git(local, "status", "--porcelain"), (local / "a.txt").read_text())

    before = state()
    snap = fetch_and_snapshot(RepoConfig(local))
    assert snap.error is None
    assert state() == before
    assert before[1] == "my-feature"


def test_default_branch_from_origin_head_not_assumed_main(world):
    _, _, local = world
    assert default_ref(RepoConfig(local)) == "origin/trunk"


def test_default_ref_falls_back_to_ls_remote_when_origin_head_unset(world):
    _, _, local = world
    git(local, "remote", "set-head", "origin", "-d")  # test setup only
    assert default_ref(RepoConfig(local)) == "origin/trunk"
    assert fetch_and_snapshot(RepoConfig(local)).ref == "origin/trunk"


def test_override_wins(world):
    origin, work, local = world
    git(work, "checkout", "-b", "release")
    sha = commit(work, "r.txt")
    git(work, "push", "origin", "release")
    repo = RepoConfig(local, default_branch_override="release")
    assert default_ref(repo) == "origin/release"
    snap = fetch_and_snapshot(repo)
    assert (snap.ref, snap.sha) == ("origin/release", sha)


def test_fetch_failure_returns_not_searched(world, tmp_path):
    _, _, local = world
    git(local, "remote", "set-url", "origin", str(tmp_path / "does-not-exist.git"))
    snap = fetch_and_snapshot(RepoConfig(local))
    assert snap.ref is None and snap.sha is None and snap.committed_at is None
    assert snap.error.startswith("not searched: ")
    assert str(tmp_path) not in snap.error  # no URLs/paths leaked from stderr


def test_missing_path_returns_not_searched(tmp_path):
    snap = fetch_and_snapshot(RepoConfig(tmp_path / "nope"))
    assert snap.ref is None and snap.error.startswith("not searched: ")


def test_not_a_git_repo_returns_not_searched(tmp_path):
    snap = fetch_and_snapshot(RepoConfig(tmp_path))
    assert snap.ref is None and snap.error.startswith("not searched: ")


def test_fetch_does_not_prune(world):
    origin, work, local = world
    git(work, "push", "origin", "trunk:feature")
    git(local, "fetch", "origin")
    assert git(local, "rev-parse", "--verify", "refs/remotes/origin/feature")
    git(origin, "branch", "-D", "feature")  # deleted upstream
    snap = fetch_and_snapshot(RepoConfig(local))
    assert snap.error is None
    assert git(local, "rev-parse", "--verify", "refs/remotes/origin/feature")


def test_describe_formats_date_without_zero_padding():
    snap = RepoSnapshot(Path("/x/virtual-assistant-agent"), "origin/main", "abc",
                        datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc), None)
    assert describe(snap) == "virtual-assistant-agent @ origin/main, 3 Nov"


def test_describe_error_snapshot():
    snap = RepoSnapshot(Path("/x/virtual-assistant-agent"), None, None, None,
                        "not searched: git fetch failed")
    assert describe(snap) == "virtual-assistant-agent: not searched: git fetch failed"


def test_d6_repo_config_prune_true_still_does_not_prune(world):
    origin, work, local = world
    git(local, "config", "fetch.prune", "true")      # Yan's repo config asks for pruning
    git(local, "config", "fetch.pruneTags", "true")
    git(work, "push", "origin", "trunk:stale-branch")
    git(local, "fetch", "--no-prune", "origin")
    assert git(local, "rev-parse", "--verify", "refs/remotes/origin/stale-branch")
    git(origin, "branch", "-D", "stale-branch")       # deleted upstream
    snap = fetch_and_snapshot(RepoConfig(local))
    assert snap.error is None
    assert git(local, "rev-parse", "--verify", "refs/remotes/origin/stale-branch")


def test_d6_git_env_disables_prompts(monkeypatch, world):
    import integrations.git_repos as gr
    seen = {}
    real = gr.subprocess.run

    def spy(args, **kw):
        seen.setdefault("calls", []).append((args, kw.get("env")))
        return real(args, **kw)

    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    monkeypatch.setattr(gr.subprocess, "run", spy)
    fetch_and_snapshot(RepoConfig(world[2]))
    fetch_args, env = next((a, e) for a, e in seen["calls"] if "fetch" in a)
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_SSH_COMMAND"] == "ssh -o BatchMode=yes"
    i = fetch_args.index("fetch")
    assert fetch_args[i:] == ["fetch", "origin"]
    for c in ("fetch.prune=false", "fetch.pruneTags=false", "gc.auto=0", "maintenance.auto=false"):
        assert c in fetch_args[:i]


def test_d6_user_ssh_command_is_kept(monkeypatch, world):
    import integrations.git_repos as gr
    envs = []
    real = gr.subprocess.run
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -i /k")
    monkeypatch.setattr(gr.subprocess, "run", lambda a, **kw: (envs.append(kw["env"]), real(a, **kw))[1])
    fetch_and_snapshot(RepoConfig(world[2]))
    assert envs and all(e["GIT_SSH_COMMAND"] == "ssh -i /k" for e in envs)
