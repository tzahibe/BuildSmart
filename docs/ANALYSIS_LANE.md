# The ANALYSIS lane — installation and operation

A read-only task class inside the existing orchestrator: an Issue labelled `claude-task` by a
trusted author gets **one comment** containing a read-only analysis, and nothing else.

It is **off by default**. An orchestrator that does not opt in behaves exactly as it does today.

## What it can and cannot do

| | |
|---|---|
| tools | `Read`, `Grep`, `Glob` — nothing else is reachable |
| working directory | a **detached** throwaway worktree, removed afterwards |
| writes | one Issue comment + the `agent:analyzed` label |
| never | branch, commit, push, PR, merge, Bash, WebFetch, network, writes to the checkout |
| contract | **none required** — this is why the lane exists |
| trust | the Issue's `author_association` must be in `github.executable_author_associations` |
| untrusted input | the Issue body is fenced and the system prompt names it as data, not instructions |

## Enable it

```yaml
# .agent/config.yaml
analysis:
  enabled: true        # default false
  max_per_tick: 2      # how many analyses may START per tick
```

Then restart the orchestrator (`agentctl stop --wait` then launchd restarts it, or
`launchctl kickstart -k gui/$(id -u)/com.buildsmart.agent-team.orchestrator`).

## Use it

1. Open an Issue, write the question in the body.
2. Add the label `claude-task`.
3. Within one poll interval (120 s) the orchestrator starts a read-only analysis.
4. The answer arrives as a comment; the Issue gets `agent:analyzed`.

**To re-run**: remove `agent:analyzed`, delete the previous analysis comment (it carries the marker
`<!-- agent-team:analysis -->`), and re-add `claude-task`. All three layers must be cleared —
that is deliberate, so a duplicated webhook or a restart cannot produce a second answer.

## Pin the Claude binary (recommended)

`claude` is on no PATH on this machine; the only copies live inside versioned VS Code extension
directories, so resolution silently depends on the editor's upgrade behaviour. Pin it:

```xml
<!-- ~/Library/LaunchAgents/com.buildsmart.agent-team.orchestrator.plist -->
<key>CLAUDE_BIN</key><string>/absolute/path/to/claude</string>
```

Verify, in the environment that matters:

```bash
agentctl doctor          # from a terminal
```

`doctor` prints the PATH it saw, whether `CLAUDE_BIN` is set, how many extension copies exist, the
resolved binary and its version, and warns when resolution is **not** pinned. Run it under launchd
too (a temporary LaunchAgent running `doctor`) — a terminal and a LaunchAgent have different PATHs,
so "it works when I run it" proves nothing about the service.

## Keep the machine awake while work runs (optional)

```yaml
power:
  caffeinate_while_working: true   # default false
```

Holds a `caffeinate -i` assertion **only** while at least one agent thread is alive, released when
the last one finishes. `pmset` is never invoked and no system preference is written. The child is
started with `-w <orchestrator pid>`, so a crash cannot leave the machine awake.

## Operational notes

- Analysis runs are gated by the same controls as everything else: `agentctl pause`, the drain on
  SIGTERM, and the usage guard.
- They hold no domain locks and consume no Issue slot, so they can neither block nor be blocked by
  engineering work — but they will not start if every worker slot is already busy.
- Each run is recorded under `.agent/logs/runs/` like any other agent run, and as an
  `analysis_published` / `analysis_complete` event in the state store.
