# Agent Team — Issue Title Convention

This is a short pointer page. The canonical page for the Agent Team workflow is
[architecture/agent-team-workflow.md](architecture/agent-team-workflow.md) — read that first.

## Title convention

Every agent Issue's title carries its own number right after the `[agent]` prefix:
`[agent] #N Title`. The number is then visible in every GitHub list, Telegram status line and
notification without opening the Issue. This is cosmetic only: `slugify()` ignores both the
`[agent]` prefix and a leading `#N`, so branch/worktree slugs are unaffected.

- `agentctl issue create --from f.md --queue` retitles the new Issue with its own number as soon
  as `create_issue` returns it.
- `agentctl issue renumber-titles [--dry-run] [--all-states]` is the idempotent one-off pass over
  already-open Issues carrying an `agent:*` label: it adds a missing number or replaces a stale
  one, and running it twice makes no further changes. `--dry-run` prints the planned
  `old -> new` pairs without changing anything; `--all-states` also covers closed Issues.

See `architecture/agent-team-workflow.md`'s "The Issue contract" and "Operating it" sections for
the full mechanism and implementation (`issue_contract.numbered_title`/`strip_title_number`,
`GitHubClient.update_issue`). Issue #25.

## Last verified against git

Branch `agent/25-issue-titles-carry-their-own-number-agen`.
