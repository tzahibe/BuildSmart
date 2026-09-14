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
from app.projects.models import Project, SourceTag, TaggedBool, TaggedInt, WetRoomKindRecord
from app.projects.preferences import PreferenceCreate, PreferenceUpdate
from app.projects.update import ProjectUpdateDiff

_FIELD_LABELS_HE = {
    "floors": 'מספר קומות',
    "bedrooms": "מספר חדרי שינה",
    "safe_room": 'ממ"ד',
    "parking_spaces": "מספר חניות",
    "wet_rooms": "מספר חדרי רחצה",
}

#: Wet-room kind (and host) -> the words the review screen uses for it.
_WET_ROOM_WORDS_HE = {
    ("shared_bathroom", None): "חדר רחצה משותף",
    ("ensuite", "MASTER_BEDROOM"): "חדר רחצה צמוד לחדר ההורים",
    ("ensuite", "BEDROOM"): "חדר רחצה צמוד לחדר שינה",
    ("guest_wc", None): "שירותי אורחים",
    ("unspecified", None): "לא צוין",
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


def _wet_room_words(record: WetRoomKindRecord) -> str:
    host = record.host if record.kind == "ensuite" else None
    word = _WET_ROOM_WORDS_HE.get((record.kind, host), record.kind)
    return f"{word} (גמיש)" if record.strength == "flexible" else word


def _build_wet_room_kind_update(project: Project, extraction: ChatIntentExtraction) -> ProposalBuildResult:
    """One wet room's kind or flexibility -> a proposal replacing the WHOLE list (specs/007 FR-4).

    The list the person confirms is the list that gets stored, row by row, so the summary shows
    every row — not just the one that moves. Rows beyond what the brief described are shown as
    "לא צוין" and are the count's unstated rooms; changing one of them is how a person states it.
    """
    intent = extraction.wet_room_kind
    count = project.wet_rooms.value if project.wet_rooms is not None else None
    if intent is None or intent.index is None or count is None:
        return ProposalBuildResult(None, "לא הצלחתי להבין לאיזה חדר רחצה הכוונה. אפשר לציין את מספרו?")
    if not 1 <= intent.index <= count:
        return ProposalBuildResult(None, f"יש {count} חדרי רחצה בפרויקט; אין חדר רחצה מספר {intent.index}.")
    if intent.kind is None and intent.strength is None and intent.host is None:
        return ProposalBuildResult(None, "לא הבנתי מה לשנות בחדר הרחצה הזה. אפשר לנסח מחדש?")

    rows = list(project.wet_room_kinds) + [WetRoomKindRecord()] * (count - len(project.wet_room_kinds))
    current = rows[intent.index - 1]
    kind = intent.kind if intent.kind is not None else current.kind
    host = intent.host if intent.host is not None else current.host
    if kind == "ensuite":
        host = host or "MASTER_BEDROOM"
    else:
        host = None
    strength = intent.strength if intent.strength is not None else current.strength
    if strength == "flexible" and kind not in ("shared_bathroom", "unspecified"):
        return ProposalBuildResult(
            None, f"{_WET_ROOM_WORDS_HE[(kind, host)]} אינו יכול להיות גמיש — רק חדר רחצה משותף יכול "
                  f"להיות צמוד לחדר שינה לפי שיקול המתכנן.")
    new_row = WetRoomKindRecord(kind=kind, host=host, strength=strength, source_text=current.source_text,
                                source=SourceTag.requested if kind != "unspecified" else SourceTag.unknown)
    if new_row.model_dump() == current.model_dump():
        return ProposalBuildResult(None, f"חדר רחצה {intent.index} כבר מוגדר כך — אין צורך בשינוי.")
    rows[intent.index - 1] = new_row

    summary = (f"חדר רחצה {intent.index}: {_wet_room_words(current)} ← {_wet_room_words(new_row)}. "
               f"חדרי הרחצה יהיו: " + "; ".join(f"{i}. {_wet_room_words(r)}" for i, r in enumerate(rows, start=1)))
    return ProposalBuildResult(
        Proposal(
            proposal_id=str(uuid.uuid4()),
            project_id=project.project_id,
            action=ProposalActionType.update_wet_room_kind,
            diff=ProjectUpdateDiff(wet_room_kinds=rows),
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
    if extraction.action == ProposalActionType.update_wet_room_kind:
        return _build_wet_room_kind_update(project, extraction)
    if extraction.action == ProposalActionType.add_preference:
        return _build_add_preference(project, extraction)
    if extraction.action == ProposalActionType.update_preference:
        return _build_update_preference(project, extraction)
    if extraction.action == ProposalActionType.remove_preference:
        return _build_remove_preference(project, extraction)
    if extraction.action == ProposalActionType.rollback_design_version:
        return _build_rollback(project, design_versions, extraction)
    return ProposalBuildResult(None, "")  # NO_ACTION — caller falls back to the plain assistant reply
