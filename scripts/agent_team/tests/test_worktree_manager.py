from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_team.config import load_config
from agent_team.tests.conftest import CONFIG_PATH
from agent_team.worktree_manager import (
    GitError,
    MergeConflict,
    WorktreeManager,
    branch_name,
    issue_from_branch,
    run_git,
    worktree_path,
)


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path):
    """A bare 'origin' plus a clone that plays the main checkout, with the real config copied in."""
    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-q", "--initial-branch=main", str(origin)], tmp_path)
    work = tmp_path / "repo"
    _git(["clone", "-q", str(origin), str(work)], tmp_path)
    _git(["config", "user.email", "t@example.com"], work)
    _git(["config", "user.name", "tester"], work)
    (work / ".agent").mkdir()
    shutil.copy(CONFIG_PATH, work / ".agent" / "config.yaml")
    (work / "README.md").write_text("hello\n")
    _git(["add", "."], work)
    _git(["commit", "-q", "-m", "init"], work)
    _git(["push", "-q", "-u", "origin", "main"], work)
    return load_config(repo_root=work)


def test_naming(repo):
    assert branch_name(repo, 12, "add-thing") == "agent/12-add-thing"
    assert worktree_path(repo, 12, "add-thing") == repo.repo_root / ".worktrees" / "12-add-thing"
    assert issue_from_branch(repo, "agent/12-add-thing") == 12
    assert issue_from_branch(repo, "feature/x") is None
    with pytest.raises(ValueError):
        branch_name(repo, 1, "../evil")


def test_ensure_creates_then_reconciles(repo):
    wm = WorktreeManager(repo)
    info = wm.ensure(5, "sample")
    assert info.created and not info.reconciled
    assert info.path.exists() and (info.path / "README.md").exists()
    assert info.branch == "agent/5-sample"
    # main checkout HEAD untouched
    assert run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo.repo_root).stdout.strip() == "main"
    # second call reuses, never duplicates
    again = wm.ensure(5, "sample")
    assert again.reconciled and not again.created and again.path == info.path
    assert len(wm.agent_worktrees()) == 1


def test_ensure_reconciles_orphan_branch_and_stale_directory(repo):
    wm = WorktreeManager(repo)
    info = wm.ensure(6, "orphan")
    (info.path / "work.txt").write_text("x")
    _git(["add", "."], info.path)
    _git(["commit", "-q", "-m", "work"], info.path)
    sha = wm.head_sha(info.path)
    # simulate a crash that lost the worktree registration but kept the branch
    run_git(["worktree", "remove", "--force", str(info.path)], repo.repo_root)
    again = wm.ensure(6, "orphan")
    assert again.reconciled and wm.head_sha(again.path) == sha
    # simulate a directory git does not know about
    run_git(["worktree", "remove", "--force", str(again.path)], repo.repo_root)
    again.path.mkdir(parents=True)
    (again.path / "junk").write_text("junk")
    third = wm.ensure(6, "orphan")
    assert third.reconciled and "moved to" in third.note
    assert (repo.repo_root / ".worktrees" / "_stale").exists()


def test_ensure_reconciles_remote_only_branch(repo):
    wm = WorktreeManager(repo)
    info = wm.ensure(7, "remote")
    (info.path / "r.txt").write_text("r")
    _git(["add", "."], info.path)
    _git(["commit", "-q", "-m", "remote work"], info.path)
    wm.push(info.path, info.branch)
    wm.remove(7, "remote", delete_branch=True)
    assert not wm.branch_exists("agent/7-remote")
    assert wm.branch_exists("agent/7-remote", remote=True)
    again = wm.ensure(7, "remote")
    assert again.reconciled and "remote branch" in again.note
    assert (again.path / "r.txt").exists()


def test_remove_and_validation_worktree(repo):
    wm = WorktreeManager(repo)
    info = wm.ensure(8, "rm")
    done = wm.remove(8, "rm", delete_branch=True)
    assert any("removed worktree" in d for d in done) and any("deleted local branch" in d for d in done)
    assert not info.path.exists()
    v = wm.validation_worktree("origin/main")
    assert v.exists() and (v / "README.md").exists()
    assert "_validation" in str(v)
    wm.remove_validation_worktree(v)
    assert not v.exists()


def test_change_tracking_and_base_update(repo):
    wm = WorktreeManager(repo)
    info = wm.ensure(9, "sync")
    (info.path / "feature.txt").write_text("f")
    _git(["add", "."], info.path)
    _git(["commit", "-q", "-m", "feature"], info.path)
    assert wm.commits_ahead(info.path) == 1
    assert wm.changed_files(info.path, wm.base_ref()) == ["feature.txt"]
    assert "feature.txt" in wm.diff(info.path, wm.base_ref())
    # main advances on the remote (someone else merged)
    other = repo.repo_root.parent / "other"
    _git(["clone", "-q", str(repo.repo_root.parent / "origin.git"), str(other)], repo.repo_root.parent)
    _git(["config", "user.email", "o@example.com"], other)
    _git(["config", "user.name", "other"], other)
    (other / "other.txt").write_text("o")
    _git(["add", "."], other)
    _git(["commit", "-q", "-m", "other"], other)
    _git(["push", "-q", "origin", "main"], other)
    wm.fetch()
    assert wm.behind_base(info.path) == 1
    wm.update_from_base(info.path)
    assert wm.behind_base(info.path) == 0 and (info.path / "other.txt").exists()


def test_merge_conflict_is_reported_and_aborted(repo):
    wm = WorktreeManager(repo)
    info = wm.ensure(10, "conflict")
    (info.path / "README.md").write_text("branch version\n")
    _git(["commit", "-q", "-am", "branch edit"], info.path)
    other = repo.repo_root.parent / "other2"
    _git(["clone", "-q", str(repo.repo_root.parent / "origin.git"), str(other)], repo.repo_root.parent)
    _git(["config", "user.email", "o@example.com"], other)
    _git(["config", "user.name", "other"], other)
    (other / "README.md").write_text("main version\n")
    _git(["commit", "-q", "-am", "main edit"], other)
    _git(["push", "-q", "origin", "main"], other)
    with pytest.raises(MergeConflict):
        wm.update_from_base(info.path)
    assert not wm.is_dirty(info.path)  # merge aborted cleanly


def test_wrong_branch_in_worktree_is_an_error(repo):
    wm = WorktreeManager(repo)
    path = worktree_path(repo, 11, "x")
    path.parent.mkdir(parents=True, exist_ok=True)
    run_git(["worktree", "add", "-b", "someone-elses-branch", str(path), "origin/main"], repo.repo_root)
    with pytest.raises(GitError):
        wm.ensure(11, "x")
