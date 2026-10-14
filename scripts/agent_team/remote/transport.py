"""Telegram Bot API transport. V1 = long polling from the orchestrator machine (no inbound port).

The token is read from the environment (`remote_control.telegram.token_env`), optionally loaded
from a chmod-600 env file so it never lives in a shell profile. It is never logged: the audit
redactor knows the Telegram token shape.
"""
from __future__ import annotations

import json
import uuid
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from agent_team import agent_runner

TELEGRAM_TOKEN_PATTERN = re.compile(r"\d{6,12}:[A-Za-z0-9_\-]{30,}")   # bot<id>:<secret>, also inside URLs
if TELEGRAM_TOKEN_PATTERN not in agent_runner._SECRET_PATTERNS:
    agent_runner._SECRET_PATTERNS.insert(0, TELEGRAM_TOKEN_PATTERN)


class TelegramError(RuntimeError):
    pass


def load_env_file(path: str | None) -> dict[str, str]:
    """KEY=VALUE lines -> dict. Missing file -> {}. Values are never printed by any caller."""
    if not path:
        return {}
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_token(token_env: str, env_file: str | None) -> str | None:
    tok = os.environ.get(token_env)
    if tok:
        return tok
    return load_env_file(env_file).get(token_env)


class TelegramTransport(Protocol):
    def get_updates(self, offset: int | None, timeout: int) -> list[dict]: ...
    def send_message(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> dict: ...
    def answer_callback(self, callback_id: str, text: str = "") -> None: ...
    def send_chat_action(self, chat_id: int, action: str = "typing") -> None: ...
    def edit_buttons(self, chat_id: int, message_id: int, buttons: list[list[dict]] | None) -> None: ...
    def send_photo(self, chat_id: int, image: bytes, caption: str = "", filename: str = "plan.png") -> dict: ...
    def get_file(self, file_id: str) -> bytes: ...
    def get_me(self) -> dict: ...


def _keyboard(buttons: list[list[dict]] | None) -> dict | None:
    if not buttons:
        return None
    return {"inline_keyboard": [[{"text": b["text"], "callback_data": b["data"][:64]} for b in row] for row in buttons]}


class HttpTelegramTransport:
    def __init__(self, token: str, *, api_base: str = "https://api.telegram.org"):
        if not token:
            raise TelegramError("no Telegram bot token")
        self._base = f"{api_base}/bot{token}/"
        self._file_base = f"{api_base}/file/bot{token}/"

    def _call(self, method: str, http_timeout: int = 60, **params: Any) -> Any:
        data = None
        if params:
            data = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
        req = urllib.request.Request(self._base + method, data=data, method="POST" if data else "GET")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=http_timeout) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise TelegramError(f"{method} -> HTTP {exc.code}: {agent_runner.redact(body)}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramError(f"{method} failed: {agent_runner.redact(str(exc))[:200]}") from exc
        if not payload.get("ok"):
            raise TelegramError(f"{method}: {agent_runner.redact(str(payload.get('description')))[:200]}")
        return payload["result"]

    def get_updates(self, offset: int | None, timeout: int) -> list[dict]:
        params: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", timeout + 30, **params)

    def send_message(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> dict:
        chunks = _chunks(text, 3900)
        result: dict = {}
        for i, chunk in enumerate(chunks):
            result = self._call("sendMessage", chat_id=chat_id, text=chunk, disable_web_page_preview=True,
                                reply_markup=_keyboard(buttons) if i == len(chunks) - 1 else None)
        return result

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._call("answerCallbackQuery", callback_query_id=callback_id, text=text[:190] or None)
        except TelegramError:
            pass  # the button reply is best-effort; the real answer is the message that follows

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            self._call("sendChatAction", 15, chat_id=chat_id, action=action)
        except TelegramError:
            pass

    def edit_buttons(self, chat_id: int, message_id: int, buttons: list[list[dict]] | None) -> None:
        try:
            self._call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                       reply_markup=_keyboard(buttons) or {"inline_keyboard": []})
        except TelegramError:
            pass

    def send_photo(self, chat_id: int, image: bytes, caption: str = "", filename: str = "plan.png") -> dict:
        """sendPhoto as multipart/form-data (the owner asked for plan IMAGES on Telegram, 2026-09-22).
        Caption ≤ 1024 chars per Telegram; longer text goes in a separate message."""
        boundary = "----agentteam" + uuid.uuid4().hex
        def field(name: str, value: str) -> bytes:
            return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
        body = field("chat_id", str(chat_id))
        if caption:
            body += field("caption", caption[:1024])
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: image/png\r\n\r\n").encode() + image + b"\r\n" + f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(self._base + "sendPhoto", data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            raise TelegramError(f"sendPhoto -> HTTP {exc.code}: {agent_runner.redact(exc.read().decode('utf-8', 'replace')[:300])}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramError(f"sendPhoto failed: {agent_runner.redact(str(exc))[:200]}") from exc
        if not payload.get("ok"):
            raise TelegramError(f"sendPhoto: {agent_runner.redact(str(payload.get('description')))[:200]}")
        return payload["result"]

    def get_file(self, file_id: str) -> bytes:
        info = self._call("getFile", file_id=file_id)
        path = info.get("file_path")
        if not path:
            raise TelegramError("getFile returned no path")
        with urllib.request.urlopen(self._file_base + path, timeout=60) as resp:
            return resp.read()

    def get_me(self) -> dict:
        return self._call("getMe")


def _chunks(text: str, n: int) -> list[str]:
    if len(text) <= n:
        return [text]
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > n and cur:
            out.append(cur)
            cur = ""
        cur += line
    if cur:
        out.append(cur)
    return out


@dataclass
class FakeTelegramTransport:
    """In-memory transport for tests: queue updates, capture everything sent."""
    incoming: list[dict] = field(default_factory=list)
    sent: list[dict] = field(default_factory=list)
    callbacks_answered: list[tuple[str, str]] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)
    fail_sends: int = 0                  # number of send_message calls to fail (for retry tests)
    next_message_id: int = 1000
    me: dict = field(default_factory=lambda: {"id": 1, "username": "test_bot"})

    def push_message(self, update_id: int, user_id: int, chat_id: int, text: str = "", *, username: str | None = None,
                     first_name: str = "U", message_id: int | None = None, voice_file_id: str | None = None) -> dict:
        msg: dict = {"message_id": message_id or update_id, "from": {"id": user_id, "first_name": first_name, "is_bot": False},
                     "chat": {"id": chat_id, "type": "private"}, "date": 0}
        if username:
            msg["from"]["username"] = username
        if voice_file_id:
            msg["voice"] = {"file_id": voice_file_id, "mime_type": "audio/ogg", "duration": 2}
        else:
            msg["text"] = text
        u = {"update_id": update_id, "message": msg}
        self.incoming.append(u)
        return u

    def push_callback(self, update_id: int, user_id: int, chat_id: int, data: str, *, callback_id: str | None = None,
                      message_id: int = 1) -> dict:
        u = {"update_id": update_id, "callback_query": {"id": callback_id or f"cbq{update_id}", "from": {"id": user_id, "first_name": "U"},
                                                        "message": {"message_id": message_id, "chat": {"id": chat_id, "type": "private"}},
                                                        "data": data}}
        self.incoming.append(u)
        return u

    def get_updates(self, offset: int | None, timeout: int) -> list[dict]:
        batch = [u for u in self.incoming if offset is None or u["update_id"] >= offset]
        self.incoming = [u for u in self.incoming if u not in batch]
        return batch

    def send_message(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> dict:
        if self.fail_sends > 0:
            self.fail_sends -= 1
            raise TelegramError("simulated send failure")
        self.next_message_id += 1
        rec = {"chat_id": chat_id, "text": text, "buttons": buttons or [], "message_id": self.next_message_id}
        self.sent.append(rec)
        return rec

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self.callbacks_answered.append((callback_id, text))

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self.actions = getattr(self, "actions", [])
        self.actions.append((chat_id, action))

    def edit_buttons(self, chat_id: int, message_id: int, buttons: list[list[dict]] | None) -> None:
        pass

    def send_photo(self, chat_id: int, image: bytes, caption: str = "", filename: str = "plan.png") -> dict:
        self.photos = getattr(self, "photos", []); self.photos.append((chat_id, len(image), caption, filename))
        return {"message_id": 900 + len(self.photos)}

    def get_file(self, file_id: str) -> bytes:
        return self.files.get(file_id, b"")

    def get_me(self) -> dict:
        return self.me

    # helpers for assertions
    def texts(self, chat_id: int | None = None) -> list[str]:
        return [m["text"] for m in self.sent if chat_id is None or m["chat_id"] == chat_id]

    def last(self) -> dict:
        return self.sent[-1] if self.sent else {}
