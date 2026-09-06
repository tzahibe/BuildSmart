"""Turns a `ChatIntentExtraction` (app/chat/intent.py) into either a concrete `Proposal`
(app/chat/proposals.py) ready to store and show the user, or a plain-language explanation of why it
couldn't (an unresolvable field/value, an ambiguous or unmatched preference reference, an out-of-range
rollback target). Nothing here mutates `Project` — see app/chat/router.py for the confirm step, which is
the only place `apply_project_update`/`rollback_to_design_version` are ever called from chat.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.chat.intent import ChatIntentExtraction, ProposalActionType
from app.chat.proposals import Proposal
from app.design.version import DesignVersion
from app.projects.models import Project, TaggedBool, TaggedInt
from app.projects.preferences import PreferenceCreate, PreferenceUpdate
from app.projects.update import ProjectUpdateDiff

_FIELD_LABELS_HE = {
    "floors": 'מספר קומות',
    "bedrooms": "מספר חדרי שינה",
    "safe_room": 'ממ"ד',
    "parking_spaces": "מספר חניות",
}

# Only CHAT/SETTINGS preferences exist today (no Regulation Engine yet — see app/projects/preferences.py
# PreferenceSource), so this can never actually trigger yet. Kept as a forward-compatible guard per this
# milestone's brief ("regulation/system constraints cannot be removed by chat") so nothing here needs to
# change again once a future Regulation Engine can produce a REGULATION-sourced preference/requirement.
_CHAT_REMOVABLE_SOURCES = ("CHAT", "SETTINGS")


@dataclass
class ProposalBuildResult:
    proposal: Proposal | None
    message: str  # the proposal's own summary (success) OR a rejection explanation (failure)


def _format_value_he(tagged_dict: dict) -> str:
    if tagged_dict["source"] == "unknown" or tagged_dict["value"] is None:
        return "לא ידוע"
    if isinstance(tagged_dict["value"], bool):
        return "כן" if tagged_dict["value"] else "לא"
    return str(tagged_dict["value"])


def _build_field_update(project: Project, extraction: ChatIntentExtraction) -> ProposalBuildResult:
    update = extraction.field_update
    if update is None or update.field is None:
        return ProposalBuildResult(None, "לא הצלחתי להבין איזו דרישה ברצונך לשנות. אפשר לנסח מחדש?")

    field = update.field
    if update.mark_unknown:
        new_tagged = TaggedBool(value=None, source="unknown") if field == "safe_room" else TaggedInt(value=None, source="unknown")
    elif field == "safe_room":
        if update.bool_value is None:
            return ProposalBuildResult(None, 'לא הבנתי אם ברצונך שיהיה ממ"ד או לא. אפשר לנסח מחדש?')
        new_tagged = TaggedBool(value=update.bool_value, source="requested")
    else:
        if update.int_value is None:
            return ProposalBuildResult(None, f"לא הבנתי לאיזה ערך לשנות את {_FIELD_LABELS_HE[field]}. אפשר לנסח מחדש?")
        if update.int_value < 0:
            return ProposalBuildResult(None, f"{_FIELD_LABELS_HE[field]} לא יכול להיות מספר שלילי.")
        new_tagged = TaggedInt(value=update.int_value, source="requested")

    existing = getattr(project, field)
    if existing is not None and existing.model_dump() == new_tagged.model_dump():
        return ProposalBuildResult(None, f"{_FIELD_LABELS_HE[field]} כבר מוגדר כך — אין צורך בשינוי.")

    diff = ProjectUpdateDiff(**{field: new_tagged})
    old_label = _format_value_he(existing.model_dump()) if existing is not None else "לא ידוע"
    new_label = _format_value_he(new_tagged.model_dump())
    summary = f"{_FIELD_LABELS_HE[field]}: {old_label} ← {new_label}"

    return ProposalBuildResult(
        Proposal(
            proposal_id=str(uuid.uuid4()),
            project_id=project.project_id,
            action=ProposalActionType.update_project_fields,
            diff=diff,
            summary=summary,
            created_at=datetime.now(),
        ),
        summary,
    )


def _build_add_preference(project: Project, extraction: ChatIntentExtraction) -> ProposalBuildResult:
    preference = extraction.preference
    if preference is None or preference.kind is None or not preference.original_text:
        return ProposalBuildResult(None, "לא הצלחתי להבין את ההעדפה שברצונך להוסיף. אפשר לנסח מחדש?")

    diff = ProjectUpdateDiff(
        add_preferences=[
            PreferenceCreate(
                kind=preference.kind,
                target=preference.target,
                related_target=preference.related_target,
                original_text=preference.original_text,
            )
        ]
    )
    summary = f'העדפה חדשה: "{preference.original_text}"'
    return ProposalBuildResult(
        Proposal(
            proposal_id=str(uuid.uuid4()),
            project_id=project.project_id,
            action=ProposalActionType.add_preference,
            diff=diff,
            summary=summary,
            created_at=datetime.now(),
        ),
        summary,
    )


def _resolve_existing_preference(project: Project, text: str | None):
    if not text:
        return None, "not_specified"
    normalized = text.strip().lower()
    matches = [p for p in project.preferences if p.original_text.strip().lower() == normalized]
    if len(matches) == 1:
        return matches[0], "ok"
    if len(matches) == 0:
        return None, "not_found"
    return None, "ambiguous"


def _build_update_preference(project: Project, extraction: ChatIntentExtraction) -> ProposalBuildResult:
    preference = extraction.preference
    match, status = _resolve_existing_preference(project, preference.existing_preference_text if preference else None)
    if status != "ok":
        return ProposalBuildResult(None, "לא מצאתי העדפה קיימת שמתאימה למה שביקשת לשנות. אפשר לציין אותה במדויק יותר?")

    fields: dict = {}
    if preference.kind is not None:
        fields["kind"] = preference.kind
    if preference.original_text:
        fields["original_text"] = preference.original_text
    if not fields:
        return ProposalBuildResult(None, "לא הבנתי מה בדיוק לשנות בהעדפה. אפשר לנסח מחדש?")

    diff = ProjectUpdateDiff(update_preferences=[PreferenceUpdate(preference_id=match.preference_id, **fields)])
    new_text = fields.get("original_text", match.original_text)
    summary = f'עדכון העדפה: "{match.original_text}" ← "{new_text}"'
    return ProposalBuildResult(
        Proposal(
            proposal_id=str(uuid.uuid4()),
            project_id=project.project_id,
            action=ProposalActionType.update_preference,
            diff=diff,
            summary=summary,
            created_at=datetime.now(),
        ),
        summary,
    )


def _build_remove_preference(project: Project, extraction: ChatIntentExtraction) -> ProposalBuildResult:
    preference = extraction.preference
    match, status = _resolve_existing_preference(project, preference.existing_preference_text if preference else None)
    if status != "ok":
        return ProposalBuildResult(None, "לא מצאתי העדפה קיימת שמתאימה למה שביקשת להסיר. אפשר לציין אותה במדויק יותר?")

    if match.source not in _CHAT_REMOVABLE_SOURCES:
        return ProposalBuildResult(None, "לא ניתן להסיר דרישה שמקורה ברגולציה או במערכת דרך הצ'אט.")

    diff = ProjectUpdateDiff(remove_preference_ids=[match.preference_id])
    summary = f'הסרת העדפה: "{match.original_text}"'
    return ProposalBuildResult(
        Proposal(
            proposal_id=str(uuid.uuid4()),
            project_id=project.project_id,
            action=ProposalActionType.remove_preference,
            diff=diff,
            summary=summary,
            created_at=datetime.now(),
        ),
        summary,
    )


def _build_rollback(project: Project, design_versions: list[DesignVersion], extraction: ChatIntentExtraction) -> ProposalBuildResult:
    ordinal = extraction.rollback.target_version_ordinal if extraction.rollback else None
    if ordinal is None or ordinal < 1 or ordinal > len(design_versions):
        return ProposalBuildResult(None, "לא מצאתי גרסת עיצוב כזו. אפשר לציין מספר גרסה קיים?")

    target = design_versions[ordinal - 1]
    if target.design_version_id == project.active_design_version_id:
        return ProposalBuildResult(None, "זו כבר הגרסה הנוכחית.")

    summary = f"חזרה לגרסת עיצוב מס' {ordinal} (מתאריך {target.created_at.strftime('%d/%m/%Y %H:%M')})"
    return ProposalBuildResult(
        Proposal(
            proposal_id=str(uuid.uuid4()),
            project_id=project.project_id,
            action=ProposalActionType.rollback_design_version,
            rollback_design_version_id=target.design_version_id,
            rollback_ordinal=ordinal,
            summary=summary,
            created_at=datetime.now(),
        ),
        summary,
    )


def build_proposal(
    project: Project, design_versions: list[DesignVersion], extraction: ChatIntentExtraction
) -> ProposalBuildResult:
    if extraction.action == ProposalActionType.update_project_fields:
        return _build_field_update(project, extraction)
    if extraction.action == ProposalActionType.add_preference:
        return _build_add_preference(project, extraction)
    if extraction.action == ProposalActionType.update_preference:
        return _build_update_preference(project, extraction)
    if extraction.action == ProposalActionType.remove_preference:
        return _build_remove_preference(project, extraction)
    if extraction.action == ProposalActionType.rollback_design_version:
        return _build_rollback(project, design_versions, extraction)
    return ProposalBuildResult(None, "")  # NO_ACTION — caller falls back to the plain assistant reply
