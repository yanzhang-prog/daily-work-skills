"""Wrapper around one Claude Agent SDK session (one board column).

Why a wrapper: the SDK gives us a message stream and a permission callback. The board wants
a small, typed event stream plus an approval gate that can wait as long as the human needs.
All SDK specifics live here so the rest of the app (and the tests) never import the SDK.
"""
import asyncio
import re
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
VALUE_MAX_CHARS = 120
ERROR_MAX_CHARS = 300
NOT_RUNNING = "session is not running"
# Only these input keys have their (redacted, truncated) value shown; all others show a size.
_SAFE_KEYS = {"file_path", "path", "pattern", "url", "title", "name", "query", "team", "project",
              "state", "label", "labels", "assignee", "id", "issue", "command"}
_REDACTIONS = [  # ordered; each replaces the secret part with <redacted>
    re.compile(r"(?i)authorization\s*[=:]\s*\S+(\s+\S+)?"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"(?i)[\w-]*(token|password|passwd|secret|api[_-]?key|apikey|access[_-]?key|cookie"
               r"|credential|auth)[\w-]*\s*[=:]\s*\S+"),
    re.compile(r'(?i)"[\w-]*(token|password|passwd|secret|api[_-]?key|cookie|credential|auth)[\w-]*"'
               r'\s*:\s*"[^"]*"'),
    re.compile(r"(?i)--[\w-]*(token|password|passwd|secret|api[_-]?key|key)[\w-]*[ =]\S+"),
    re.compile(r"(?i)(?<!\S)-u\s+\S+:\S+"),
    re.compile(r"(?i)[?&](token|access_token|api_key|key|sig|signature|secret|password)=[^&\s]+"),
    re.compile(r"://[^/\s:@]+:[^@\s]+@"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
]


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


def _redact(text: str) -> str:
    for rx in _REDACTIONS:
        text = rx.sub("<redacted>", text)
    return text


def _describe(key: str, value: Any) -> str:
    if isinstance(value, (list, dict, tuple, set)):
        return f"{key}={len(value)} items"
    if key not in _SAFE_KEYS:
        return f"{key}={len(str(value))} chars"
    s = _redact(" ".join(str(value).split()))
    return f"{key}={s[:VALUE_MAX_CHARS] + '...' if len(s) > VALUE_MAX_CHARS else s}"


def summarize(tool: str, tool_input: dict[str, Any] | None) -> str:
    """Short one-liner: tool name plus safe inputs. Unsafe keys show only their size."""
    parts = [_describe(str(k), v) for k, v in (tool_input or {}).items()]
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
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._session_id: str | None = None
        self._alive = False
        self._closed = False
        self._closed_evt = asyncio.Event()

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
            permission_mode="default",  # never a skip-permissions mode
            resume=resume,
        )

    async def start(self, resume: str | None = None) -> None:
        if self._closed or self._client is not None:
            raise RuntimeError("start() can only be called once, before close()")
        self._client = self._factory(self._build_options(resume))
        try:
            await self._client.connect()
        except Exception as e:  # noqa: BLE001 - any transport failure is surfaced as an event
            self._fail(e)
            return
        self._alive = True
        self._worker = asyncio.create_task(self._work())

    async def send(self, text: str) -> None:
        if not self._alive or self._closed:
            self._emit(SessionError(NOT_RUNNING, _now()))
            return
        self._inbox.put_nowait(text)

    async def _work(self) -> None:
        """The single consumer of the SDK stream: one turn at a time, in order."""
        while True:
            text = await self._inbox.get()
            if not await self._run_turn(text):
                while not self._inbox.empty():  # report, never silently drop, queued messages
                    self._inbox.get_nowait()
                    self._emit(SessionError("message not delivered: session failed", _now()))
                return

    async def _run_turn(self, text: str) -> bool:
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
            return True
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return False

    def _fail(self, e: Exception) -> None:
        self._alive = False
        self._emit(SessionError(f"{type(e).__name__}: {e}"[:ERROR_MAX_CHARS], _now()))

    def _emit(self, event: Event) -> None:
        self._queue.put_nowait(event)

    async def _can_use_tool(self, tool_name: str, tool_input: dict[str, Any], context: Any):
        """Allow only exact ALLOWED_TOOLS matches at once; otherwise ask the human and wait.

        Bash(...) rule patterns are enforced CLI-side and never equal a bare "Bash" here, so
        unmatched Bash calls reach the human."""
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
        """Yield queued events; once close() was called, drain what is left and stop."""
        while True:
            if self._queue.empty():
                if self._closed:
                    return
                getter = asyncio.ensure_future(self._queue.get())
                closer = asyncio.ensure_future(self._closed_evt.wait())
                done, pending = await asyncio.wait({getter, closer}, return_when=asyncio.FIRST_COMPLETED)
                for p in pending:
                    p.cancel()
                if getter not in done:
                    await asyncio.gather(*pending, return_exceptions=True)
                    continue
                yield getter.result()
            else:
                yield self._queue.get_nowait()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._closed_evt.set()
        self._alive = False
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result(False)
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
        self._closed_evt.set()
