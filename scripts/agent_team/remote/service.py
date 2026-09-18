"""The Telegram polling service — a deterministic process, not an LLM loop.

    loop:
      drain the notification outbox (READY FOR OWNER messages; bounded retries; dedup by key)
      getUpdates(offset, long-poll timeout)
      for each update: replay-protect by update_id -> pairing / authorization -> quick parse or
                       interpreter -> typed command -> gateway -> reply
      persist the offset

Single instance per repo (flock + pid file). SIGTERM stops after the current poll returns.
"""
from __future__ import annotations

import fcntl
import logging
import os
import queue
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_team.agent_runner import redact
from agent_team.config import Config
from agent_team.remote import commands as C
from agent_team.remote.commands import OwnerCommand, parse_callback
from agent_team.remote.gateway import Gateway
from agent_team.remote.transport import TelegramError, TelegramTransport
from agent_team.remote.voice import NullTranscriber, Transcriber
from agent_team.state_store import StateStore

log = logging.getLogger("agent_team.remote")


class RemoteAlreadyRunning(RuntimeError):
    pass


@dataclass
class RemoteService:
    config: Config
    store: StateStore
    transport: TelegramTransport
    gateway: Gateway
    transcriber: Transcriber = field(default_factory=NullTranscriber)
    clock: object = time.time
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock_fh: object = None
    handled: int = 0
    # Updates are handled on one worker thread (in order) so a slow interpreter call never blocks
    # polling; `threaded=False` (tests) handles them inline.
    threaded: bool = False
    _queue: "queue.Queue[dict]" = field(default_factory=queue.Queue)
    _worker: threading.Thread | None = None

    # -- singleton ------------------------------------------------------------------------
    def acquire_singleton(self) -> None:
        path = self.config.path(self.config.state_dir) / "remote.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise RemoteAlreadyRunning(f"another Telegram service holds {path}") from exc
        fh.seek(0); fh.truncate(); fh.write(str(os.getpid())); fh.flush()
        self._lock_fh = fh

    def release_singleton(self) -> None:
        if self._lock_fh:
            try:
                fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_fh.close()
                self._lock_fh = None

    # -- one iteration --------------------------------------------------------------------
    def drain_outbox(self) -> int:
        owner = self.store.owner()
        if owner is None:
            return 0   # nobody to notify yet: rows stay pending without consuming attempts
        sent = 0
        for note in self.store.due_notifications():
            buttons = [[{"text": b["text"], "data": b["data"]} for b in row] for row in note["buttons"]]
            try:
                res = self.transport.send_message(int(owner["chat_id"]), note["text"], buttons)
                self.store.mark_notification(note["id"], sent=True, message_id=res.get("message_id"))
                sent += 1
            except TelegramError as exc:
                status = self.store.mark_notification(note["id"], sent=False, error=redact(str(exc)),
                                                      max_attempts=self.config.notify_max_attempts,
                                                      backoff_seconds=self.config.notify_retry_backoff_seconds)
                log.warning("notification %s failed (%s): %s", note["dedup_key"], status, redact(str(exc)))
        return sent

    def poll_once(self, timeout: int | None = None) -> int:
        offset_raw = self.store.get_meta("telegram_offset")
        offset = int(offset_raw) if offset_raw else None
        try:
            updates = self.transport.get_updates(offset, self.config.telegram_poll_timeout_seconds if timeout is None else timeout)
        except TelegramError as exc:
            log.warning("getUpdates failed: %s", redact(str(exc)))
            return 0
        n = 0
        for u in updates:
            uid = int(u.get("update_id", 0))
            try:
                if self.store.mark_update(uid):
                    self._typing_ack(u)
                    if self.threaded:
                        self._queue.put(u)
                    else:
                        self.handle_update(u)
                    n += 1
            except Exception:  # noqa: BLE001 — a malformed update must never stop the service
                log.exception("update %s failed", uid)
            self.store.set_meta("telegram_offset", str(uid + 1))
        self.handled += n
        return n

    def _typing_ack(self, u: dict) -> None:
        """Instant feedback: show 'typing…' the moment an owner message is received."""
        msg = u.get("message") or (u.get("callback_query") or {}).get("message") or {}
        chat = (msg.get("chat") or {}).get("id")
        sender = ((u.get("message") or u.get("callback_query") or {}).get("from") or {}).get("id")
        if chat and sender and self.gateway.is_owner(sender):
            try:
                self.transport.send_chat_action(int(chat), "typing")
            except Exception:  # noqa: BLE001
                pass

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                u = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.handle_update(u)
            except Exception:  # noqa: BLE001
                log.exception("update handling failed")

    def tick(self) -> None:
        self.drain_outbox()
        self.poll_once()

    def run(self) -> None:
        self.acquire_singleton()
        previous = {}
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *_: self._stop.set())
            log.info("telegram service started (long polling, timeout %ss)", self.config.telegram_poll_timeout_seconds)
            self.threaded = True
            self._worker = threading.Thread(target=self._worker_loop, name="telegram-handler", daemon=True)
            self._worker.start()
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:  # noqa: BLE001
                    log.exception("tick failed")
                    self._stop.wait(5)
        finally:
            for sig, h in previous.items():
                signal.signal(sig, h)
            self.release_singleton()

    # -- dispatch -------------------------------------------------------------------------
    def handle_update(self, u: dict) -> None:
        if "callback_query" in u:
            self._handle_callback(u["callback_query"])
            return
        msg = u.get("message")
        if not isinstance(msg, dict):
            return
        chat = msg.get("chat") or {}
        sender = msg.get("from") or {}
        if chat.get("type") != "private" or sender.get("is_bot"):
            return
        chat_id, user_id = int(chat["id"]), int(sender["id"])
        command_id = f"msg:{chat_id}:{msg.get('message_id')}"
        text = msg.get("text")
        from_voice = False
        if text is None and (msg.get("voice") or msg.get("audio")):
            from_voice = True
            media = msg.get("voice") or msg.get("audio")
            if not self.gateway.is_owner(user_id):
                self._reply(chat_id, "⛔ לא מורשה.")
                return
            try:
                audio = self.transport.get_file(media["file_id"])
            except TelegramError:
                audio = b""
            text = self.transcriber.transcribe(audio, media.get("mime_type", "audio/ogg"))
            if not text:
                self._reply(chat_id, "התקבלה הודעה קולית, אבל תמלול לא מוגדר (remote_control.telegram.transcription_provider). אנא הקלד את ההודעה.")
                return
            self.store.record_event(None, "voice_transcribed", {"chars": len(text)})
        if not isinstance(text, str) or not text.strip():
            return
        text = text.strip()[:4000]
        quick = C.quick_parse(text)
        if quick and quick.action == C.PAIR:
            reply = self.gateway.execute(OwnerCommand(C.PAIR, {"code": quick.args["code"]}, command_id=command_id, user_id=user_id, chat_id=chat_id))
            self._reply(chat_id, reply.text)
            return
        if not self.gateway.is_owner(user_id):
            self.store.record_event(None, "remote_denied", {"user_id": user_id, "chat_id": chat_id, "reason": "not the paired owner"})
            self._reply(chat_id, "⛔ לא מורשה. הבוט הזה עונה רק לבעלים המצומד.")
            return
        def on_slow(action: str) -> None:
            self._reply(chat_id, "⏳ מנסח את הטיוטה, זה לוקח כדקה…" if action == C.CREATE_ISSUE_DRAFT else "⏳ מעדכן את הטיוטה…")
            self.transport.send_chat_action(chat_id, "typing")

        reply = self.gateway.interpret_and_execute(text, user_id=user_id, chat_id=chat_id, command_id=command_id, from_voice=from_voice,
                                                   on_slow=on_slow)
        self._reply(chat_id, reply.text, reply.buttons)

    def _handle_callback(self, cq: dict) -> None:
        sender = cq.get("from") or {}
        chat = (cq.get("message") or {}).get("chat") or {}
        user_id = int(sender.get("id", 0))
        chat_id = int(chat.get("id", 0)) if chat else None
        cmd = parse_callback(cq.get("data", ""))
        try:
            self.transport.answer_callback(str(cq.get("id", "")))
        except Exception:  # noqa: BLE001
            pass
        if cmd is None:
            if chat_id:
                self._reply(chat_id, "הכפתור הזה כבר לא תקף.")
            return
        cmd.command_id = f"cb:{cq.get('id')}"
        cmd.user_id, cmd.chat_id = user_id, chat_id
        if not self.gateway.is_owner(user_id):
            self.store.record_event(None, "remote_denied", {"user_id": user_id, "reason": "callback from non-owner", "action": cmd.action})
            return
        reply = self.gateway.execute(cmd)
        if chat_id:
            self._reply(chat_id, reply.text, reply.buttons)

    def _reply(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
        try:
            self.transport.send_message(chat_id, text[:12000], buttons)
        except TelegramError as exc:
            log.warning("reply to %s failed: %s", chat_id, redact(str(exc)))
