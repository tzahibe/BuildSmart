import pytest
from fastapi.testclient import TestClient

# `app.main` must be imported before any module that constructs an OpenAI-backed singleton at import
# time (e.g. app.chat.router's `assistant: ChatAssistant = OpenAIChatAssistant()`) — it's the one that
# calls load_dotenv(), same ordering requirement as backend/tests/test_requirements.py.
from app.main import app
from app.chat import router as chat_router
from app.chat.assistant import ChatAssistant
from app.chat.models import ChatMessage
from app.chat.repository import JsonFileConversationRepository
from app.projects.models import Project
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes


class FakeChatAssistant(ChatAssistant):
    """Deterministic test double — no real OpenAI calls (matching FakeRequirementParser's
    hermeticity convention, see backend/tests/test_requirements.py)."""

    def __init__(self, *, reply_text: str = "תשובה לדוגמה", should_fail: bool = False):
        self.reply_text = reply_text
        self.should_fail = should_fail
        self.calls: list[tuple[Project, list[ChatMessage], str]] = []

    def reply(self, project: Project, history: list[ChatMessage], new_message: str) -> str:
        self.calls.append((project, history, new_message))
        if self.should_fail:
            raise RuntimeError("simulated assistant failure")
        return self.reply_text


PROJECT_PAYLOAD = {
    "city": "מודיעין-מכבים-רעות",
    "street": "אגוז מכבים רעות",
    "plot_area_m2": 500,
    "built_area_m2": 150,
    "description": "בית עם 3 חדרי שינה",
}


@pytest.fixture
def project_repo(tmp_path):
    return JsonFileProjectRepository(tmp_path / "projects.json")


@pytest.fixture
def conversation_repo(tmp_path):
    return JsonFileConversationRepository(tmp_path / "conversations.json")


@pytest.fixture
def fake_assistant():
    return FakeChatAssistant()


@pytest.fixture
def client(project_repo, conversation_repo, fake_assistant, monkeypatch):
    monkeypatch.setattr(project_base_routes, "repository", project_repo)
    monkeypatch.setattr(chat_router, "repository", conversation_repo)
    monkeypatch.setattr(chat_router, "assistant", fake_assistant)
    return TestClient(app)


def _create_project(client: TestClient) -> str:
    response = client.post("/projects", json=PROJECT_PAYLOAD)
    assert response.status_code == 201
    return response.json()["project_id"]


def test_new_project_has_empty_conversation(client: TestClient):
    project_id = _create_project(client)

    response = client.get(f"/projects/{project_id}/chat")

    assert response.status_code == 200
    assert response.json() == {"project_id": project_id, "messages": []}


def test_send_message_appends_user_and_assistant_messages(client: TestClient, fake_assistant):
    project_id = _create_project(client)

    response = client.post(f"/projects/{project_id}/chat/messages", json={"content": "כמה חדרי שינה יש?"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "כמה חדרי שינה יש?"
    assert body["messages"][1]["role"] == "assistant"
    assert body["messages"][1]["content"] == fake_assistant.reply_text
    # The assistant is grounded in the actual project record, not just the raw message.
    assert fake_assistant.calls[0][0].project_id == project_id


def test_conversation_persists_across_requests(client: TestClient):
    project_id = _create_project(client)
    client.post(f"/projects/{project_id}/chat/messages", json={"content": "שלום"})

    response = client.get(f"/projects/{project_id}/chat")

    assert response.status_code == 200
    assert len(response.json()["messages"]) == 2


def test_second_message_includes_prior_history_in_the_assistant_call(client: TestClient, fake_assistant):
    project_id = _create_project(client)
    client.post(f"/projects/{project_id}/chat/messages", json={"content": "הודעה ראשונה"})

    client.post(f"/projects/{project_id}/chat/messages", json={"content": "הודעה שנייה"})

    second_call_history = fake_assistant.calls[1][1]
    assert len(second_call_history) == 2
    assert second_call_history[0].content == "הודעה ראשונה"


def test_get_chat_nonexistent_project_returns_404(client: TestClient):
    response = client.get("/projects/00000000-0000-0000-0000-000000000000/chat")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_post_chat_nonexistent_project_returns_404(client: TestClient):
    response = client.post(
        "/projects/00000000-0000-0000-0000-000000000000/chat/messages", json={"content": "שלום"}
    )

    assert response.status_code == 404


def test_empty_content_returns_422(client: TestClient):
    project_id = _create_project(client)

    response = client.post(f"/projects/{project_id}/chat/messages", json={"content": "   "})

    assert response.status_code == 422


def test_assistant_failure_returns_502_and_persists_nothing(client: TestClient, fake_assistant):
    project_id = _create_project(client)
    fake_assistant.should_fail = True

    response = client.post(f"/projects/{project_id}/chat/messages", json={"content": "שלום"})

    assert response.status_code == 502
    conversation = client.get(f"/projects/{project_id}/chat").json()
    assert conversation["messages"] == []
