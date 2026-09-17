"""Autonomous engineering workflow — orchestration package.

Everything here is infrastructure around the product, never product behavior. The entry point is
`scripts/agentctl` (a thin wrapper that runs `agent_team.cli` inside this directory's own uv
environment). See docs/wiki/architecture/agent-team-workflow.md for the architecture.
"""
