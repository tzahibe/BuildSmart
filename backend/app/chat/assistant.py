import os
from abc import ABC, abstractmethod

from openai import OpenAI

from app.chat.models import ChatMessage, ChatRole
from app.projects.models import Project, SourceTag

_SYSTEM_PROMPT_HEADER = """\
את/ה עוזר/ת AI של BuildSmart, מלווה משתמש בתכנון ראשוני של בית מגורים בישראל. ענה/י בעברית, בקצרה \
ובאופן ידידותי, והתבסס/י רק על הנתונים שסופקו לך למטה עבור הפרויקט הזה — אל תמציא/י פרטים שלא נמסרו.

חשוב: אין לך יכולת לשנות בפועל את הדרישות השמורות של הפרויקט — אתה יכול לדון בהן ולהציע שינויים, אך \
המשתמש צריך לבצע כל שינוי בעצמו דרך טופס עריכת הפרויקט. ציין/ני זאת אם המשתמש מבקש ממך לשנות משהו \
בפועל.
"""


def _describe_tagged(label: str, value, unit: str = "") -> str:
    if value is None or value.source == SourceTag.unknown:
        return f"{label}: לא ידוע"
    return f"{label}: {value.value}{unit} (מקור: {value.source.value})"


def _build_project_context(project: Project) -> str:
    lines = [
        f"עיר: {project.city}",
        f"רחוב: {project.street}",
        f"שטח מגרש: {project.plot_area_m2} מ\"ר",
        f"שטח בנייה: {project.built_area_m2} מ\"ר",
        f"תיאור מקורי שסיפק המשתמש: {project.description}",
    ]

    if project.requirements_parsed_at is not None:
        lines.append("--- דרישות שחולצו מהתיאור ---")
        lines.append(_describe_tagged("מספר קומות", project.floors))
        lines.append(_describe_tagged("מספר חדרי שינה", project.bedrooms))
        lines.append(_describe_tagged("ממ\"ד", project.safe_room))
        lines.append(_describe_tagged("מספר חניות", project.parking_spaces))
        if project.pool is not None:
            lines.append(_describe_tagged("בריכה", project.pool.requested))
    else:
        lines.append("הדרישות המפורטות עדיין לא חולצו מהתיאור.")

    if project.design_generated_at is not None and project.rooms is not None:
        lines.append("--- מודל תכנון שנוצר ---")
        lines.append(f"מידות המגרש: {project.site_width_m:.1f} x {project.site_depth_m:.1f} מ'")
        floors = sorted({room.floor for room in project.rooms})
        for floor in floors:
            room_types = [room.type for room in project.rooms if room.floor == floor]
            lines.append(f"קומה {floor}: {', '.join(room_types)}")
        if project.design_notes:
            lines.append("הערות תכנון: " + "; ".join(project.design_notes))
    else:
        lines.append("עדיין לא נוצר מודל תכנון עבור הפרויקט.")

    return "\n".join(lines)


class ChatAssistant(ABC):
    @abstractmethod
    def reply(self, project: Project, history: list[ChatMessage], new_message: str) -> str: ...


class OpenAIChatAssistant(ChatAssistant):
    """Replies via OpenAI's gpt-5-nano (same model/client pattern as
    app.requirements.parser.OpenAIRequirementParser) grounded in the project's current data — see
    specs/004-design-viewer-chat/research.md §3. Never calls a tool and cannot mutate the stored
    Project (plan.md's Design decisions)."""

    def __init__(self, model: str = "gpt-5-nano") -> None:
        self._model = model
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def reply(self, project: Project, history: list[ChatMessage], new_message: str) -> str:
        system_prompt = _SYSTEM_PROMPT_HEADER + "\n--- נתוני הפרויקט ---\n" + _build_project_context(project)

        messages = [{"role": "system", "content": system_prompt}]
        for message in history:
            role = "user" if message.role == ChatRole.user else "assistant"
            messages.append({"role": role, "content": message.content})
        messages.append({"role": "user", "content": new_message})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        content = response.choices[0].message.content
        assert content is not None
        return content
