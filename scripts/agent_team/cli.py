"""`scripts/agentctl` — the operator / Team Lead command line.

    agentctl status                      what are my agents doing?
    agentctl run [--once] [--dry-run]    the orchestrator loop (foreground)
    agentctl start | stop                the orchestrator as a background daemon (pid file)
    agentctl dry-run                     one tick with no spawn / no push / no PR / no merge
    agentctl labels                      create/update the label catalogue on GitHub
    agentctl protect-main                configure branch protection (reports the exact blocker)
    agentctl issue validate N | queue N | create --from FILE [--queue] | render --from FILE
    agentctl approve N --kind lead_approval|lead_architecture_review [--note ...]
    agentctl requeue N | block N --reason ... | resume-pr N [--update-base] [--rereview --reason ...]
    agentctl audit N                     the reconstructable timeline of one issue
    agentctl investigate --domain D "question"   an on-demand read-only Sonnet domain lead
    agentctl reconcile                   one reconciliation pass, printed
    agentctl doctor                      environment checks (gh auth, claude binary, config)
    agentctl pause | resume              stop/continue taking new work (audited; the owner can also do it on Telegram)
    agentctl remote start|run|stop|status|pair|unpair|doctor   the Telegram owner control plane

Governance: the orchestrator never merges and never adds owner:approved. `issue queue` adds
agent:queued only; execution starts when the owner adds owner:approved (Telegram "Create & Queue" /
"approve", or the GitHub UI). Merges happen on the owner's CONFIRM MERGE (Telegram) or the GitHub button.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from agent_team import state_machine as sm
from agent_team.agent_runner import ClaudeCliRunner, FakeAgentRunner, resolve_claude_binary
from agent_team.audit import setup_logging
from agent_team.config import Config, ConfigError, load_config
from agent_team.github_client import GhCliTransport, GitHubClient, GitHubError
from agent_team.issue_contract import ContractError, parse_contract, render_body, verification_manifest
from agent_team.labels import ALL_LABELS, metadata_labels
from agent_team.orchestrator import Orchestrator, OrchestratorAlreadyRunning
from agent_team.resource_manager import ResourceManager
from agent_team.state_store import StateStore, TransitionConflict


def _github(config: Config, *, require_auth: bool = True) -> GitHubClient:
    transport = GhCliTransport()
    ok, why = transport.available()
    if not ok and require_auth:
        raise SystemExit(f"GitHub access unavailable: {why}")
    return GitHubClient(config.repo, transport)


def _orchestrator(config: Config, *, dry_run: bool, fake_runner: bool = False) -> Orchestrator:
    github = _github(config, require_auth=True)
    runner = FakeAgentRunner() if (fake_runner or dry_run) else ClaudeCliRunner(
        config.claude_binary, heartbeat_interval=config.heartbeat_interval_seconds)
    return Orchestrator(config, github=github, runner=runner, dry_run=dry_run)


# -- commands ---------------------------------------------------------------------------------

def cmd_status(config: Config, args) -> int:
    from agent_team.status import render
    store = StateStore(config.state_db_path)
    print(render(config, store, ResourceManager(config, store), probe_machine=not args.no_probe))
    pid = _daemon_pid(config)
    print(f"orchestrator daemon: {'running (pid %s)' % pid if pid else 'not running'}")
    if sys.platform == "darwin":
        for w, st in launchd_status(config).items():
            print(f"launchd {w}: {st}")
    return 0


def cmd_run(config: Config, args) -> int:
    setup_logging(config, verbose=args.verbose)
    try:
        orch = _orchestrator(config, dry_run=args.dry_run)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    try:
        orch.run(once=args.once)
    except OrchestratorAlreadyRunning as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 3
    return 0


def cmd_dry_run(config: Config, args) -> int:
    setup_logging(config, verbose=args.verbose)
    try:
        orch = _orchestrator(config, dry_run=True)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    report = orch.tick()
    print("DRY-RUN tick:", report.summary())
    from agent_team.status import render
    print()
    print(render(config, orch.store, orch.resources, probe_machine=True))
    orch.shutdown()
    return 0


def _pidfile(config: Config) -> Path:
    return config.path(config.state_dir) / "orchestrator.pid"


def _daemon_pid(config: Config) -> int | None:
    p = _pidfile(config)
    if not p.exists():
        return None
    try:
        pid = int(p.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def cmd_start(config: Config, args) -> int:
    if _daemon_pid(config):
        print(f"already running (pid {_daemon_pid(config)})")
        return 0
    ok, why = GhCliTransport().available()
    if not ok:
        print(f"cannot start: {why}", file=sys.stderr)
        return 2
    logs = config.path(config.logs_dir)
    logs.mkdir(parents=True, exist_ok=True)
    _pidfile(config).parent.mkdir(parents=True, exist_ok=True)
    out = open(logs / "daemon.out", "a")
    cmd = [sys.executable, "-c",
           f"import sys; sys.path.insert(0, {str(config.repo_root / 'scripts')!r}); from agent_team.cli import main; sys.exit(main())",
           "run"] + (["--verbose"] if args.verbose else [])
    proc = subprocess.Popen(cmd, cwd=str(config.repo_root), stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
                            env={**os.environ, "AGENT_TEAM_REPO_ROOT": str(config.repo_root)})
    _pidfile(config).write_text(str(proc.pid))
    print(f"orchestrator started (pid {proc.pid}); log: {logs / 'orchestrator.log'}")
    return 0


def cmd_stop(config: Config, args) -> int:
    pid = _daemon_pid(config)
    if not pid:
        print("not running")
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(60):
        time.sleep(0.5)
        if not _daemon_pid(config):
            break
    print(f"stopped (pid {pid})" if not _daemon_pid(config) else f"pid {pid} still shutting down")
    _pidfile(config).unlink(missing_ok=True)
    return 0


def cmd_labels(config: Config, args) -> int:
    if args.dry_run:
        for l in ALL_LABELS:
            print(f"{l.name:22s} #{l.color} {l.description}")
        return 0
    gh = _github(config)
    for l in ALL_LABELS:
        print(f"{gh.ensure_label(l.name, l.color, l.description):8s} {l.name}")
    return 0


def cmd_protect_main(config: Config, args) -> int:
    gh = _github(config)
    try:
        repo = gh.get_repo()
        perms = repo.get("permissions") or {}
        print(f"repo {repo.get('full_name')} default branch {repo.get('default_branch')} admin={perms.get('admin')}")
        current = gh.get_branch_protection(config.base_branch)
        print("current protection:", json.dumps(current, indent=1)[:800] if current else "none")
        if args.show:
            return 0
        enforce = True if args.enforce_admins else config.protect_enforce_admins
        contexts = list(config.protection_required_contexts)
        res = gh.set_branch_protection(config.base_branch, contexts, enforce_admins=enforce)
        enabled = (res.get("enforce_admins") or {}).get("enabled")
        store = StateStore(config.state_db_path)
        store.record_event(None, "protection_set", {"branch": config.base_branch, "contexts": contexts, "enforce_admins": enabled,
                                                    "by": "agentctl protect-main"})
        print(f"protection set on {config.base_branch}: required contexts {contexts}, enforce_admins={enabled}")
        if not enabled:
            print("NOTE: administrators are exempt — break-glass only. The orchestrator never merges through that "
                  "exemption; reconciliation records any bypass as `admin_bypass_detected` in the audit trail.")
        return 0
    except GitHubError as exc:
        print(f"BLOCKED: {exc} (HTTP {exc.status}) — {exc.body[:300]}", file=sys.stderr)
        return 4


def _read_contract_file(path: Path, number: int, title: str | None, config: Config):
    text = path.read_text(encoding="utf-8")
    first, _, rest = text.partition("\n")
    if first.startswith("# "):
        title = title or first[2:].strip()
        body = rest
    else:
        body = text
    if not title:
        raise SystemExit("a title is required: first line `# [agent] Title` in the file or --title")
    return parse_contract(number, title, body, known_locks=config.known_locks, behavior_domains=config.behavior_domains)


def cmd_issue(config: Config, args) -> int:
    if args.issue_cmd == "render":
        c = _read_contract_file(Path(args.from_file), 0, args.title, config)
        print(f"# {c.title}\n")
        print(render_body(c))
        return 0
    if args.issue_cmd == "create":
        try:
            c = _read_contract_file(Path(args.from_file), 0, args.title, config)
        except ContractError as exc:
            print("contract invalid:\n- " + "\n- ".join(exc.problems), file=sys.stderr)
            return 1
        labels = ["agent:queued" if args.queue else "agent:draft", *metadata_labels(c.domains, c.risk, c.resource_class)]
        gh = _github(config)
        issue = gh.create_issue(c.title, render_body(c), labels)
        print(f"created #{issue['number']} {issue.get('html_url')} labels={labels}")
        if args.queue:
            print(f"note: queued but NOT approved — the owner must add {config.owner_approval_label} before it runs")
        return 0
    gh = _github(config)
    issue = gh.get_issue(args.number)
    try:
        c = parse_contract(issue["number"], issue.get("title", ""), issue.get("body") or "", known_locks=config.known_locks,
                           behavior_domains=config.behavior_domains)
    except ContractError as exc:
        print(f"#{args.number} contract INVALID:\n- " + "\n- ".join(exc.problems))
        return 1
    manifest = verification_manifest(c, regression_domains=config.regression_domains)
    if args.issue_cmd == "validate":
        print(f"#{args.number} contract OK: {c.risk}/{c.resource_class} domains={list(c.domains)} AC={len(c.acceptance_criteria)} "
              f"targets={len(c.verification)} deps={list(c.dependencies)} regression_required={manifest['regression_required']} "
              f"lost_allowance={c.lost_allowance} semantic_acs={list(c.semantic_review_acs)}")
        if args.json:
            print(json.dumps(manifest, indent=2))
        return 0
    if args.issue_cmd == "queue":
        if issue.get("author_association", "NONE") not in config.executable_author_associations:
            print(f"refusing: author association {issue.get('author_association')} is not executable")
            return 1
        expected = set(metadata_labels(c.domains, c.risk, c.resource_class))
        have = [l["name"] for l in issue.get("labels", [])]
        for l in have:
            if l.split(":")[0] in ("domain", "risk", "resource") and l not in expected:
                gh.remove_label(args.number, l)
        gh.add_labels(args.number, sorted(expected - set(have)))
        gh.set_state_label(args.number, sm.QUEUED)
        approved = config.owner_approval_label in have
        print(f"#{args.number} queued (labels: agent:queued + {sorted(expected)}); owner approval: "
              + ("present" if approved else f"MISSING — nothing runs until the owner adds {config.owner_approval_label} (Telegram or GitHub)"))
        return 0
    return 1


def cmd_approve(config: Config, args) -> int:
    store = StateStore(config.state_db_path)
    rec = store.get(args.number)
    if rec is None:
        print(f"#{args.number} is not tracked")
        return 1
    store.add_approval(args.number, args.kind, "opus-team-lead", args.note or "")
    print(f"#{args.number}: recorded {args.kind} (state {rec.state})")
    try:
        _github(config).comment(args.number, f"**[agent-team]** Team Lead recorded `{args.kind}`: {args.note or ''}")
    except SystemExit:
        pass
    return 0


def cmd_requeue(config: Config, args) -> int:
    store = StateStore(config.state_db_path)
    rec = store.get(args.number)
    if rec is None:
        print("not tracked")
        return 1
    try:
        store.release_locks(args.number, "requeue")
        store.transition(args.number, sm.QUEUED, allowed_from=(sm.BLOCKED,), attempt_number=0 if args.reset_attempts else rec.attempt_number,
                         failure_class=None, last_error=None, note=f"requeued by lead: {args.reason or ''}")
    except (TransitionConflict, Exception) as exc:  # noqa: BLE001
        print(f"cannot requeue: {exc}")
        return 1
    try:
        gh = _github(config)
        gh.set_state_label(args.number, sm.QUEUED)
        gh.comment(args.number, f"**[agent-team]** Team Lead requeued: {args.reason or ''}")
    except SystemExit:
        pass
    print(f"#{args.number} -> QUEUED")
    return 0


def cmd_resume_pr(config: Config, args) -> int:
    """Lead decision after a BLOCKED PR: resume at PR_OPEN. `--update-base` first merges the base
    branch into the Issue branch (in its own worktree) and pushes, so CI re-runs against the current
    workflow/base — the normal move after an ENVIRONMENT/INFRA fix landed on main. `--rereview
    --reason "..."` additionally clears a stored review verdict that is bound to the (unchanged)
    head so the orchestrator's REVIEW step runs a fresh independent review instead of reporting the
    old verdict forever — the fix for a verdict later shown to be factually wrong."""
    if args.rereview and not args.reason:
        print("error: --rereview requires --reason \"<why the previous verdict is being discarded>\"")
        return 1
    from agent_team.worktree_manager import MergeConflict, WorktreeManager
    store = StateStore(config.state_db_path)
    rec = store.get(args.number)
    if rec is None or not rec.pr_number:
        print("not tracked or no PR")
        return 1
    if args.update_base:
        wm = WorktreeManager(config)
        slug = rec.contract_dict().get("slug") or Path(rec.worktree).name.split("-", 1)[1]
        info = wm.ensure(args.number, slug)
        try:
            behind = wm.behind_base(info.path)
            if behind:
                wm.update_from_base(info.path)
                wm.push(info.path, info.branch)
                print(f"#{args.number}: merged {wm.base_ref()} into {info.branch} ({behind} commit(s)) and pushed")
            else:
                print(f"#{args.number}: branch already up to date with {wm.base_ref()}")
        except MergeConflict as exc:
            print(f"cannot update base: {exc}")
            return 1
        store.record_event(args.number, "base_updated_by_lead", {"behind": behind, "head": wm.head_sha(info.path)})
    if args.rereview:
        rec = store.get(args.number)
        previous_verdict = rec.review_verdict
        try:
            gh = _github(config)
            head = gh.get_pr(rec.pr_number)["head"]["sha"]
        except SystemExit:
            gh, head = None, None
        store.update(args.number, review_verdict=None)
        store.record_event(args.number, "review_reset_by_lead", {"reason": args.reason, "previous_verdict": previous_verdict})
        if gh is not None:
            try:
                gh.comment(args.number, f"**[agent-team]** Team Lead ordered a fresh independent review: {args.reason}\n\n"
                                        f"Previous verdict: `{previous_verdict}`")
            except SystemExit:
                pass
            if head:
                try:
                    gh.set_commit_status(head, "pending", config.review_status_context,
                                         "re-review ordered by the Team Lead", target_url=rec.pr_url)
                except SystemExit:
                    pass
        print(f"#{args.number}: cleared review_verdict ({previous_verdict}) and ordered a fresh review: {args.reason}")
    try:
        note = "resumed at PR by lead"
        if args.update_base:
            note += " (base updated)"
        if args.rereview:
            note += " (re-review ordered)"
        store.transition(args.number, sm.PR_OPEN, allowed_from=(sm.BLOCKED,), failure_class=None, last_error=None,
                         validated_commit=None, note=note)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot resume: {exc}")
        return 1
    try:
        _github(config).set_state_label(args.number, sm.PR_OPEN)
    except SystemExit:
        pass
    print(f"#{args.number} -> PR_OPEN (CI will re-run its evaluation)")
    return 0


def cmd_block(config: Config, args) -> int:
    store = StateStore(config.state_db_path)
    rec = store.get(args.number)
    if rec is None:
        print("not tracked")
        return 1
    try:
        store.release_locks(args.number, "lead-block")
        store.transition(args.number, sm.BLOCKED, failure_class="LEAD_BLOCKED", last_error=args.reason, note="blocked by lead")
    except Exception as exc:  # noqa: BLE001
        print(f"cannot block: {exc}")
        return 1
    try:
        gh = _github(config)
        gh.set_state_label(args.number, sm.BLOCKED)
        gh.comment(args.number, f"**[agent-team]** Team Lead blocked this issue: {args.reason}")
    except SystemExit:
        pass
    print(f"#{args.number} -> BLOCKED")
    return 0


def cmd_audit(config: Config, args) -> int:
    store = StateStore(config.state_db_path)
    rec = store.get(args.number)
    if rec is None:
        print("not tracked")
        return 1
    print(f"#{rec.issue_id} {rec.title}\n state={rec.state} risk={rec.risk} class={rec.resource_class} attempt={rec.attempt_number} "
          f"pr={rec.pr_number} branch={rec.branch}\n worktree={rec.worktree}\n validated={rec.validated_commit} review={rec.review_verdict} "
          f"failure_class={rec.failure_class}\n last_error={rec.last_error}\n approvals={rec.approvals}\n")
    for e in store.events(args.number, limit=args.limit):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e["ts"]))
        payload = json.dumps(e["payload"], ensure_ascii=False)
        print(f"{ts}  {e['kind']:18s} {payload[:200]}")
    runs = config.path(config.logs_dir) / "runs" / str(args.number)
    if runs.exists():
        print("\nrun records:")
        for p in sorted(runs.iterdir()):
            print("  ", p)
    return 0


def cmd_investigate(config: Config, args) -> int:
    setup_logging(config)
    runner = ClaudeCliRunner(config.claude_binary)
    orch = Orchestrator(config, github=_github(config, require_auth=False), runner=runner, dry_run=True)
    result = orch.investigate(args.domain, args.question)
    if not result.ok:
        print(f"domain lead failed: {result.error}", file=sys.stderr)
        return 1
    print(json.dumps(result.structured, indent=2, ensure_ascii=False))
    return 0


def cmd_reconcile(config: Config, args) -> int:
    setup_logging(config)
    from agent_team.reconciliation import reconcile
    orch = _orchestrator(config, dry_run=args.dry_run, fake_runner=True)
    for a in reconcile(orch) or ["nothing to reconcile"]:
        print(a)
    orch.release_singleton()
    return 0


def cmd_doctor(config: Config, args) -> int:
    ok = True
    print(f"config: {config.repo_root / '.agent' / 'config.yaml'} (repo {config.repo}, base {config.base_branch})")
    gh_ok, why = GhCliTransport().available()
    print(f"gh: {'OK' if gh_ok else 'MISSING'} — {why}")
    ok &= gh_ok
    try:
        b = resolve_claude_binary(config.claude_binary)
        v = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        print(f"claude: OK — {b} ({v})")
    except Exception as exc:  # noqa: BLE001
        print(f"claude: MISSING — {exc}")
        ok = False
    print(f"state db: {config.state_db_path} ({'exists' if config.state_db_path.exists() else 'not created yet'})")
    print(f"worktree root: {config.path(config.worktree_root)}")
    from agent_team.resource_manager import PsutilProbe
    p = PsutilProbe()
    print(f"machine: CPU {p.cpu_percent(1.0):.0f}% free RAM {p.free_memory_gb():.1f} GiB "
          f"(limits: {config.cpu_threshold_percent:.0f}%, {config.min_free_memory_gb:.1f} GiB)")
    print(f"daemon: {'running (pid %s)' % _daemon_pid(config) if _daemon_pid(config) else 'not running'}")
    return 0 if ok else 1


# -- pause / resume ---------------------------------------------------------------------------

def cmd_pause(config: Config, args) -> int:
    store = StateStore(config.state_db_path)
    store.set_meta("scheduler_paused", "1")
    store.record_event(None, "scheduler_paused", {"source": "cli", "by": "operator", "reason": args.reason or ""})
    print("paused: no new claims, no new workers, no new repair loops")
    return 0


def cmd_resume(config: Config, args) -> int:
    store = StateStore(config.state_db_path)
    store.set_meta("scheduler_paused", "0")
    store.record_event(None, "scheduler_resumed", {"source": "cli", "by": "operator", "reason": args.reason or ""})
    print("resumed")
    return 0


# -- remote (Telegram) ------------------------------------------------------------------------

def _remote_pidfile(config: Config) -> Path:
    return config.path(config.state_dir) / "remote.pid"


def _remote_pid(config: Config) -> int | None:
    p = _remote_pidfile(config)
    if not p.exists():
        return None
    try:
        pid = int(p.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def _remote_env(config: Config) -> dict:
    from agent_team.remote.transport import load_env_file
    env = dict(os.environ)
    for k, v in load_env_file(config.telegram_env_file).items():
        env.setdefault(k, v)
    return env


def _build_remote_service(config: Config):
    from agent_team.remote.gateway import Gateway
    from agent_team.remote.interpreter import ClaudeInterpreter
    from agent_team.remote.service import RemoteService
    from agent_team.remote.transport import HttpTelegramTransport, resolve_token
    from agent_team.remote.voice import make_transcriber
    token = resolve_token(config.telegram_token_env, config.telegram_env_file)
    if not token:
        raise SystemExit(f"no bot token: set {config.telegram_token_env} or put it in {config.telegram_env_file}")
    github = _github(config, require_auth=True)
    orch = Orchestrator(config, github=github, runner=FakeAgentRunner(), dry_run=False)   # actions only; never runs the loop
    store = orch.store
    interpreter = ClaudeInterpreter(repo_root=config.repo_root, model=config.interpreter_model,
                                    timeout_seconds=config.interpreter_timeout_seconds, binary=config.claude_binary)
    gateway = Gateway(config=config, store=store, github=github, orch=orch, interpreter=interpreter)
    return RemoteService(config=config, store=store, transport=HttpTelegramTransport(token), gateway=gateway,
                         transcriber=make_transcriber(config.transcription_provider))


def cmd_remote(config: Config, args) -> int:
    sub = args.remote_cmd
    if sub == "run":
        setup_logging(config, verbose=getattr(args, "verbose", False))
        if not config.telegram_enabled:
            print("remote_control.telegram.enabled is false", file=sys.stderr)
            return 2
        for k, v in _remote_env(config).items():
            os.environ.setdefault(k, v)
        from agent_team.remote.service import RemoteAlreadyRunning
        svc = _build_remote_service(config)
        try:
            svc.run()
        except RemoteAlreadyRunning as exc:
            print(f"refusing to start: {exc}", file=sys.stderr)
            return 3
        return 0
    if sub == "start":
        if _remote_pid(config):
            print(f"already running (pid {_remote_pid(config)})")
            return 0
        env = _remote_env(config)
        if not env.get(config.telegram_token_env):
            print(f"cannot start: no {config.telegram_token_env} (env or {config.telegram_env_file})", file=sys.stderr)
            return 2
        logs = config.path(config.logs_dir)
        logs.mkdir(parents=True, exist_ok=True)
        _remote_pidfile(config).parent.mkdir(parents=True, exist_ok=True)
        out = open(logs / "remote.out", "a")
        cmd = [sys.executable, "-c",
               f"import sys; sys.path.insert(0, {str(config.repo_root / 'scripts')!r}); from agent_team.cli import main; sys.exit(main())",
               "remote", "run"]
        env["AGENT_TEAM_REPO_ROOT"] = str(config.repo_root)
        proc = subprocess.Popen(cmd, cwd=str(config.repo_root), stdout=out, stderr=subprocess.STDOUT, start_new_session=True, env=env)
        _remote_pidfile(config).write_text(str(proc.pid))
        print(f"telegram service started (pid {proc.pid}); log: {logs / 'orchestrator.log'}")
        return 0
    if sub == "stop":
        pid = _remote_pid(config)
        if not pid:
            print("not running")
            return 0
        os.kill(pid, signal.SIGTERM)
        for _ in range(120):
            time.sleep(0.5)
            if not _remote_pid(config):
                break
        print(f"stopped (pid {pid})" if not _remote_pid(config) else f"pid {pid} still shutting down (waits for the current long poll)")
        _remote_pidfile(config).unlink(missing_ok=True)
        return 0
    store = StateStore(config.state_db_path)
    if sub == "status":
        owner = store.owner()
        pending = [n for n in store.due_notifications(50)]
        print(f"service: {'running (pid %s)' % _remote_pid(config) if _remote_pid(config) else 'not running'}")
        print(f"owner: {'paired (telegram user %s)' % owner['telegram_user_id'] if owner else 'NOT paired — run `agentctl remote pair`'}")
        print(f"offset: {store.get_meta('telegram_offset', '-')}  paused: {store.get_meta('scheduler_paused', '0') == '1'}")
        print(f"notifications due: {len(pending)}")
        return 0
    if sub == "pair":
        if getattr(args, "user_id", None):
            # Operator pairing at the terminal: the owner, working on this machine, names the numeric
            # Telegram user id seen on their own messages to the bot. Audited like a code pairing.
            store.set_owner(int(args.user_id), int(args.chat_id or args.user_id))
            store.record_event(None, "owner_paired_by_operator", {"telegram_user_id": int(args.user_id)})
            print(f"owner paired by operator: telegram user {args.user_id} (chat {args.chat_id or args.user_id})")
            return 0
        import secrets as _secrets
        code = f"{_secrets.randbelow(900000) + 100000}"
        store.create_pairing_code(code, config.pairing_ttl_seconds)
        print(f"Pairing code: {code}  (valid {config.pairing_ttl_seconds // 60} min, one-time)")
        print("In Telegram, the owner sends:  /pair " + code)
        return 0
    if sub == "unpair":
        store.clear_owner()
        print("owner unpaired; run `agentctl remote pair` to pair again")
        return 0
    if sub == "doctor":
        from agent_team.remote.transport import HttpTelegramTransport, TelegramError, resolve_token
        token = resolve_token(config.telegram_token_env, config.telegram_env_file)
        print(f"token: {'present (from env/file)' if token else 'MISSING'}  enabled: {config.telegram_enabled}  mode: {config.telegram_mode}")
        if token:
            try:
                me = HttpTelegramTransport(token).get_me()
                print(f"bot: @{me.get('username')} (id {me.get('id')})")
            except TelegramError as exc:
                print(f"bot: ERROR {exc}")
        owner = store.owner()
        print(f"owner: {'paired (user %s)' % owner['telegram_user_id'] if owner else 'not paired'}")
        print(f"service: {'running' if _remote_pid(config) else 'not running'}  interpreter: {config.interpreter_model}  transcription: {config.transcription_provider}")
        return 0
    return 1


# -- permanent services (macOS launchd user agents) -------------------------------------------

LAUNCHD_LABELS = {"orchestrator": "com.buildsmart.agent-team.orchestrator", "remote": "com.buildsmart.agent-team.remote"}


def launchd_plist(config: Config, which: str) -> str:
    """A launchd user agent that keeps the service alive across logins, crashes and reboots."""
    label = LAUNCHD_LABELS[which]
    logs = config.path(config.logs_dir)
    boot = f"import sys; sys.path.insert(0, {str(config.repo_root / 'scripts')!r}); from agent_team.cli import main; sys.exit(main())"
    argv = [sys.executable, "-c", boot] + (["run"] if which == "orchestrator" else ["remote", "run"])
    args_xml = "".join(f"\n      <string>{a.replace('&', '&amp;').replace('<', '&lt;')}</string>" for a in argv)
    path_env = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + os.path.dirname(sys.executable)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>{args_xml}
  </array>
  <key>WorkingDirectory</key><string>{config.repo_root}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>AGENT_TEAM_REPO_ROOT</key><string>{config.repo_root}</string>
    <key>PATH</key><string>{path_env}</string>
    <key>HOME</key><string>{os.path.expanduser('~')}</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>{logs / f'launchd-{which}.log'}</string>
  <key>StandardErrorPath</key><string>{logs / f'launchd-{which}.log'}</string>
</dict>
</plist>
"""


def _launchd_dir() -> Path:
    return Path(os.path.expanduser("~/Library/LaunchAgents"))


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def cmd_install(config: Config, args) -> int:
    """Install (or reinstall) the launchd user agents so both services are permanent."""
    if sys.platform != "darwin":
        print("launchd install is macOS-only; use a systemd unit on Linux", file=sys.stderr)
        return 2
    which = ["orchestrator", "remote"] if args.service == "all" else [args.service]
    config.path(config.logs_dir).mkdir(parents=True, exist_ok=True)
    _launchd_dir().mkdir(parents=True, exist_ok=True)
    uid = os.getuid()
    for w in which:
        # a manually started instance would fight the agent for the singleton lock: stop it first
        if w == "orchestrator" and _daemon_pid(config):
            cmd_stop(config, args)
        if w == "remote" and _remote_pid(config):
            cmd_remote(config, type("A", (), {"remote_cmd": "stop"})())
        plist = _launchd_dir() / f"{LAUNCHD_LABELS[w]}.plist"
        _launchctl("bootout", f"gui/{uid}/{LAUNCHD_LABELS[w]}")
        plist.write_text(launchd_plist(config, w), encoding="utf-8")
        res = _launchctl("bootstrap", f"gui/{uid}", str(plist))
        if res.returncode != 0:
            res = _launchctl("load", "-w", str(plist))
        ok = res.returncode == 0
        print(f"{w}: {'installed and started' if ok else 'INSTALL FAILED: ' + (res.stderr or res.stdout).strip()[:200]} — {plist}")
        StateStore(config.state_db_path).record_event(None, "service_installed", {"service": w, "plist": str(plist), "ok": ok})
    print("both services now start at login, restart on crash, and survive reboots" if args.service == "all" else "")
    return 0


def cmd_uninstall(config: Config, args) -> int:
    which = ["orchestrator", "remote"] if args.service == "all" else [args.service]
    uid = os.getuid()
    for w in which:
        plist = _launchd_dir() / f"{LAUNCHD_LABELS[w]}.plist"
        _launchctl("bootout", f"gui/{uid}/{LAUNCHD_LABELS[w]}")
        if plist.exists():
            plist.unlink()
        print(f"{w}: uninstalled ({plist})")
        StateStore(config.state_db_path).record_event(None, "service_uninstalled", {"service": w})
    return 0


def launchd_status(config: Config) -> dict[str, str]:
    out = {}
    uid = os.getuid()
    for w, label in LAUNCHD_LABELS.items():
        res = _launchctl("print", f"gui/{uid}/{label}")
        if res.returncode != 0:
            out[w] = "not installed"
        else:
            pid = next((l.split("=")[1].strip() for l in res.stdout.splitlines() if l.strip().startswith("pid =")), None)
            out[w] = f"installed, running (pid {pid})" if pid else "installed, not running"
    return out


# -- parser -----------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentctl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo-root", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status"); s.add_argument("--no-probe", action="store_true"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("run"); s.add_argument("--once", action="store_true"); s.add_argument("--dry-run", action="store_true")
    s.add_argument("--verbose", action="store_true"); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("dry-run"); s.add_argument("--verbose", action="store_true"); s.set_defaults(fn=cmd_dry_run)
    s = sub.add_parser("start"); s.add_argument("--verbose", action="store_true"); s.set_defaults(fn=cmd_start)
    s = sub.add_parser("stop"); s.set_defaults(fn=cmd_stop)
    s = sub.add_parser("labels"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_labels)
    s = sub.add_parser("protect-main"); s.add_argument("--enforce-admins", action="store_true"); s.add_argument("--show", action="store_true")
    s.set_defaults(fn=cmd_protect_main)

    s = sub.add_parser("issue"); isub = s.add_subparsers(dest="issue_cmd", required=True)
    v = isub.add_parser("validate"); v.add_argument("number", type=int); v.add_argument("--json", action="store_true")
    q = isub.add_parser("queue"); q.add_argument("number", type=int)
    c = isub.add_parser("create"); c.add_argument("--from", dest="from_file", required=True); c.add_argument("--title"); c.add_argument("--queue", action="store_true")
    r = isub.add_parser("render"); r.add_argument("--from", dest="from_file", required=True); r.add_argument("--title")
    s.set_defaults(fn=cmd_issue)

    s = sub.add_parser("approve"); s.add_argument("number", type=int)
    s.add_argument("--kind", choices=["lost_allowance"], default="lost_allowance",
                   help="the only Team Lead acknowledgement left: a declared LOST allowance (merge itself is the owner's)")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("requeue"); s.add_argument("number", type=int); s.add_argument("--reason"); s.add_argument("--reset-attempts", action="store_true")
    s.set_defaults(fn=cmd_requeue)
    s = sub.add_parser("resume-pr"); s.add_argument("number", type=int); s.add_argument("--update-base", action="store_true")
    s.add_argument("--rereview", action="store_true"); s.add_argument("--reason")
    s.set_defaults(fn=cmd_resume_pr)
    s = sub.add_parser("block"); s.add_argument("number", type=int); s.add_argument("--reason", required=True); s.set_defaults(fn=cmd_block)
    s = sub.add_parser("audit"); s.add_argument("number", type=int); s.add_argument("--limit", type=int, default=200); s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("investigate"); s.add_argument("--domain", required=True); s.add_argument("question"); s.set_defaults(fn=cmd_investigate)
    s = sub.add_parser("reconcile"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_reconcile)
    s = sub.add_parser("doctor"); s.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("pause"); s.add_argument("--reason"); s.set_defaults(fn=cmd_pause)
    s = sub.add_parser("resume"); s.add_argument("--reason"); s.set_defaults(fn=cmd_resume)
    s = sub.add_parser("remote"); rsub = s.add_subparsers(dest="remote_cmd", required=True)
    for name in ("start", "stop", "status", "unpair", "doctor"):
        rsub.add_parser(name)
    pr_ = rsub.add_parser("pair"); pr_.add_argument("--user-id", type=int, help="operator pairing: the owner's numeric Telegram user id")
    pr_.add_argument("--chat-id", type=int)
    s = sub.add_parser("install"); s.add_argument("service", nargs="?", choices=["all", "orchestrator", "remote"], default="all"); s.set_defaults(fn=cmd_install)
    s = sub.add_parser("uninstall"); s.add_argument("service", nargs="?", choices=["all", "orchestrator", "remote"], default="all"); s.set_defaults(fn=cmd_uninstall)
    r = rsub.add_parser("run"); r.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_remote)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(repo_root=Path(args.repo_root).resolve() if args.repo_root else None)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    return args.fn(config, args)


if __name__ == "__main__":
    sys.exit(main())
