"""Voice messages: a transcription adapter so voice enters the SAME command path as text.

`transcribe(audio, mime) -> text | None`. `NullTranscriber` (default) returns None and the service
tells the owner that voice is not configured — text V1 is never blocked by a missing provider.
`OpenAIWhisperTranscriber` posts the audio to OpenAI's transcription endpoint when
`remote_control.telegram.transcription_provider: openai` and OPENAI_API_KEY is set.

Voice may draft Issues and ask questions. Voice never authorizes a merge: CONFIRM_MERGE is
button-only in the gateway, regardless of what a transcript says.
"""
from __future__ import annotations

import json
import os
import urllib.request
import uuid
from typing import Protocol


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio: bytes, mime: str) -> str | None: ...


class NullTranscriber:
    name = "none"

    def transcribe(self, audio: bytes, mime: str) -> str | None:
        return None


class OpenAIWhisperTranscriber:
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str = "whisper-1"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model

    def transcribe(self, audio: bytes, mime: str) -> str | None:
        if not self.api_key or not audio:
            return None
        boundary = uuid.uuid4().hex
        ext = "ogg" if "ogg" in (mime or "") else "m4a"
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{self.model}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voice.{ext}\"\r\nContent-Type: {mime or 'audio/ogg'}\r\n\r\n".encode(),
            audio, b"\r\n", f"--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=body, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return (json.load(resp).get("text") or "").strip() or None
        except Exception:  # noqa: BLE001 — a failed transcription is "not understood", never a crash
            return None


class FakeTranscriber:
    name = "fake"

    def __init__(self, mapping: dict[bytes, str] | None = None):
        self.mapping = mapping or {}

    def transcribe(self, audio: bytes, mime: str) -> str | None:
        return self.mapping.get(audio)


def make_transcriber(provider: str) -> Transcriber:
    if provider == "openai":
        return OpenAIWhisperTranscriber()
    return NullTranscriber()
