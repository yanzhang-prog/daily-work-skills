"""A canned stand-in for ClaudeSession, for the page and tests (TICKET_BOARD_FAKE=1).

Same interface as ClaudeSession. On send() it emits some text, a tool call, then a permission
request for a Linear write, waits for the answer, and finishes the turn.
"""
import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import config
from integrations.claude_session import (
    AssistantText, Event, PermissionRequest, SessionError, ToolActivity, TurnFinished,
)

FAKE_TOOL = "mcp__claude_ai_Linear__save_issue"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeClaudeSession:
    def __init__(self, repo_lines: list[str], client_factory=None, cwd=None,
                 delay: float | None = None) -> None:
        self._repo_lines = repo_lines
        self._delay = config.FAKE_SESSION_DELAY_SECONDS if delay is None else delay
        self._queue: asyncio.Queue = asyncio.Queue()
        self._pending: dict[str, asyncio.Future] = {}
        self._tasks: set[asyncio.Task] = set()
        self._turn_lock = asyncio.Lock()
        self._session_id: str | None = None
        self._alive = False
        self._closed = False

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def alive(self) -> bool:
        return self._alive

    async def start(self, resume: str | None = None) -> None:
        if self._closed:
            raise RuntimeError("start() can only be called before close()")
        self._session_id = resume
        self._alive = True

    async def send(self, text: str) -> None:
        if not self._alive or self._closed:
            self._queue.put_nowait(SessionError("session is not running", _now()))
            return
        task = asyncio.create_task(self._turn(text))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _turn(self, text: str) -> None:
        async with self._turn_lock:
            emit = self._queue.put_nowait
            await asyncio.sleep(self._delay)
            emit(AssistantText(f"(fake) working on: {text[:60]}", _now()))
            await asyncio.sleep(self._delay)
            emit(ToolActivity("Read", "Read file_path=README.md", _now()))
            await asyncio.sleep(self._delay)
            request_id = uuid.uuid4().hex
            fut = asyncio.get_running_loop().create_future()
            self._pending[request_id] = fut
            emit(PermissionRequest(request_id, FAKE_TOOL, "title=(fake) ticket", _now()))
            try:
                allowed = await fut
            finally:
                self._pending.pop(request_id, None)
            if self._closed:
                return
            emit(AssistantText("(fake) saved." if allowed else "(fake) not saved: denied.", _now()))
            self._session_id = self._session_id or f"fake-{uuid.uuid4().hex[:8]}"
            emit(TurnFinished(self._session_id, _now()))

    async def answer_permission(self, request_id: str, allow: bool) -> None:
        fut = self._pending.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(bool(allow))

    async def events(self) -> AsyncIterator[Event]:
        while True:
            ev = await self._queue.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._alive = False
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result(False)
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._queue.put_nowait(None)
