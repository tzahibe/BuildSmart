"""Branch + worktree isolation: one branch and one worktree per Issue, never the main checkout.

Naming: branch `agent/<issue>-<slug>`, worktree `<worktree_root>/<issue>-<slug>`.

Everything goes through `git -C <repo_root> worktree|branch|fetch|push` — commands that never move
the main checkout's HEAD, index or working tree (the user runs git in the IDE on that checkout
concurrently; see PROJECT_STATE "never mutate git in the main checkout"). `ensure()` reconciles a
branch/worktree left behind by a crashed attempt instead of creating a duplicate.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from agent_team.config import Config

_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


class GitError(RuntimeError):
    pass


class MergeConflict(GitError):
    pass


@dataclass(frozen=True)
class WorktreeInfo:
    issue_id: int
    branch: str
    path: Path
    head_sha: str
    created: bool           # a brand-new branch + worktree
    reconciled: bool        # reused something left behind by an earlier attempt
    note: str = ""


@dataclass(frozen=True)
class WorktreeEntry:
    path: Path
    head: str
    branch: str | None      # None when detached
    locked: bool


def run_git(args: list[str], cwd: Path, *, check: bool = True, timeout: int = 600, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=full_env)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {cwd} (exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def branch_name(config: Config, issue_id: int, slug: str) -> str:
    if not _SAFE_SLUG.match(slug):
        raise ValueError(f"unsafe slug {slug!r}")
    return f"{config.branch_prefix}{issue_id}-{slug}"


def worktree_path(config: Config, issue_id: int, slug: str) -> Path:
    if not _SAFE_SLUG.match(slug):
        raise ValueError(f"unsafe slug {slug!r}")
    return config.path(config.worktree_root) / f"{issue_id}-{slug}"


def issue_from_branch(config: Config, branch: str) -> int | None:
    if not branch.startswith(config.branch_prefix):
        return None
    m = re.match(r"^(\d+)-", branch[len(config.branch_prefix):])
    return int(m.group(1)) if m else None


class WorktreeManager:
    def __init__(self, config: Config, *, remote: str = "origin"):
        self.config = config
        self.root = config.repo_root
        self.remote = remote

    # -- queries ------------------------------------------------------------------------------
    def list_worktrees(self) -> list[WorktreeEntry]:
        out = run_git(["worktree", "list", "--porcelain"], self.root).stdout
        entries: list[WorktreeEntry] = []
        cur: dict = {}
        for line in out.splitlines() + [""]:
            if not line.strip():
                if cur.get("path"):
                    entries.append(WorktreeEntry(Path(cur["path"]), cur.get("head", ""), cur.get("branch"), cur.get("locked", False)))
                cur = {}
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                cur["path"] = value
            elif key == "HEAD":
                cur["head"] = value
            elif key == "branch":
                cur["branch"] = value.removeprefix("refs/heads/")
            elif key == "locked":
                cur["locked"] = True
            elif key == "detached":
                cur["branch"] = None
        return entries

    def agent_worktrees(self) -> list[WorktreeEntry]:
        root = self.config.path(self.config.worktree_root).resolve()
        return [e for e in self.list_worktrees() if e.path.resolve().is_relative_to(root)]

    def branch_exists(self, branch: str, *, remote: bool = False) -> bool:
        ref = f"refs/remotes/{self.remote}/{branch}" if remote else f"refs/heads/{branch}"
        return run_git(["show-ref", "--verify", "--quiet", ref], self.root, check=False).returncode == 0

    def has_remote(self) -> bool:
        return run_git(["remote", "get-url", self.remote], self.root, check=False).returncode == 0

    def fetch(self) -> bool:
        if not self.has_remote():
            return False
        proc = run_git(["fetch", "--prune", self.remote], self.root, check=False, timeout=300)
        return proc.returncode == 0

    #: Weekend/holiday mode: new work starts from (and PRs target) the period's integration branch.
    base_override: str | None = None

    def base_branch(self) -> str:
        return self.base_override or self.config.base_branch

    def base_ref(self, branch: str | None = None) -> str:
        base = branch or self.base_branch()
        if self.has_remote() and self.branch_exists(base, remote=True):
            return f"{self.remote}/{base}"
        return base

    def create_branch_from(self, name: str, source_ref: str) -> str:
        """Create `name` on the remote at `source_ref` (no-op when it exists). Returns its SHA."""
        self.fetch()
        if not self.branch_exists(name, remote=True):
            sha = run_git(["rev-parse", source_ref], self.root).stdout.strip()
            run_git(["push", self.remote, f"{sha}:refs/heads/{name}"], self.root, timeout=300)
            self.fetch()
        return run_git(["rev-parse", f"{self.remote}/{name}"], self.root).stdout.strip()

    def delete_remote_branch(self, name: str) -> bool:
        proc = run_git(["push", self.remote, "--delete", name], self.root, check=False, timeout=300)
        self.fetch()
        return proc.returncode == 0

    def ensure_named(self, issue_id: int, branch: str, slug: str = "rollup") -> WorktreeInfo:
        """A worktree for an existing branch that does not follow the issue naming (the rollup PR
        of an integration branch)."""
        path = worktree_path(self.config, issue_id, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fetch()
        registered = {e.path.resolve(): e for e in self.list_worktrees()}
        entry = registered.get(path.resolve())
        if entry is None:
            # git allows one checkout per branch: reuse whichever worktree already holds it
            entry = next((e for e in registered.values() if e.branch == branch), None)
            if entry is not None:
                path = entry.path
        if entry is not None:
            if entry.branch != branch:
                raise GitError(f"worktree {path} is registered on branch {entry.branch!r}, expected {branch!r}")
            run_git(["pull", "--ff-only", "-q", self.remote, branch], path, check=False)
            return WorktreeInfo(issue_id, branch, path, self.head_sha(path), created=False, reconciled=True, note="existing worktree reused")
        if self.branch_exists(branch):
            run_git(["worktree", "add", str(path), branch], self.root)
        else:
            run_git(["worktree", "add", "--track", "-b", branch, str(path), f"{self.remote}/{branch}"], self.root)
        return WorktreeInfo(issue_id, branch, path, self.head_sha(path), created=True, reconciled=False, note="worktree created")

    def base_sha(self, branch: str | None = None) -> str:
        return run_git(["rev-parse", self.base_ref(branch)], self.root).stdout.strip()

    @staticmethod
    def head_sha(path: Path) -> str:
        return run_git(["rev-parse", "HEAD"], path).stdout.strip()

    @staticmethod
    def is_dirty(path: Path) -> bool:
        return bool(run_git(["status", "--porcelain", "--untracked-files=no"], path).stdout.strip())

    @staticmethod
    def changed_files(path: Path, base_ref: str) -> list[str]:
        out = run_git(["diff", "--name-only", f"{base_ref}...HEAD"], path).stdout
        return [l.strip() for l in out.splitlines() if l.strip()]

    @staticmethod
    def diff(path: Path, base_ref: str, *, max_bytes: int = 400_000) -> str:
        out = run_git(["diff", f"{base_ref}...HEAD"], path).stdout
        if len(out) > max_bytes:
            return out[:max_bytes] + f"\n... [diff truncated at {max_bytes} bytes]\n"
        return out

    def commits_ahead(self, path: Path) -> int:
        out = run_git(["rev-list", "--count", f"{self.base_ref()}..HEAD"], path).stdout.strip()
        return int(out or 0)

    def merge_base(self, path: Path) -> str:
        return run_git(["merge-base", self.base_ref(), "HEAD"], path).stdout.strip()

    def behind_base(self, path: Path, base: str | None = None) -> int:
        out = run_git(["rev-list", "--count", f"HEAD..{self.base_ref(base)}"], path).stdout.strip()
        return int(out or 0)

    # -- lifecycle ----------------------------------------------------------------------------
    def ensure(self, issue_id: int, slug: str, base: str | None = None) -> WorktreeInfo:
        """Create or reconcile the branch/worktree for an issue. Never duplicates. `base` names the
        branch a NEW branch starts from (a ROOT's integration branch); default: the current base."""
        branch = branch_name(self.config, issue_id, slug)
        path = worktree_path(self.config, issue_id, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fetch()

        registered = {e.path.resolve(): e for e in self.list_worktrees()}
        entry = registered.get(path.resolve())
        if entry is not None:
            if entry.branch != branch:
                raise GitError(f"worktree {path} is registered on branch {entry.branch!r}, expected {branch!r}")
            return WorktreeInfo(issue_id, branch, path, self.head_sha(path), created=False, reconciled=True,
                                note="existing worktree reused")

        if path.exists():
            # A directory git does not know about (crash between mkdir and registration).
            stale = path.parent / "_stale" / f"{path.name}-{int(time.time())}"
            stale.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(stale))
            run_git(["worktree", "prune"], self.root)
            note = f"unregistered directory moved to {stale}; "
        else:
            note = ""

        if self.branch_exists(branch):
            run_git(["worktree", "add", str(path), branch], self.root)
            return WorktreeInfo(issue_id, branch, path, self.head_sha(path), created=False, reconciled=True,
                                note=note + "existing local branch checked out into a new worktree")
        if self.branch_exists(branch, remote=True):
            run_git(["worktree", "add", "--track", "-b", branch, str(path), f"{self.remote}/{branch}"], self.root)
            return WorktreeInfo(issue_id, branch, path, self.head_sha(path), created=False, reconciled=True,
                                note=note + "existing remote branch checked out into a new worktree")
        start = self.base_ref(base)
        run_git(["worktree", "add", "-b", branch, str(path), start], self.root)
        return WorktreeInfo(issue_id, branch, path, self.head_sha(path), created=True, reconciled=False,
                            note=note + f"new branch from {start}")

    def remove(self, issue_id: int, slug: str, *, delete_branch: bool = False, force: bool = False) -> list[str]:
        """Remove the worktree (and optionally the local branch). Returns what was done."""
        branch = branch_name(self.config, issue_id, slug)
        path = worktree_path(self.config, issue_id, slug)
        done: list[str] = []
        registered = {e.path.resolve(): e for e in self.list_worktrees()}
        if path.resolve() in registered:
            args = ["worktree", "remove", str(path)]
            if force:
                args.append("--force")
            run_git(args, self.root)
            done.append(f"removed worktree {path}")
        elif path.exists():
            shutil.rmtree(path)
            done.append(f"deleted unregistered directory {path}")
        run_git(["worktree", "prune"], self.root)
        if delete_branch and self.branch_exists(branch):
            run_git(["branch", "-D", branch], self.root)
            done.append(f"deleted local branch {branch}")
        return done

    def validation_worktree(self, ref: str) -> Path:
        """A fresh, detached, clean worktree at `ref` for regression/smoke gates."""
        sha = run_git(["rev-parse", ref], self.root).stdout.strip()
        path = self.config.path(self.config.worktree_root) / "_validation" / sha[:12]
        registered = {e.path.resolve() for e in self.list_worktrees()}
        if path.resolve() in registered:
            run_git(["worktree", "remove", "--force", str(path)], self.root)
        if path.exists():
            shutil.rmtree(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        run_git(["worktree", "add", "--detach", str(path), sha], self.root)
        return path

    def remove_validation_worktree(self, path: Path) -> None:
        registered = {e.path.resolve() for e in self.list_worktrees()}
        if path.resolve() in registered:
            run_git(["worktree", "remove", "--force", str(path)], self.root)
        elif path.exists():
            shutil.rmtree(path)
        run_git(["worktree", "prune"], self.root)

    # -- publishing / syncing -----------------------------------------------------------------
    def push(self, path: Path, branch: str) -> str:
        proc = run_git(["push", "-u", self.remote, f"{branch}:{branch}"], path, timeout=300)
        return (proc.stdout + proc.stderr).strip()

    def begin_merge(self, path: Path, base: str | None = None) -> list[str]:
        """Merge the base into the branch and, on conflict, LEAVE the merge in progress (conflict markers
        in the files) so the fixer can resolve it — the fixer's tools cannot run `git merge` themselves.
        Returns the conflicted paths (empty when the merge completed cleanly)."""
        self.fetch()
        base = self.base_ref(base)
        proc = run_git(["merge", "--no-edit", base], path, check=False)
        if proc.returncode == 0:
            return []
        conflicted = [l for l in run_git(["diff", "--name-only", "--diff-filter=U"], path, check=False).stdout.splitlines() if l.strip()]
        if not conflicted:                       # failed for another reason: do not leave a half state behind
            run_git(["merge", "--abort"], path, check=False)
            raise GitError(proc.stderr[-800:])
        return conflicted

    def update_from_base(self, path: Path, base: str | None = None) -> str:
        """Merge the (fetched) base into the branch inside its own worktree. Raises MergeConflict."""
        self.fetch()
        base = self.base_ref(base)
        proc = run_git(["merge", "--no-edit", base], path, check=False)
        if proc.returncode != 0:
            run_git(["merge", "--abort"], path, check=False)
            raise MergeConflict(f"merging {base} into {path.name} conflicts: {proc.stdout.strip()[-800:]}")
        return proc.stdout.strip()

    def delete_remote_branch(self, branch: str) -> bool:
        if not self.has_remote():
            return False
        proc = run_git(["push", self.remote, "--delete", branch], self.root, check=False, timeout=120)
        return proc.returncode == 0
