"""Builds the assistant's reply AFTER a proposal is confirmed and actually applied — deterministically,
from the real `ProjectUpdateResult` (or the rolled-back `Project`), never from a second LLM call. This is
what makes "describe what actually changed, not what it intended" a guarantee rather than a hope: an LLM
asked to summarize its own prior intent could drift from what really happened; reading the literal result
object cannot.
"""

from app.chat.proposals import Proposal
from app.projects.models import Project
from app.projects.update import ProjectUpdateResult


def describe_update_result(proposal: Proposal, result: ProjectUpdateResult) -> str:
    lines = [f"בוצע: {proposal.summary}"]

    if result.design_error is not None:
        lines.append(
            f"השינוי נשמר, אך לא ניתן היה ליצור עיצוב חדש כרגע ({result.design_error.code}). "
            f"אפשר לנסות שוב מאוחר יותר מדף העיצוב."
        )
    elif result.design_version is not None:
        room_types = sorted({room.type for room in (result.project.rooms or [])})
        lines.append(f"נוצרה גרסת עיצוב חדשה. הפריסה הנוכחית כוללת: {', '.join(room_types)}.")

    return "\n".join(lines)


def describe_rollback_result(proposal: Proposal, project: Project) -> str:
    room_types = sorted({room.type for room in (project.rooms or [])})
    rooms_text = ", ".join(room_types) if room_types else "אין חדרים"
    return f"{proposal.summary}. בוצע. הפריסה הנוכחית כוללת: {rooms_text}."
