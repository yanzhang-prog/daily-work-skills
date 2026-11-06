"""Ticket board server: HTTP + WebSocket wiring only.

Status rules live in states/column_state.py, history persistence in states/history_state.py,
git and Claude access in integrations/. This module connects them.

Security: the board can approve a Linear write, so every HTTP and WebSocket request must come
from a page on this machine. The Host check blocks DNS rebinding (a hostile site resolving to
127.0.0.1); the Origin check blocks cross-site requests and cross-site WebSocket hijacking
(browsers do not apply CORS to WebSockets, so the server must check).
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints
from starlette.websockets import WebSocketDisconnect

import config
from integrations.claude_session import (
    AssistantText, ClaudeSession, PermissionRequest, SessionError, ToolActivity, TurnFinished,
    redact_text,
)
from integrations.fake_session import FakeClaudeSession
from integrations.git_repos import RepoSnapshot, describe, fetch_and_snapshot
from prompts import COLUMN_FIRST_MESSAGE_PROMPT
from states.column_state import Column, ColumnRegistry, SessionFlags, Status, derive_status
from states.handoff_state import HandoffSummary, read_handoff
from states.history_state import HistoryStore

log = logging.getLogger("ticket_board")
STATIC_DIR = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LABELS = {Status.WORKING: "Working", Status.NEEDS_YOU: "Needs you",
          Status.DONE: "Done", Status.STUCK: "Stuck"}
CLOSE_NOT_FOUND = 4404
ERROR_LIMIT = 300  # chars of any error text shown to the client or stored


def assert_local_host(host: str) -> None:
    if host not in LOCAL_HOSTS:
        raise ValueError(f"refusing to bind {host!r}: the board must stay on localhost")


class NewColumn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=config.MAX_TITLE_CHARS)]
    request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                              max_length=config.MAX_TEXT_CHARS)]


class OriginHostGuard:
    """Pure ASGI middleware: reject foreign Host or Origin headers before any route runs."""

    def __init__(self, app, allowed_hosts: set[str], allowed_origins: set[str]):
        self.app, self.hosts, self.origins = app, allowed_hosts, allowed_origins

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            bad = headers.get("host") not in self.hosts or (
                "origin" in headers and headers["origin"] not in self.origins)
            if bad:
                if scope["type"] == "websocket":
                    await receive()  # websocket.connect
                    await send({"type": "websocket.close", "code": 1008})  # before accept = HTTP 403
                else:
                    await JSONResponse({"detail": "forbidden"}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


@dataclass
class Runtime:
    """Live (in-memory) side of one column."""
    column: Column
    session: Any = None
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    subscribers: set = field(default_factory=set)
    pending: dict[str, str] = field(default_factory=dict)  # request_id -> tool
    waiting_for_reply: bool = False
    last_event_at: datetime | None = None
    error: str | None = None
    last_sig: tuple | None = None
    primed: bool = False
    starting: bool = False


class Board:
    def __init__(self, *, registry, session_factory, snapshotter, handoff_reader, clock,
                 history, repos, poll_seconds):
        self.registry, self.session_factory = registry, session_factory
        self.snapshotter, self.handoff_reader = snapshotter, handoff_reader
        self.clock, self.history, self.repos = clock, history, repos
        self.poll_seconds = poll_seconds
        self.runtimes: dict[str, Runtime] = {}
        self.board_subs: set[asyncio.Queue] = set()
        self.poll_task: asyncio.Task | None = None

    # ----- status -----
    def runtime(self, col: Column) -> Runtime:
        rt = self.runtimes.get(col.id)
        if rt is None:
            rt = self.runtimes[col.id] = Runtime(col)
        rt.column = col
        return rt

    async def primed(self, col: Column) -> Runtime:
        """Runtime whose history seq counter is loaded. The first next_seq scans the file, so
        it runs in a thread here; after that record() is a pure in-memory + tiny append."""
        rt = self.runtime(col)
        if not rt.primed:
            await asyncio.to_thread(self.history.next_seq, col.id)
            rt.primed = True
        return rt

    async def _handoff(self, col: Column) -> HandoffSummary | None:
        if not col.handoff_path:
            return None
        return await asyncio.to_thread(self.handoff_reader, col.handoff_path)

    async def status_json(self, rt: Runtime) -> dict:
        h = await self._handoff(rt.column)  # the only await; flags are read after it
        flags = SessionFlags(
            alive=bool(rt.starting or (rt.session is not None and rt.session.alive)),
            waiting_for_reply=rt.waiting_for_reply,
            pending_permission=next(reversed(rt.pending.values()), None),
            last_event_at=self.clock() if rt.starting else rt.last_event_at,
            error=None if rt.starting else rt.error)
        st = derive_status(handoff=h, session=flags, now=self.clock())
        note = "starting..." if rt.starting and st.status == Status.WORKING else st.note
        return {"status": st.status.value, "label": LABELS[st.status], "note": note,
                "phase": h.current_phase if h else "Investigate",
                "completed": list(h.completed) if h else []}

    async def column_json(self, col: Column) -> dict:
        s = await self.status_json(self.runtime(col))
        return {"id": col.id, "title": col.title, **s,
                "repos_read": list(col.repos_read), "closed": col.closed}

    async def columns_json(self, include_closed: bool = False) -> list[dict]:
        return [await self.column_json(c) for c in self.registry.list(include_closed)]

    async def publish(self, rt: Runtime) -> None:
        """Push status to this column's sockets, and the list to the board, if it changed."""
        s = await self.status_json(rt)
        sig = (s["status"], s["note"], s["phase"], tuple(s["completed"]))
        if sig == rt.last_sig:
            return
        rt.last_sig = sig
        for q in list(rt.subscribers):
            q.put_nowait({"kind": "status", "status": s})
        await self.notify_board()

    async def notify_board(self) -> None:
        if self.board_subs:
            msg = {"kind": "columns", "columns": await self.columns_json()}
            for q in list(self.board_subs):
                q.put_nowait(msg)

    # ----- events -----
    def record(self, rt: Runtime, type_: str, at: datetime, **fields) -> None:
        """Store (seq assigned here) and then broadcast. Stored first so a replay that starts
        after a broadcast always sees it; clients de-duplicate by seq.

        Deliberately synchronous (R18b compromise): the append is a tiny write, and having no
        await between assigning the seq and appending it is what keeps seq strictly increasing
        under concurrent callers. The heavy reads (first seq scan, replay, handoff files) run
        in threads instead."""
        cid = rt.column.id
        ev = {"seq": self.history.next_seq(cid), "type": type_, "at": at.isoformat(), **fields}
        self.history.append(cid, ev)
        for q in list(rt.subscribers):
            q.put_nowait({"kind": "event", "event": ev})

    async def handle_event(self, rt: Runtime, ev) -> None:
        rt.last_event_at = self.clock()
        if isinstance(ev, AssistantText):
            self.record(rt, "assistant_text", ev.at, text=ev.text)
        elif isinstance(ev, ToolActivity):
            self.record(rt, "tool_activity", ev.at, tool=ev.tool, summary=ev.summary)
        elif isinstance(ev, PermissionRequest):
            rt.pending[ev.request_id] = ev.tool
            self.record(rt, "permission_request", ev.at, request_id=ev.request_id,
                        tool=ev.tool, summary=ev.summary)
        elif isinstance(ev, TurnFinished):
            rt.waiting_for_reply = True
            if rt.column.session_id != ev.session_id:
                rt.column.session_id = ev.session_id
                self.registry.update(rt.column)
            self.record(rt, "turn_finished", ev.at, session_id=ev.session_id)
        elif isinstance(ev, SessionError):
            rt.error = redact_text(ev.message, ERROR_LIMIT)
            self.record(rt, "session_error", ev.at, message=rt.error)
        await self.publish(rt)

    async def pump(self, rt: Runtime, session) -> None:
        try:
            async for ev in session.events():
                await self.handle_event(rt, ev)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("event stream failed for %s", rt.column.id)
            rt.error = "event stream failed"
        finally:
            if rt.session is session:
                rt.pending.clear()
        if rt.session is session:
            await self.publish(rt)

    # ----- sessions -----
    async def snapshots(self) -> list[RepoSnapshot]:
        return list(await asyncio.gather(
            *(asyncio.to_thread(self.snapshotter, r) for r in self.repos)))

    @staticmethod
    def repo_line(s: RepoSnapshot) -> str:
        detail = s.error if s.error or not s.ref else f"read {s.ref}"
        return f"{s.path.name}: {s.path} ({detail or 'not searched'})"

    @staticmethod
    async def _close_quiet(session) -> None:
        try:
            await session.close()
        except Exception as e:  # noqa: BLE001 - best effort; never surface or log raw text
            log.warning("session close failed: %s", redact_text(f"{type(e).__name__}: {e}"))

    async def retire(self, rt: Runtime) -> None:
        """Close the current session and stop its pump, so nothing leaks or feeds stale events."""
        old, rt.session = rt.session, None
        if old is not None:
            await self._close_quiet(old)
        await self._stop_task(rt)
        rt.pending = {}

    async def launch(self, rt: Runtime, repo_lines: list[str], resume: str | None) -> bool:
        """Create a NEW session (a failed/closed one cannot restart) and start its event pump."""
        await self.retire(rt)
        session = self.session_factory(repo_lines)
        rt.session, rt.error = session, None
        rt.waiting_for_reply = False
        rt.last_event_at = self.clock()
        try:
            await session.start(resume=resume)
        except Exception as e:  # noqa: BLE001
            log.warning("session start failed for %s: %s", rt.column.id, type(e).__name__)
            await self._fail(rt, e)
            await self.retire(rt)
            return False
        rt.task = asyncio.create_task(self.pump(rt, session))
        if not session.alive:  # failed start: the error event is queued; close lets it drain
            await self._close_quiet(session)
            return False
        return True

    async def _fail(self, rt: Runtime, e: Exception) -> None:
        rt.error = redact_text(f"{type(e).__name__}: {e}", ERROR_LIMIT)
        self.record(rt, "session_error", self.clock(), message=rt.error)

    @asynccontextmanager
    async def starting(self, rt: Runtime):
        """Show Working "starting..." (not Stuck) while repos fetch and the session starts."""
        rt.starting = True
        await self.publish(rt)
        try:
            yield
        finally:
            rt.starting = False

    async def ensure_session(self, rt: Runtime) -> None:
        """Lazy resume: on first open after a restart (stored session id, no live session)."""
        async with rt.lock:
            sid = rt.column.session_id
            if sid and (rt.session is None or not rt.session.alive) and not rt.column.closed:
                async with self.starting(rt):
                    snaps = await self.snapshots()
                    await self.launch(rt, [self.repo_line(s) for s in snaps], sid)
                await self.publish(rt)

    async def create(self, title: str, request: str) -> Column:
        col = self.registry.add(title)
        rt = await self.primed(col)
        async with rt.lock:
            try:
                async with self.starting(rt):
                    snaps = await self.snapshots()
                    col.repos_read = [describe(s) for s in snaps]
                    self.registry.update(col)
                    if await self.launch(rt, [self.repo_line(s) for s in snaps], None):
                        first = COLUMN_FIRST_MESSAGE_PROMPT.format(
                            request=request, handoff_path=col.handoff_path)
                        self.record(rt, "user_message", self.clock(), message=request)
                        await rt.session.send(first)
            except Exception as e:  # noqa: BLE001 - keep the column, show it Stuck
                log.warning("create failed for %s: %s", col.id, type(e).__name__)
                await self._fail(rt, e)
                await self.retire(rt)
        await self.publish(rt)
        await self.notify_board()
        return col

    async def close_column(self, col: Column) -> None:
        rt = self.runtime(col)
        async with rt.lock:
            await self.retire(rt)
            self.registry.close(col.id)  # handoff and history files are never touched
            for q in list(rt.subscribers):
                q.put_nowait(None)
        await self.notify_board()

    async def reopen(self, col: Column) -> Column:
        col = self.registry.reopen(col.id)
        rt = await self.primed(col)
        async with rt.lock:
            if rt.session is None or not rt.session.alive:
                if col.session_id:
                    async with self.starting(rt):
                        snaps = await self.snapshots()
                        await self.launch(rt, [self.repo_line(s) for s in snaps], col.session_id)
                else:
                    await self.retire(rt)
                    rt.error = "no session to resume"
        await self.publish(rt)
        await self.notify_board()
        return col

    @staticmethod
    async def _stop_task(rt: Runtime) -> None:
        task, rt.task = rt.task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    # ----- client commands -----
    async def on_message(self, rt: Runtime, text: str) -> str | None:
        if rt.session is None or not rt.session.alive:
            return "session is not running"
        rt.waiting_for_reply = False
        rt.last_event_at = self.clock()
        self.record(rt, "user_message", self.clock(), message=text)
        await self.publish(rt)
        await rt.session.send(text)
        return None

    async def on_permission(self, rt: Runtime, request_id: str, allow: bool) -> None:
        tool = rt.pending.pop(request_id, None)
        if tool is None or rt.session is None:
            return  # not a request of THIS column's session: ignore
        self.record(rt, "permission_answer", self.clock(), request_id=request_id,
                    tool=tool, allow=allow)
        await self.publish(rt)
        await rt.session.answer_permission(request_id, allow)

    # ----- polling and shutdown -----
    async def poll(self) -> None:
        while True:
            await asyncio.sleep(self.poll_seconds)
            for col in self.registry.list():
                await self.publish(self.runtime(col))

    async def shutdown(self) -> None:
        if self.poll_task:
            self.poll_task.cancel()
            await asyncio.gather(self.poll_task, return_exceptions=True)
        for rt in list(self.runtimes.values()):
            await self.retire(rt)


async def _safe_send(ws: WebSocket, msg: dict) -> bool:
    try:
        await ws.send_json(msg)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


async def _pump_socket(ws: WebSocket, q: asyncio.Queue, receiver: asyncio.Task, on_item) -> None:
    """Forward queue items to the socket until the client leaves or the queue yields None."""
    while True:
        getter = asyncio.ensure_future(q.get())
        done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
        if getter not in done:
            getter.cancel()
            return
        item = getter.result()
        if item is None:
            return
        msg = on_item(item)
        if msg is not None and not await _safe_send(ws, msg):
            return


def create_app(*, registry: ColumnRegistry | None = None, session_factory: Callable | None = None,
               snapshotter: Callable | None = None, handoff_reader: Callable | None = None,
               clock: Callable[[], datetime] | None = None, history_dir: Path | None = None,
               history: HistoryStore | None = None, repos: list | None = None,
               allowed_hosts: set[str] | None = None, allowed_origins: set[str] | None = None,
               poll_seconds: float | None = None) -> FastAPI:
    if session_factory is None:
        def session_factory(repo_lines):
            cls = FakeClaudeSession if config.USE_FAKE_SESSIONS else ClaudeSession
            return cls(repo_lines)
    names = {config.HOST, "127.0.0.1", "localhost"}
    hosts = allowed_hosts if allowed_hosts is not None else {f"{n}:{config.PORT}" for n in names}
    origins = (allowed_origins if allowed_origins is not None
               else {f"http://{n}:{config.PORT}" for n in names})
    board = Board(
        registry=registry or ColumnRegistry(config.STATE_FILE),
        session_factory=session_factory, snapshotter=snapshotter or fetch_and_snapshot,
        handoff_reader=handoff_reader or read_handoff,
        clock=clock or (lambda: datetime.now(timezone.utc)),
        history=history or HistoryStore(history_dir), repos=repos if repos is not None else config.REPOS,
        poll_seconds=poll_seconds if poll_seconds is not None else config.HANDOFF_POLL_SECONDS)

    @asynccontextmanager
    async def lifespan(_app):
        board.poll_task = asyncio.create_task(board.poll())
        try:
            yield
        finally:
            await board.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.state.board = board

    def get_col(column_id: str) -> Column:
        try:
            return board.registry.get(column_id)
        except KeyError:
            raise HTTPException(404, "unknown column") from None

    @app.get("/api/columns")
    async def list_columns(include_closed: bool = False):
        return await board.columns_json(include_closed)

    @app.post("/api/columns", status_code=201)
    async def create_column(body: NewColumn):
        return await board.column_json(await board.create(body.title, body.request))

    @app.delete("/api/columns/{column_id}", status_code=204)
    async def delete_column(column_id: str):
        await board.close_column(get_col(column_id))
        return Response(status_code=204)

    @app.post("/api/columns/{column_id}/reopen")
    async def reopen_column(column_id: str):
        return await board.column_json(await board.reopen(get_col(column_id)))

    @app.websocket("/ws/columns/{column_id}")
    async def column_ws(ws: WebSocket, column_id: str, after: int = 0):
        try:
            col = board.registry.get(column_id)
        except KeyError:
            col = None
        if col is None or col.closed:
            await ws.close(code=CLOSE_NOT_FOUND)
            return
        rt = await board.primed(col)
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        rt.subscribers.add(q)  # subscribe BEFORE reading history: nothing can fall in the gap
        # No await since subscribing: every event with seq > top reaches q. Clamp `after` to the
        # stored max so a too-high value cannot make us drop later live events.
        top = board.history.next_seq(column_id) - 1
        after = min(after, top)
        receiver = asyncio.create_task(_receive_commands(ws, board, rt))
        try:
            stored = await asyncio.to_thread(board.history.read_after, column_id, after)
            last = after
            for ev in stored:
                if not await _safe_send(ws, {"kind": "event", "event": ev}):
                    return
                last = ev["seq"]

            def forward(item):
                nonlocal last
                if item["kind"] == "event":
                    if item["event"]["seq"] <= last:  # already replayed
                        return None
                    last = item["event"]["seq"]
                return item

            if not await _safe_send(ws, {"kind": "status", "status": await board.status_json(rt)}):
                return
            await board.ensure_session(rt)
            await _pump_socket(ws, q, receiver, forward)
        finally:
            rt.subscribers.discard(q)
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
            try:
                await ws.close()
            except RuntimeError:
                pass

    @app.websocket("/ws/board")
    async def board_ws(ws: WebSocket):
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        board.board_subs.add(q)
        receiver = asyncio.create_task(_drain_client(ws))
        try:
            if await _safe_send(ws, {"kind": "columns", "columns": await board.columns_json()}):
                await _pump_socket(ws, q, receiver, lambda m: m)
        finally:
            board.board_subs.discard(q)
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
            try:
                await ws.close()
            except RuntimeError:
                pass

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    guarded = OriginHostGuard(app, hosts, origins)
    guarded.board = board  # tests reach the board through the wrapper
    return guarded  # type: ignore[return-value]


async def _drain_client(ws: WebSocket) -> None:
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        return


async def _receive_commands(ws: WebSocket, board: Board, rt: Runtime) -> None:
    """Handle client commands. Returns when the client disconnects."""
    async def err(text: str) -> None:
        await _safe_send(ws, {"kind": "error", "error": text})

    while True:
        try:
            raw = await ws.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            return
        try:
            data = json.loads(raw)
            kind = data["type"]
        except (ValueError, KeyError, TypeError):
            await err("invalid message")
            continue
        if kind == "message":
            text = data.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > config.MAX_TEXT_CHARS:
                await err("invalid message text")
                continue
            problem = await board.on_message(rt, text)
            if problem:
                await err(problem)
        elif kind == "permission":
            rid, allow = data.get("request_id"), data.get("allow")
            if not isinstance(rid, str) or not isinstance(allow, bool):
                await err("invalid permission answer")
                continue
            await board.on_permission(rt, rid, allow)
        else:
            await err("unknown message type")


class _LazyApp:
    """`uvicorn server:app` target. Builds the real app on first request, not at import."""

    def __init__(self) -> None:
        self._app = None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = _LazyApp()

if __name__ == "__main__":
    import uvicorn

    assert_local_host(config.HOST)
    uvicorn.run(app, host=config.HOST, port=config.PORT)
