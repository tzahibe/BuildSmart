"""GitHub access: one small REST client, two transports, one fake.

- `GhCliTransport`   — runs `gh api` (the user's `gh auth login`); used by the local orchestrator.
- `TokenTransport`   — urllib + `GITHUB_TOKEN`; used inside GitHub Actions (CI gates).
- `FakeGitHub`       — in-memory issues/labels/PRs/checks for the orchestration tests.

Everything the orchestrator needs is a method here, so no other module shells out to `gh` or
speaks HTTP. Tokens never appear in logs: the transports read them from the environment and
`gh` keeps its own credential store.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent_team.labels import STATE_LABEL_PREFIX, state_to_label

API = "https://api.github.com"


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class Transport(Protocol):
    def request(self, method: str, path: str, *, body: dict | None = None, paginate: bool = False, raw: bool = False) -> Any: ...


class GhCliTransport:
    def __init__(self, binary: str | None = None):
        self.binary = binary or shutil.which("gh") or "gh"

    def available(self) -> tuple[bool, str]:
        if not shutil.which(self.binary) and not os.path.exists(self.binary):
            return False, "gh CLI is not installed (brew install gh)"
        proc = subprocess.run([self.binary, "auth", "status"], capture_output=True, text=True)
        if proc.returncode != 0:
            return False, "gh is not authenticated — run `gh auth login` once (browser flow)"
        return True, "gh authenticated"

    def command(self, method: str, path: str, *, has_body: bool = False, paginate: bool = False, raw: bool = False) -> list[str]:
        cmd = [self.binary, "api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
        if paginate:
            cmd += ["--paginate", "--slurp"]
        if raw:
            # Job logs carry ANSI sequences and artifacts are binary zips: without this flag `gh api`
            # refuses to write them at all (pilot finding — evidence silently went missing).
            cmd.append("--allow-escape-sequences")
        if has_body:
            cmd += ["--input", "-"]
        return cmd

    def request(self, method: str, path: str, *, body: dict | None = None, paginate: bool = False, raw: bool = False) -> Any:
        cmd = self.command(method, path, has_body=body is not None, paginate=paginate, raw=raw)
        stdin = json.dumps(body) if body is not None else None
        if raw and stdin is not None:
            stdin = stdin.encode()
        proc = subprocess.run(cmd, input=stdin, capture_output=True, text=not raw, timeout=300)
        if proc.returncode != 0:
            err = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode("utf-8", "replace")
            status = None
            if "HTTP " in err:
                try:
                    status = int(err.split("HTTP ")[1].split()[0].rstrip(":)"))
                except (ValueError, IndexError):
                    status = None
            raise GitHubError(f"gh api {method} {path} failed: {err.strip()[:500]}", status, err)
        if raw:
            return proc.stdout
        text = proc.stdout.strip()
        if not text:
            return None
        data = json.loads(text)
        if paginate and isinstance(data, list) and data and isinstance(data[0], list):
            return [item for page in data for item in page]
        return data


class TokenTransport:
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not self.token:
            raise GitHubError("GITHUB_TOKEN is not set")

    def request(self, method: str, path: str, *, body: dict | None = None, paginate: bool = False, raw: bool = False) -> Any:
        url = path if path.startswith("http") else API + path
        results: list = []
        while url:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {self.token}")
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("X-GitHub-Api-Version", "2022-11-28")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = resp.read()
                    link = resp.headers.get("Link", "")
            except urllib.error.HTTPError as exc:
                raise GitHubError(f"{method} {path} -> HTTP {exc.code}", exc.code, exc.read().decode("utf-8", "replace")[:500]) from exc
            if raw:
                return payload
            page = json.loads(payload) if payload.strip() else None
            if not paginate:
                return page
            results.extend(page if isinstance(page, list) else [page])
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
        return results


@dataclass
class GitHubClient:
    repo: str
    transport: Transport

    # -- issues -------------------------------------------------------------------------------
    def get_issue(self, number: int) -> dict:
        return self.transport.request("GET", f"/repos/{self.repo}/issues/{number}")

    def list_issues(self, *, labels: tuple[str, ...] = (), state: str = "open") -> list[dict]:
        q = f"state={state}&per_page=100"
        if labels:
            q += "&labels=" + ",".join(labels)
        items = self.transport.request("GET", f"/repos/{self.repo}/issues?{q}", paginate=True) or []
        return [i for i in items if "pull_request" not in i]

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return self.transport.request("POST", f"/repos/{self.repo}/issues", body={"title": title, "body": body, "labels": labels})

    def issue_labels(self, number: int) -> list[str]:
        return [l["name"] for l in self.get_issue(number).get("labels", [])]

    def add_labels(self, number: int, labels: list[str]) -> None:
        self.transport.request("POST", f"/repos/{self.repo}/issues/{number}/labels", body={"labels": labels})

    def remove_label(self, number: int, label: str) -> None:
        try:
            self.transport.request("DELETE", f"/repos/{self.repo}/issues/{number}/labels/{urllib.request.quote(label, safe='')}")
        except GitHubError as exc:
            if exc.status != 404:
                raise

    def set_state_label(self, number: int, state: str) -> str:
        """Replace whatever `agent:*` label is present with the one for `state`. Idempotent."""
        target = state_to_label(state)
        current = self.issue_labels(number)
        for l in current:
            if l.startswith(STATE_LABEL_PREFIX) and l != target:
                self.remove_label(number, l)
        if target not in current:
            self.add_labels(number, [target])
        return target

    def comment(self, number: int, body: str) -> dict:
        return self.transport.request("POST", f"/repos/{self.repo}/issues/{number}/comments", body={"body": body})

    def close_issue(self, number: int, reason: str = "completed") -> None:
        self.transport.request("PATCH", f"/repos/{self.repo}/issues/{number}", body={"state": "closed", "state_reason": reason})

    def reopen_issue(self, number: int) -> None:
        self.transport.request("PATCH", f"/repos/{self.repo}/issues/{number}", body={"state": "open"})

    # -- labels -------------------------------------------------------------------------------
    def list_labels(self) -> list[dict]:
        return self.transport.request("GET", f"/repos/{self.repo}/labels?per_page=100", paginate=True) or []

    def ensure_label(self, name: str, color: str, description: str) -> str:
        try:
            self.transport.request("POST", f"/repos/{self.repo}/labels", body={"name": name, "color": color, "description": description})
            return "created"
        except GitHubError as exc:
            if exc.status == 422:
                self.transport.request("PATCH", f"/repos/{self.repo}/labels/{urllib.request.quote(name, safe='')}",
                                       body={"color": color, "description": description})
                return "updated"
            raise

    # -- pull requests ------------------------------------------------------------------------
    def get_pr(self, number: int) -> dict:
        return self.transport.request("GET", f"/repos/{self.repo}/pulls/{number}")

    def find_pr_for_branch(self, branch: str, *, state: str = "open") -> dict | None:
        owner = self.repo.split("/")[0]
        prs = self.transport.request("GET", f"/repos/{self.repo}/pulls?head={owner}:{branch}&state={state}&per_page=10") or []
        return prs[0] if prs else None

    def create_pr(self, *, head: str, base: str, title: str, body: str, draft: bool = False) -> dict:
        return self.transport.request("POST", f"/repos/{self.repo}/pulls",
                                      body={"head": head, "base": base, "title": title, "body": body, "draft": draft})

    def update_pr(self, number: int, **fields_to_set: Any) -> dict:
        return self.transport.request("PATCH", f"/repos/{self.repo}/pulls/{number}", body=fields_to_set)

    def pr_files(self, number: int) -> list[str]:
        files = self.transport.request("GET", f"/repos/{self.repo}/pulls/{number}/files?per_page=100", paginate=True) or []
        return [f["filename"] for f in files]

    def review_pr(self, number: int, body: str, event: str = "COMMENT") -> dict:
        """Post the reviewer's verdict. Never APPROVE through the owner's token — that would be the
        author approving their own PR; the orchestrator's state store holds the real verdict."""
        if event == "APPROVE":
            event = "COMMENT"
        return self.transport.request("POST", f"/repos/{self.repo}/pulls/{number}/reviews", body={"body": body, "event": event})

    def merge_pr(self, number: int, *, method: str = "squash", title: str | None = None, sha: str | None = None) -> dict:
        body: dict[str, Any] = {"merge_method": method}
        if title:
            body["commit_title"] = title
        if sha:
            body["sha"] = sha
        return self.transport.request("PUT", f"/repos/{self.repo}/pulls/{number}/merge", body=body)

    def delete_branch(self, branch: str) -> bool:
        try:
            self.transport.request("DELETE", f"/repos/{self.repo}/git/refs/heads/{branch}")
            return True
        except GitHubError as exc:
            if exc.status in (404, 422):
                return False
            raise

    # -- commit statuses (the independent-review gate) ----------------------------------------
    def set_commit_status(self, sha: str, state: str, context: str, description: str, target_url: str | None = None) -> dict:
        body: dict[str, Any] = {"state": state, "context": context, "description": description[:140]}
        if target_url:
            body["target_url"] = target_url
        return self.transport.request("POST", f"/repos/{self.repo}/statuses/{sha}", body=body)

    def combined_status(self, sha: str) -> dict[str, dict]:
        """context -> {state, description, updated_at} (latest per context, as GitHub reports it)."""
        data = self.transport.request("GET", f"/repos/{self.repo}/commits/{sha}/status") or {}
        return {s["context"]: {"state": s.get("state"), "description": s.get("description"), "updated_at": s.get("updated_at")}
                for s in data.get("statuses", [])}

    # -- checks / actions ---------------------------------------------------------------------
    def check_runs(self, sha: str) -> list[dict]:
        data = self.transport.request("GET", f"/repos/{self.repo}/commits/{sha}/check-runs?per_page=100")
        return (data or {}).get("check_runs", [])

    def workflow_runs(self, sha: str) -> list[dict]:
        data = self.transport.request("GET", f"/repos/{self.repo}/actions/runs?head_sha={sha}&per_page=50")
        return (data or {}).get("workflow_runs", [])

    def run_jobs(self, run_id: int) -> list[dict]:
        data = self.transport.request("GET", f"/repos/{self.repo}/actions/runs/{run_id}/jobs?per_page=100")
        return (data or {}).get("jobs", [])

    def job_logs(self, job_id: int, *, max_bytes: int = 200_000) -> str:
        raw = self.transport.request("GET", f"/repos/{self.repo}/actions/jobs/{job_id}/logs", raw=True)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        return raw[-max_bytes:] if raw else ""

    def run_artifacts(self, run_id: int) -> list[dict]:
        data = self.transport.request("GET", f"/repos/{self.repo}/actions/runs/{run_id}/artifacts?per_page=100")
        return (data or {}).get("artifacts", [])

    def download_artifact(self, artifact_id: int) -> bytes:
        return self.transport.request("GET", f"/repos/{self.repo}/actions/artifacts/{artifact_id}/zip", raw=True)

    # -- repo / protection --------------------------------------------------------------------
    def get_repo(self) -> dict:
        return self.transport.request("GET", f"/repos/{self.repo}")

    def get_branch_protection(self, branch: str) -> dict | None:
        try:
            return self.transport.request("GET", f"/repos/{self.repo}/branches/{branch}/protection")
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise

    def set_branch_protection(self, branch: str, required_checks: list[str], *, enforce_admins: bool = False) -> dict:
        body = {
            "required_status_checks": {"strict": True, "contexts": required_checks},
            "enforce_admins": enforce_admins,
            "required_pull_request_reviews": None,
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "required_linear_history": False,
        }
        return self.transport.request("PUT", f"/repos/{self.repo}/branches/{branch}/protection", body=body)

    def compare(self, base: str, head: str) -> dict:
        return self.transport.request("GET", f"/repos/{self.repo}/compare/{base}...{head}")


# --------------------------------------------------------------------------------------------
# fake
# --------------------------------------------------------------------------------------------

@dataclass
class FakeGitHub:
    """In-memory GitHub for tests: enough of the surface above to drive the orchestrator."""
    repo: str = "acme/widgets"
    issues: dict[int, dict] = field(default_factory=dict)
    prs: dict[int, dict] = field(default_factory=dict)
    labels: dict[str, dict] = field(default_factory=dict)
    checks: dict[str, list[dict]] = field(default_factory=dict)        # sha -> check runs
    statuses: dict[str, dict[str, dict]] = field(default_factory=dict)   # sha -> {context: {state, description}}
    status_log: list[tuple[str, str, str, str]] = field(default_factory=list)  # (sha, context, state, description)
    artifacts: dict[str, dict[str, dict]] = field(default_factory=dict)  # sha -> {name: json}
    comments: list[tuple[int, str]] = field(default_factory=list)
    reviews: list[tuple[int, str, str]] = field(default_factory=list)
    merged: list[int] = field(default_factory=list)
    deleted_branches: list[str] = field(default_factory=list)
    protection: dict[str, dict] = field(default_factory=dict)
    next_number: int = 100
    fail_merge_with: str | None = None
    default_branch_sha: str = "basesha"
    on_merge: Any = None   # optional callable(pr) -> merge sha, so tests can really merge into a temp origin
    on_head_sha: Any = None  # optional callable(branch) -> sha, so a pushed repair moves the PR head like on GitHub

    def add_issue(self, number: int, title: str, body: str, labels: list[str], *, author_association: str = "OWNER",
                  state: str = "open") -> dict:
        self.issues[number] = {"number": number, "title": title, "body": body, "state": state,
                               "labels": [{"name": l} for l in labels], "author_association": author_association,
                               "user": {"login": "owner"}, "html_url": f"https://github.com/{self.repo}/issues/{number}"}
        return self.issues[number]

    # issues
    def get_issue(self, number: int) -> dict:
        if number not in self.issues:
            raise GitHubError("not found", 404)
        return self.issues[number]

    def list_issues(self, *, labels: tuple[str, ...] = (), state: str = "open") -> list[dict]:
        out = []
        for i in sorted(self.issues.values(), key=lambda x: x["number"]):
            if state != "all" and i["state"] != state:
                continue
            names = {l["name"] for l in i["labels"]}
            if all(l in names for l in labels):
                out.append(i)
        return out

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        n = self.next_number
        self.next_number += 1
        return self.add_issue(n, title, body, labels)

    def issue_labels(self, number: int) -> list[str]:
        return [l["name"] for l in self.get_issue(number)["labels"]]

    def add_labels(self, number: int, labels: list[str]) -> None:
        cur = self.issue_labels(number)
        self.get_issue(number)["labels"] = [{"name": l} for l in cur + [l for l in labels if l not in cur]]

    def remove_label(self, number: int, label: str) -> None:
        self.get_issue(number)["labels"] = [l for l in self.get_issue(number)["labels"] if l["name"] != label]

    def set_state_label(self, number: int, state: str) -> str:
        target = state_to_label(state)
        for l in self.issue_labels(number):
            if l.startswith(STATE_LABEL_PREFIX) and l != target:
                self.remove_label(number, l)
        if target not in self.issue_labels(number):
            self.add_labels(number, [target])
        return target

    def comment(self, number: int, body: str) -> dict:
        self.comments.append((number, body))
        return {"id": len(self.comments)}

    def close_issue(self, number: int, reason: str = "completed") -> None:
        self.get_issue(number)["state"] = "closed"

    def reopen_issue(self, number: int) -> None:
        self.get_issue(number)["state"] = "open"

    # labels
    def list_labels(self) -> list[dict]:
        return list(self.labels.values())

    def ensure_label(self, name: str, color: str, description: str) -> str:
        status = "updated" if name in self.labels else "created"
        self.labels[name] = {"name": name, "color": color, "description": description}
        return status

    # prs
    def get_pr(self, number: int) -> dict:
        if number not in self.prs:
            raise GitHubError("not found", 404)
        pr = self.prs[number]
        if self.on_head_sha and not pr.get("merged"):
            pr["head"]["sha"] = self.on_head_sha(pr["head"]["ref"]) or pr["head"]["sha"]
        return pr

    def find_pr_for_branch(self, branch: str, *, state: str = "open") -> dict | None:
        for pr in self.prs.values():
            if pr["head"]["ref"] == branch and (state == "all" or pr["state"] == state):
                return self.get_pr(pr["number"])
        return None

    def create_pr(self, *, head: str, base: str, title: str, body: str, draft: bool = False) -> dict:
        n = self.next_number
        self.next_number += 1
        self.prs[n] = {"number": n, "state": "open", "title": title, "body": body, "merged": False, "draft": draft,
                       "head": {"ref": head, "sha": f"sha-{head}"}, "base": {"ref": base, "sha": self.default_branch_sha},
                       "mergeable": True, "mergeable_state": "clean", "html_url": f"https://github.com/{self.repo}/pull/{n}"}
        return self.prs[n]

    def update_pr(self, number: int, **fields_to_set: Any) -> dict:
        self.get_pr(number).update(fields_to_set)
        return self.get_pr(number)

    def pr_files(self, number: int) -> list[str]:
        return self.get_pr(number).get("files", [])

    def review_pr(self, number: int, body: str, event: str = "COMMENT") -> dict:
        self.reviews.append((number, event if event != "APPROVE" else "COMMENT", body))
        return {"id": len(self.reviews)}

    required_contexts_for_merge: tuple[str, ...] = ()   # simulate branch protection on merge (405 like GitHub)

    def merge_pr(self, number: int, *, method: str = "squash", title: str | None = None, sha: str | None = None) -> dict:
        if self.fail_merge_with:
            raise GitHubError(self.fail_merge_with, 405)
        pr = self.get_pr(number)
        head = pr["head"]["sha"]
        for ctx in self.required_contexts_for_merge:
            run_ok = any(r.get("name") == ctx and r.get("conclusion") == "success" for r in self.checks.get(head, []))
            status_ok = self.statuses.get(head, {}).get(ctx, {}).get("state") == "success"
            if not (run_ok or status_ok):
                raise GitHubError(f"Required status check \"{ctx}\" is expected.", 405)
        pr["merged"] = True
        pr["state"] = "closed"
        pr["merge_commit_sha"] = self.on_merge(pr) if self.on_merge else f"merge-{number}"
        self.merged.append(number)
        self.default_branch_sha = pr["merge_commit_sha"]
        return {"merged": True, "sha": pr["merge_commit_sha"]}

    def delete_branch(self, branch: str) -> bool:
        self.deleted_branches.append(branch)
        return True

    # statuses
    def set_commit_status(self, sha: str, state: str, context: str, description: str, target_url: str | None = None) -> dict:
        self.statuses.setdefault(sha, {})[context] = {"state": state, "description": description, "updated_at": None}
        self.status_log.append((sha, context, state, description))
        return {"state": state, "context": context}

    def combined_status(self, sha: str) -> dict[str, dict]:
        return dict(self.statuses.get(sha, {}))

    # checks
    def check_runs(self, sha: str) -> list[dict]:
        return self.checks.get(sha, [])

    def workflow_runs(self, sha: str) -> list[dict]:
        return [{"id": 1, "head_sha": sha, "status": "completed", "conclusion": "success"}] if sha in self.checks else []

    def run_jobs(self, run_id: int) -> list[dict]:
        return []

    def job_logs(self, job_id: int, *, max_bytes: int = 200_000) -> str:
        return ""

    def run_artifacts(self, run_id: int) -> list[dict]:
        return []

    def download_artifact(self, artifact_id: int) -> bytes:
        return b""

    # repo
    def get_repo(self) -> dict:
        return {"full_name": self.repo, "default_branch": "main", "permissions": {"admin": True}}

    def get_branch_protection(self, branch: str) -> dict | None:
        return self.protection.get(branch)

    def set_branch_protection(self, branch: str, required_checks: list[str], *, enforce_admins: bool = False) -> dict:
        self.protection[branch] = {"required_status_checks": {"contexts": required_checks}, "enforce_admins": {"enabled": enforce_admins}}
        return self.protection[branch]

    def compare(self, base: str, head: str) -> dict:
        return {"behind_by": 0, "ahead_by": 1}
