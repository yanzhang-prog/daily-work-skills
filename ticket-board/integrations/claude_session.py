"""Wrapper around one Claude Agent SDK session (one board column).

Why a wrapper: the SDK gives us a message stream and a permission callback. The board wants
a small, typed event stream plus an approval gate that can wait as long as the human needs.
All SDK specifics live here so the rest of the app (and the tests) never import the SDK.
"""
import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, PermissionResultAllow,
    PermissionResultDeny, ResultMessage, TextBlock, ToolUseBlock,
)

import config
from prompts import COLUMN_REPO_CONTEXT_PROMPT

SUMMARY_MAX_CHARS = 200
VALUE_MAX_CHARS = 60
ERROR_MAX_CHARS = 300
# Input keys never shown in a summary (bulk content or likely secrets).
_HIDDEN_KEY_PARTS = ("content", "body", "text", "description", "token", "secret",
                     "password", "key", "authorization", "new_string", "old_string")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AssistantText:
    text: str
    at: datetime


@dataclass(frozen=True)
class ToolActivity:
    tool: str
    summary: str
    at: datetime


@dataclass(frozen=True)
class PermissionRequest:
    request_id: str
    tool: str
    summary: str
    at: datetime


@dataclass(frozen=True)
class TurnFinished:
    session_id: str
    at: datetime


@dataclass(frozen=True)
class SessionError:
    message: str
    at: datetime


Event = AssistantText | ToolActivity | PermissionRequest | TurnFinished | SessionError

_END = object()  # queue sentinel: close() was called


def summarize(tool: str, tool_input: dict[str, Any] | None) -> str:
    """Short, secret-free one-liner: tool name plus truncated scalar inputs."""
    parts = []
    for k, v in (tool_input or {}).items():
        if any(h in str(k).lower() for h in _HIDDEN_KEY_PARTS):
            continue
        s = str(v).replace("\n", " ")
        if len(s) > VALUE_MAX_CHARS:
            s = s[:VALUE_MAX_CHARS] + "..."
        parts.append(f"{k}={s}")
    out = f"{tool} {' '.join(parts)}".strip()
    return out if len(out) <= SUMMARY_MAX_CHARS else out[:SUMMARY_MAX_CHARS - 3] + "..."


def _default_factory(options: ClaudeAgentOptions):
    return ClaudeSDKClient(options)


class ClaudeSession:
    def __init__(self, repo_lines: list[str], client_factory: Callable[[ClaudeAgentOptions], Any] | None = None,
                 cwd=None) -> None:
        self._repo_lines = repo_lines
        self._factory = client_factory or _default_factory
        self._cwd = cwd or config.SESSION_CWD
        self._client = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._pending: dict[str, asyncio.Future] = {}
        self._tasks: set[asyncio.Task] = set()
        self._session_id: str | None = None
        self._alive = False
        self._closed = False

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def alive(self) -> bool:
        return self._alive

    def _build_options(self, resume: str | None) -> ClaudeAgentOptions:
        repo_list = "\n".join(f"- {line}" for line in self._repo_lines)
        cwd = str(self._cwd)
        return ClaudeAgentOptions(
            model=config.MODEL_NAME,
            cwd=cwd,
            add_dirs=[str(r.path) for r in config.REPOS if str(r.path) != cwd],
            setting_sources=["user", "project"],
            system_prompt={"type": "preset", "preset": "claude_code",
                           "append": COLUMN_REPO_CONTEXT_PROMPT.format(repo_list=repo_list)},
            allowed_tools=list(config.ALLOWED_TOOLS),
            disallowed_tools=list(config.DISALLOWED_TOOLS),
            can_use_tool=self._can_use_tool,
            resume=resume,
        )

    async def start(self, resume: str | None = None) -> None:
        self._client = self._factory(self._build_options(resume))
        try:
            await self._client.connect()
            self._alive = True
        except Exception as e:  # noqa: BLE001 - any transport failure is surfaced as an event
            self._fail(e)

    async def send(self, text: str) -> None:
        if self._client is None or self._closed:
            return
        task = asyncio.create_task(self._run_turn(text))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_turn(self, text: str) -> None:
        try:
            await self._client.query(text)
            async for msg in self._client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for b in msg.content:
                        if isinstance(b, TextBlock):
                            self._emit(AssistantText(b.text, _now()))
                        elif isinstance(b, ToolUseBlock):
                            self._emit(ToolActivity(b.name, summarize(b.name, b.input), _now()))
                elif isinstance(msg, ResultMessage):
                    self._session_id = msg.session_id
                    self._emit(TurnFinished(msg.session_id, _now()))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self._fail(e)

    def _fail(self, e: Exception) -> None:
        self._alive = False
        self._emit(SessionError(f"{type(e).__name__}: {e}"[:ERROR_MAX_CHARS], _now()))

    def _emit(self, event: Event) -> None:
        self._queue.put_nowait(event)

    async def _can_use_tool(self, tool_name: str, tool_input: dict[str, Any], context: Any):
        """Allow only exact ALLOWED_TOOLS matches at once; otherwise ask the human and wait."""
        if tool_name in config.ALLOWED_TOOLS:
            return PermissionResultAllow()
        if self._closed:
            return PermissionResultDeny(message="Session closed.")
        request_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = fut
        self._emit(PermissionRequest(request_id, tool_name, summarize(tool_name, tool_input), _now()))
        try:
            allow = await fut  # no timeout on purpose: the human decides
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never allow on error
            allow = False
        finally:
            self._pending.pop(request_id, None)
        if allow is True:
            return PermissionResultAllow()
        return PermissionResultDeny(message="Yan denied this action.")

    async def answer_permission(self, request_id: str, allow: bool) -> None:
        fut = self._pending.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(bool(allow))
        # Unknown id: ignored, nothing is ever allowed by default.

    async def events(self) -> AsyncIterator[Event]:
        while True:
            item = await self._queue.get()
            if item is _END:
                return
            yield item

    async def close(self) -> None:
        self._closed = True
        self._alive = False
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result(False)
        for t in list(self._tasks):
            t.cancel()
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
        self._queue.put_nowait(_END)
