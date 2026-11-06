import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import config
import server
from integrations.claude_session import (
    AssistantText, PermissionRequest, SessionError, ToolActivity, TurnFinished,
)
from integrations.git_repos import RepoSnapshot
from states.column_state import ColumnRegistry
from states.handoff_state import HandoffSummary
from states.history_state import HistoryStore

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
BASE = f"http://127.0.0.1:{config.PORT}"


class ScriptedSession:
    """Stands in for ClaudeSession. The test thread pushes events with push()."""

    def __init__(self, repo_lines, fail_start=False, send_raises=False, close_raises=False,
                 fail_resume=False, dead_on_resume=False):
        self.repo_lines = repo_lines
        self.fail_start = fail_start
        self.fail_resume = fail_resume
        self.dead_on_resume = dead_on_resume
        self.send_raises = send_raises
        self.close_raises = close_raises
        self.started = False
        self.resume = "unset"
        self.sent: list[str] = []
        self.answers: list[tuple[str, bool]] = []
        self.closed = False
        self.session_id = None
        self.alive = False
        self._q = None
        self._loop = None

    async def start(self, resume=None):
        self.resume = resume
        self._loop = asyncio.get_running_loop()
        self._q = asyncio.Queue()
        if self.fail_start:
            raise RuntimeError("boom token=abc123 /Users/yanzhang/x")
        if resume is not None and self.fail_resume:
            raise RuntimeError("No conversation found with session ID")
        self.started = True
        self.alive = not (resume is not None and self.dead_on_resume)

    async def send(self, text):
        if self.send_raises:
            raise RuntimeError("send failed api_key=sk-abc12345678")
        self.sent.append(text)

    async def answer_permission(self, request_id, allow):
        self.answers.append((request_id, allow))

    async def events(self):
        while True:
            ev = await self._q.get()
            if ev is None:
                return
            yield ev

    async def close(self):
        self.closed = True
        self.alive = False
        if self._q is not None:
            self._q.put_nowait(None)
        if self.close_raises:
            raise RuntimeError("close failed")

    def push(self, ev):
        self._loop.call_soon_threadsafe(self._q.put_nowait, ev)


def ok_snap(repo):
    return RepoSnapshot(repo.path, "origin/main", "abc", NOW, None)


class Harness:
    def __init__(self, tmp_path, snapshotter=ok_snap, handoff_reader=lambda p: None,
                 fail_start=False, history=None, send_raises=False, close_raises=False,
                 clock=lambda: NOW, poll_seconds=0.05, settings_paths=(), session_kw=None,
                 session_factory=None, **kw):
        self.tmp = tmp_path
        self.sessions: list[ScriptedSession] = []
        self.snap_calls = []
        self.factory_lines = []
        self.factory_handoffs = []
        self.session_kw = dict(session_kw or {})
        self.fail_start = fail_start
        self.loop_thread = None
        self.reader_threads = []
        user_reader = handoff_reader

        def reader(path):
            self.reader_threads.append(threading.get_ident())
            return user_reader(path)

        handoff_reader = reader

        def factory(repo_lines, handoff_path):
            self.loop_thread = threading.get_ident()  # factory runs on the event-loop thread
            self.factory_lines.append(repo_lines)
            self.factory_handoffs.append(handoff_path)
            if session_factory is not None:
                s = session_factory(repo_lines, handoff_path)
            else:
                s = ScriptedSession(repo_lines, fail_start=self.fail_start,
                                    send_raises=send_raises, close_raises=close_raises,
                                    **self.session_kw)
            self.sessions.append(s)
            return s

        def snap(repo):
            self.snap_calls.append(repo)
            return snapshotter(repo)

        self.registry = ColumnRegistry(tmp_path / "cols.json", clock=lambda: NOW,
                                       handoff_dir=tmp_path / "handoff")
        self.history_dir = tmp_path / "history"
        self.app = server.create_app(
            registry=self.registry, session_factory=factory, snapshotter=snap,
            handoff_reader=handoff_reader, clock=clock,
            history_dir=self.history_dir, history=history, poll_seconds=poll_seconds,
            settings_paths=list(settings_paths), **kw)

    def client(self):
        return TestClient(self.app, base_url=BASE)


def wsc(client, path, headers=None):
    # TestClient always dials ws://testserver, so set the Host a real browser would send.
    return client.websocket_connect(path, headers={"Host": f"127.0.0.1:{config.PORT}", **(headers or {})})


def wait_for(fn, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.01)
    raise AssertionError("condition not met in time")


def create(client, title="Add search", request="Build the search ticket"):
    r = client.post("/api/columns", json={"title": title, "request": request})
    assert r.status_code == 201, r.text
    return r.json()


def recv_until(ws, pred, limit=50):
    for _ in range(limit):
        m = ws.receive_json()
        if pred(m):
            return m
    raise AssertionError("expected message never arrived")


def status_of(client, cid):
    return next(c for c in client.get("/api/columns").json() if c["id"] == cid)


# ---------- create / list ----------

def test_create_column_fetches_repos_then_sends_request(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c, request="Build the search ticket")
        assert len(h.snap_calls) == len(config.REPOS)
        assert [r.path for r in h.snap_calls] == [r.path for r in config.REPOS]
        assert h.factory_lines == [[
            f"{r.path.name}: {r.path} (read origin/main)" for r in config.REPOS]]
        s = h.sessions[0]
        assert s.started and s.resume is None
        handoff = h.registry.get(col["id"]).handoff_path
        assert len(s.sent) == 1
        assert "Build the search ticket" in s.sent[0]
        assert str(handoff) in s.sent[0]
        assert col["repos_read"] == [f"{r.path.name} @ origin/main, 6 Nov" for r in config.REPOS]


def test_failed_fetch_does_not_fail_create(tmp_path):
    def bad(repo):
        return RepoSnapshot(repo.path, None, None, None, "not searched: git fetch failed (exit 1)")
    h = Harness(tmp_path, snapshotter=bad)
    with h.client() as c:
        col = create(c)
        assert all("not searched" in r for r in col["repos_read"])
        assert len(col["repos_read"]) == len(config.REPOS)
        assert all("(not searched: " in line for line in h.factory_lines[0])
        assert "not searched" in json.dumps(c.get("/api/columns").json())


def test_columns_json_shape(tmp_path):
    reader = lambda p: HandoffSummary("Shape", ("Investigate", "Decide"), (), None)
    h = Harness(tmp_path, handoff_reader=reader)
    with h.client() as c:
        col = create(c)
        rows = c.get("/api/columns").json()
        assert len(rows) == 1
        row = rows[0]
        assert set(row) == {"id", "title", "status", "label", "note", "phase",
                            "completed", "repos_read", "closed"}
        assert row["id"] == col["id"] and row["title"] == "Add search"
        assert row["status"] == "working" and row["label"] == "Working"
        assert row["phase"] == "Shape" and row["completed"] == ["Investigate", "Decide"]
        assert row["closed"] is False


def test_phase_defaults_to_investigate_without_handoff(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        create(c)
        row = c.get("/api/columns").json()[0]
        assert row["phase"] == "Investigate" and row["completed"] == []


def test_session_start_failure_listed_stuck(tmp_path):
    h = Harness(tmp_path, fail_start=True)
    with h.client() as c:
        col = create(c)
        row = status_of(c, col["id"])
        assert row["status"] == "stuck" and row["label"] == "Stuck"
        assert "boom" in row["note"]
        assert "Traceback" not in row["note"]


# ---------- close / reopen ----------

def test_close_does_not_delete_handoff_file_or_history(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        handoff = h.registry.get(col["id"]).handoff_path
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text("# handoff")
        hist = h.history_dir / f"{col['id']}.jsonl"
        assert hist.exists()
        assert c.delete(f"/api/columns/{col['id']}").status_code == 204
        assert h.sessions[0].closed
        assert handoff.read_text() == "# handoff"
        assert hist.exists()
        assert c.get("/api/columns").json() == []
        listed = c.get("/api/columns?include_closed=true").json()
        assert [r["closed"] for r in listed] == [True]
        assert c.delete("/api/columns/nope").status_code == 404


def test_reopen_resumes_with_stored_session_id(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(TurnFinished("sess-123", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-123")
        c.delete(f"/api/columns/{col['id']}")
        r = c.post(f"/api/columns/{col['id']}/reopen")
        assert r.status_code == 200 and r.json()["closed"] is False
        assert len(h.sessions) == 2
        assert h.sessions[1].resume == "sess-123" and h.sessions[1].started
        assert [x["id"] for x in c.get("/api/columns").json()] == [col["id"]]
        assert c.post("/api/columns/nope/reopen").status_code == 404


def test_reopen_without_session_id_is_stuck(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        c.delete(f"/api/columns/{col['id']}")
        r = c.post(f"/api/columns/{col['id']}/reopen")
        assert r.json()["status"] == "stuck" and r.json()["note"] == "no session to resume"
        assert len(h.sessions) == 1


# ---------- websocket history ----------

def test_replay_after_seq(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        for i in range(3):
            s.push(AssistantText(f"t{i}", NOW))
        wait_for(lambda: len(h.history_dir.joinpath(f"{col['id']}.jsonl").read_text().splitlines()) == 4)
        with wsc(c, f"/ws/columns/{col['id']}?after=2") as ws:
            seqs = []
            while True:
                m = ws.receive_json()
                if m["kind"] == "status":
                    break
                seqs.append(m["event"]["seq"])
        assert seqs == [3, 4]


def test_event_json_shape(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        s.push(ToolActivity("Read", "Read file_path=a", NOW))
        s.push(PermissionRequest("r1", "Bash", "Bash command=ls", NOW))
        s.push(TurnFinished("sid", NOW))
        s.push(SessionError("bad", NOW))
        wait_for(lambda: len(HistoryStore(h.history_dir).read_after(col["id"])) == 5)
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            evs = []
            while len(evs) < 5:
                m = ws.receive_json()
                if m["kind"] == "event":
                    evs.append(m["event"])
        assert [e["type"] for e in evs] == [
            "user_message", "tool_activity", "permission_request", "turn_finished", "session_error"]
        assert evs[0]["message"] == "Build the search ticket" or "search ticket" in evs[0]["message"]
        assert (evs[1]["tool"], evs[1]["summary"]) == ("Read", "Read file_path=a")
        assert (evs[2]["request_id"], evs[2]["tool"], evs[2]["summary"]) == ("r1", "Bash", "Bash command=ls")
        assert evs[3]["session_id"] == "sid" and evs[4]["message"] == "bad"
        assert [e["seq"] for e in evs] == [1, 2, 3, 4, 5]
        assert all(datetime.fromisoformat(e["at"]) for e in evs)


class GatedHistory(HistoryStore):
    """read_after blocks until released, so a live event can land mid-replay."""

    def __init__(self, d):
        super().__init__(d)
        self.entered = threading.Event()
        self.proceed = threading.Event()
        self.gate = False

    def read_after(self, column_id, after_seq=0):
        if self.gate:
            self.entered.set()
            assert self.proceed.wait(5)
        return super().read_after(column_id, after_seq)


def test_reconnect_replays_history_once_without_duplicates(tmp_path):
    hist = GatedHistory(tmp_path / "history")
    h = Harness(tmp_path, history=hist)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        s.push(AssistantText("one", NOW))
        s.push(AssistantText("two", NOW))
        wait_for(lambda: hist.next_seq(col["id"]) == 4)
        hist.gate = True
        with wsc(c, f"/ws/columns/{col['id']}?after=1") as ws:
            assert hist.entered.wait(3)
            # This event is stored AND broadcast while the replay read is still pending.
            s.push(AssistantText("during", NOW))
            wait_for(lambda: hist.next_seq(col["id"]) == 5)
            hist.proceed.set()
            s.push(AssistantText("after", NOW))
            seqs = []
            while len(seqs) < 4:
                m = ws.receive_json()
                if m["kind"] == "event":
                    seqs.append(m["event"]["seq"])
        assert seqs == [2, 3, 4, 5]  # each exactly once, in order


def test_history_survives_new_app_instance(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(AssistantText("persisted", NOW))
        wait_for(lambda: hist_len(h.history_dir, col["id"]) == 2)
    h2 = Harness(tmp_path)  # same registry file and history dir
    with h2.client() as c2:
        with wsc(c2, f"/ws/columns/{col['id']}") as ws:
            texts = []
            while len(texts) < 2:
                m = ws.receive_json()
                if m["kind"] == "event":
                    texts.append((m["event"]["seq"], m["event"].get("text") or m["event"].get("message")))
        assert texts[1] == (2, "persisted")
        # new events continue the sequence rather than restarting at 1
        h2.registry.update(h2.registry.get(col["id"]))
        assert h2.app is not h.app


def hist_len(d, cid):
    return len(HistoryStore(d).read_after(cid))


def test_first_ws_connect_resumes_session_lazily(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(TurnFinished("sess-9", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-9")
    h2 = Harness(tmp_path)  # restart: no live session
    with h2.client() as c2:
        assert status_of(c2, col["id"])["status"] == "stuck"
        assert h2.sessions == []
        with wsc(c2, f"/ws/columns/{col['id']}") as ws:
            wait_for(lambda: h2.sessions and h2.sessions[0].started)
            assert h2.sessions[0].resume == "sess-9"
            ws.send_json({"type": "message", "text": "hello again"})
            wait_for(lambda: h2.sessions[0].sent == ["hello again"])
        assert status_of(c2, col["id"])["status"] != "stuck"


def test_lazy_resume_failure_is_stuck_with_error(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(TurnFinished("sess-9", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-9")
    h2 = Harness(tmp_path, fail_start=True)
    with h2.client() as c2:
        with wsc(c2, f"/ws/columns/{col['id']}"):
            wait_for(lambda: status_of(c2, col["id"])["note"].startswith("RuntimeError"))
        row = status_of(c2, col["id"])
        assert row["status"] == "stuck" and "boom" in row["note"]


def test_ws_refused_for_closed_column(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        c.delete(f"/api/columns/{col['id']}")
        with pytest.raises(WebSocketDisconnect) as e:
            with wsc(c, f"/ws/columns/{col['id']}"):
                pass
        assert e.value.code == 4404
        with pytest.raises(WebSocketDisconnect) as e2:
            with wsc(c, "/ws/columns/unknown"):
                pass
        assert e2.value.code == 4404


# ---------- permissions ----------

def test_permission_answer_reaches_session(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            s.push(PermissionRequest("r1", "mcp__claude_ai_Linear__save_issue", "title=x", NOW))
            recv_until(ws, lambda m: m["kind"] == "event" and m["event"]["type"] == "permission_request")
            ws.send_json({"type": "permission", "request_id": "r1", "allow": True})
            ans = recv_until(ws, lambda m: m["kind"] == "event" and m["event"]["type"] == "permission_answer")
        assert s.answers == [("r1", True)]
        assert ans["event"]["request_id"] == "r1" and ans["event"]["allow"] is True


def test_permission_answer_for_unknown_request_ignored(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            ws.send_json({"type": "permission", "request_id": "ghost", "allow": True})
            ws.send_json({"type": "message", "text": "sync"})  # processed after the answer
            wait_for(lambda: "sync" in s.sent)
        assert s.answers == []
        types = [e["type"] for e in HistoryStore(h.history_dir).read_after(col["id"])]
        assert "permission_answer" not in types


def test_permission_answer_cannot_cross_columns(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        a = create(c, title="A")
        b = create(c, title="B")
        sa, sb = h.sessions
        sa.push(PermissionRequest("req-a", "mcp__claude_ai_Linear__save_issue", "t", NOW))
        wait_for(lambda: status_of(c, a["id"])["status"] == "needs_you")
        with wsc(c, f"/ws/columns/{b['id']}") as wsb:
            wsb.send_json({"type": "permission", "request_id": "req-a", "allow": True})
            wsb.send_json({"type": "message", "text": "sync"})
            wait_for(lambda: "sync" in sb.sent)
        assert sa.answers == [] and sb.answers == []
        assert status_of(c, a["id"])["status"] == "needs_you"  # still waiting on the human


# ---------- status ----------

def test_status_needs_you_while_permission_pending_and_working_after_answer(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        assert status_of(c, col["id"])["status"] == "working"
        s.push(PermissionRequest("r1", "mcp__claude_ai_Linear__save_issue", "title=x", NOW))
        wait_for(lambda: status_of(c, col["id"])["status"] == "needs_you")
        assert status_of(c, col["id"])["note"] == "allow mcp__claude_ai_Linear__save_issue?"
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            ws.send_json({"type": "permission", "request_id": "r1", "allow": True})
            wait_for(lambda: s.answers)
        wait_for(lambda: status_of(c, col["id"])["status"] == "working")


def test_status_push_on_change(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        with wsc(c, "/ws/board") as board:
            first = board.receive_json()
            assert first["kind"] == "columns"
            assert [(r["id"], r["status"]) for r in first["columns"]] == [(col["id"], "working")]
            h.sessions[0].push(TurnFinished("sid", NOW))
            m = recv_until(board, lambda m: m["columns"][0]["status"] == "needs_you")
            assert m["kind"] == "columns" and m["columns"][0]["label"] == "Needs you"


def test_column_ws_gets_status_message(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            h.sessions[0].push(TurnFinished("sid", NOW))
            m = recv_until(ws, lambda m: m["kind"] == "status" and m["status"]["status"] == "needs_you")
        assert set(m["status"]) == {"status", "label", "note", "phase", "completed"}


def test_user_message_flips_back_to_working_and_is_recorded(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        s.push(TurnFinished("sid", NOW))
        wait_for(lambda: status_of(c, col["id"])["status"] == "needs_you")
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            ws.send_json({"type": "message", "text": "go on"})
            wait_for(lambda: s.sent[-1:] == ["go on"])
        wait_for(lambda: status_of(c, col["id"])["status"] == "working")
        msgs = [e.get("message") for e in HistoryStore(h.history_dir).read_after(col["id"])
                if e["type"] == "user_message"]
        assert msgs[-1] == "go on"


def test_handoff_change_is_picked_up_by_poll(tmp_path):
    state = {"h": None}
    h = Harness(tmp_path, handoff_reader=lambda p: state["h"])
    with h.client() as c:
        col = create(c)
        with wsc(c, "/ws/board") as board:
            board.receive_json()
            state["h"] = HandoffSummary("Draft", ("Investigate", "Decide", "Shape"), (), None)
            m = recv_until(board, lambda m: m["columns"][0]["phase"] == "Draft")
        assert m["columns"][0]["completed"] == ["Investigate", "Decide", "Shape"]


# ---------- security ----------

def test_cross_origin_request_rejected(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        r = c.post("/api/columns", json={"title": "t", "request": "r"},
                   headers={"Origin": "http://evil.example"})
        assert r.status_code == 403
        assert h.sessions == [] and c.get("/api/columns").json() == []
        col = create(c)
        with pytest.raises(WebSocketDisconnect):
            with wsc(c, f"/ws/columns/{col['id']}",
                                     headers={"Origin": "http://evil.example"}):
                pass
        with pytest.raises(WebSocketDisconnect):
            with wsc(c, "/ws/board", headers={"Origin": f"http://127.0.0.1:{config.PORT + 1}"}):
                pass
        assert c.get("/api/columns", headers={"Origin": "null"}).status_code == 403


def test_foreign_host_header_rejected(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        assert c.get("/api/columns", headers={"Host": "evil.example:8765"}).status_code == 403
        assert c.get("/api/columns", headers={"Host": "127.0.0.1:9999"}).status_code == 403
        assert c.get("/", headers={"Host": "evil.example"}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with wsc(c, "/ws/board", headers={"Host": "evil.example:8765"}):
                pass


def test_localhost_origin_allowed(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        for origin in (f"http://127.0.0.1:{config.PORT}", f"http://localhost:{config.PORT}"):
            assert c.get("/api/columns", headers={"Origin": origin}).status_code == 200
        r = c.get("/api/columns", headers={"Host": f"localhost:{config.PORT}"})
        assert r.status_code == 200
        with wsc(c, "/ws/board", headers={"Origin": f"http://localhost:{config.PORT}"}) as ws:
            assert ws.receive_json()["kind"] == "columns"


def test_assert_local_host():
    for ok in ("127.0.0.1", "localhost", "::1"):
        server.assert_local_host(ok)
    for bad in ("0.0.0.0", "192.168.1.5", ""):
        with pytest.raises(ValueError):
            server.assert_local_host(bad)


# ---------- input validation / static ----------

def test_invalid_input_rejected(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        assert c.post("/api/columns", json={"title": "", "request": "x"}).status_code == 422
        assert c.post("/api/columns", json={"title": "x" * 121, "request": "x"}).status_code == 422
        assert c.post("/api/columns", json={"title": "x", "request": ""}).status_code == 422
        assert c.post("/api/columns", json={"title": "x", "request": "y" * 20001}).status_code == 422
        assert c.post("/api/columns", json={"title": "x"}).status_code == 422
        assert h.sessions == [] and h.registry.list(True) == []
        col = create(c)
        s = h.sessions[0]
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            ws.send_json({"type": "message", "text": ""})
            err = recv_until(ws, lambda m: m["kind"] == "error")
            assert err["error"]
            ws.send_json({"type": "message", "text": "y" * 20001})
            recv_until(ws, lambda m: m["kind"] == "error")
            ws.send_json({"type": "message", "text": "real"})
            wait_for(lambda: s.sent[-1:] == ["real"])
        assert s.sent == [s.sent[0], "real"]  # first message + the one valid one only


def test_index_and_static_served(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        r = c.get("/")
        assert r.status_code == 200 and "Ticket Board" in r.text
        assert c.get("/static/index.html").status_code == 200


# ---------- fix round 1 ----------

def history_text(h, cid):
    p = h.history_dir / f"{cid}.jsonl"
    return p.read_text() if p.exists() else ""


def test_replacing_dead_session_closes_old_and_stops_old_pump(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s0 = h.sessions[0]
        s0.push(TurnFinished("sess-1", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-1")
        old_task = h.app.board.runtimes[col["id"]].task
        s0.alive = False  # died without close(): its client would leak
        with wsc(c, f"/ws/columns/{col['id']}"):
            wait_for(lambda: len(h.sessions) == 2 and h.sessions[1].started)
        assert s0.closed is True
        wait_for(old_task.done)
        s0.push(AssistantText("stale-event", NOW))
        h.sessions[1].push(AssistantText("fresh-event", NOW))
        wait_for(lambda: "fresh-event" in history_text(h, col["id"]))
        assert "stale-event" not in history_text(h, col["id"])


def test_failed_start_closes_the_session(tmp_path):
    h = Harness(tmp_path, fail_start=True)
    with h.client() as c:
        create(c)
        assert h.sessions[0].closed is True


def test_start_failure_secrets_not_in_note_event_or_history(tmp_path):
    h = Harness(tmp_path, fail_start=True)
    with h.client() as c:
        col = create(c)
        assert "abc123" not in col["note"] and "abc123" not in status_of(c, col["id"])["note"]
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            m = recv_until(ws, lambda m: m["kind"] == "event" and m["event"]["type"] == "session_error")
        assert "abc123" not in json.dumps(m)
        assert "abc123" not in history_text(h, col["id"])
        assert "boom" in col["note"]


def test_session_error_event_message_is_redacted(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(SessionError("failed password=hunter2xyz here", NOW))
        wait_for(lambda: status_of(c, col["id"])["status"] == "stuck")
        assert "hunter2xyz" not in status_of(c, col["id"])["note"]
        assert "hunter2xyz" not in history_text(h, col["id"])


def test_handoff_reader_runs_off_the_event_loop_thread(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        create(c)
        c.get("/api/columns")
        time.sleep(0.2)  # let the poll run too
        assert h.reader_threads and h.loop_thread is not None
        assert all(t != h.loop_thread for t in h.reader_threads)


async def test_concurrent_record_keeps_seq_strictly_increasing(tmp_path):
    h = Harness(tmp_path)
    board = h.app.board
    col = h.registry.add("t")
    rt = await board.primed(col)

    async def writer(tag):
        for i in range(50):
            board.record(rt, "assistant_text", NOW, text=f"{tag}{i}")
            await asyncio.sleep(0)

    await asyncio.gather(writer("a"), writer("b"))
    seqs = [e["seq"] for e in HistoryStore(h.history_dir).read_after(col.id)]
    assert seqs == list(range(1, 101))


def test_after_beyond_stored_max_still_gets_live_events(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(AssistantText("one", NOW))
        wait_for(lambda: hist_len(h.history_dir, col["id"]) == 2)
        with wsc(c, f"/ws/columns/{col['id']}?after=999999") as ws:
            assert ws.receive_json()["kind"] == "status"  # replay was empty
            dog = threading.Timer(3, ws.close)  # watchdog: a dropped event must fail, not hang
            dog.start()
            try:
                h.sessions[0].push(AssistantText("live", NOW))
                m = ws.receive_json()
            finally:
                dog.cancel()
        assert m["kind"] == "event" and m["event"]["text"] == "live"


def test_send_failure_keeps_column_stuck_with_redacted_note(tmp_path):
    h = Harness(tmp_path, send_raises=True)
    with h.client() as c:
        r = c.post("/api/columns", json={"title": "t", "request": "r"})
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "stuck" and "sk-abc12345678" not in body["note"]
        assert "send failed" in body["note"]
        assert [x["id"] for x in c.get("/api/columns").json()] == [body["id"]]
        assert "sk-abc12345678" not in history_text(h, body["id"])


def test_column_shows_working_starting_while_repos_fetch(tmp_path):
    gate = threading.Event()
    h = Harness(tmp_path, snapshotter=lambda repo: (gate.wait(5), ok_snap(repo))[1])
    with h.client() as c:
        t = threading.Thread(target=lambda: c.post("/api/columns", json={"title": "t", "request": "r"}))
        t.start()
        try:
            row = wait_for(lambda: (c.get("/api/columns").json() or [None])[0])
            assert row["status"] == "working" and row["note"] == "starting..."
        finally:
            gate.set()
            t.join(5)
        assert status_of(c, row["id"])["note"] != "starting..."


def test_close_survives_session_close_failure(tmp_path):
    h = Harness(tmp_path, close_raises=True)
    with h.client() as c:
        col = create(c)
        assert c.delete(f"/api/columns/{col['id']}").status_code == 204
        assert c.get("/api/columns").json() == []
        assert h.registry.get(col["id"]).closed is True


# ---------- final fix wave ----------
from integrations.claude_session import ClaudeSession, SessionIdKnown, handoff_write_rule
from prompts import COLUMN_RESUME_FALLBACK_PROMPT


class HangConnectClient:
    """SDK client stand-in whose connect() never returns."""

    def __init__(self, options):
        self.options = options

    async def connect(self):
        await asyncio.Event().wait()

    async def disconnect(self):
        pass


def hung_claude_factory(repo_lines, handoff_path):
    return ClaudeSession(repo_lines, client_factory=HangConnectClient,
                         extra_allowed_tools=[handoff_write_rule(handoff_path)])


def history_events(h, cid):
    return HistoryStore(h.history_dir).read_after(cid)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


def with_watchdog(ws, fn, seconds=3):
    dog = threading.Timer(seconds, ws.close)  # a missing push must fail the test, not hang it
    dog.start()
    try:
        return fn()
    finally:
        dog.cancel()


# A1
def test_a1_hung_connect_becomes_stuck_within_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "START_TIMEOUT_SECONDS", 0.2)
    h = Harness(tmp_path, session_factory=hung_claude_factory)
    with h.client() as c:
        t0 = time.time()
        col = create(c)
        assert time.time() - t0 < 3
        row = status_of(c, col["id"])
        assert row["status"] == "stuck" and "TimeoutError" in row["note"]
        assert row["note"] != "starting..."


def test_a1_delete_returns_while_start_is_hung(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "START_TIMEOUT_SECONDS", 1.5)
    monkeypatch.setattr(config, "CLOSE_LOCK_TIMEOUT_SECONDS", 0.1)
    h = Harness(tmp_path, session_factory=hung_claude_factory)
    with h.client() as c:
        t = threading.Thread(target=lambda: c.post("/api/columns", json={"title": "t", "request": "r"}))
        t.start()
        try:
            row = wait_for(lambda: (c.get("/api/columns").json() or [None])[0])
            wait_for(lambda: h.sessions)  # the hung start is under way
            t0 = time.time()
            assert c.delete(f"/api/columns/{row['id']}").status_code == 204
            assert time.time() - t0 < 1.0  # did not wait for the 1.5 s start timeout
            assert h.registry.get(row["id"]).closed is True
        finally:
            t.join(5)
        assert not t.is_alive()
        rt = h.app.board.runtimes[row["id"]]
        assert rt.session is None and rt.task is None  # nothing left running on a closed column
        assert c.get("/api/columns").json() == []


def test_a1_server_bounds_a_session_start_that_ignores_its_own_timeout(tmp_path, monkeypatch):
    class Hangs(ScriptedSession):
        async def start(self, resume=None):
            await asyncio.Event().wait()

    monkeypatch.setattr(config, "START_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(server, "START_GRACE_SECONDS", 0.1)
    h = Harness(tmp_path, session_factory=lambda lines, hp: Hangs(lines))
    with h.client() as c:
        col = create(c)
        row = status_of(c, col["id"])
        assert row["status"] == "stuck" and "TimeoutError" in row["note"]


def test_a1_repo_fetch_is_bounded_while_starting(tmp_path, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(config, "SNAPSHOT_BUDGET_SECONDS", 0.2)
    h = Harness(tmp_path, snapshotter=lambda repo: (gate.wait(5), ok_snap(repo))[1])
    try:
        with h.client() as c:
            t0 = time.time()
            col = create(c)
            assert time.time() - t0 < 3
            assert all("not searched" in r and "timed out" in r for r in col["repos_read"])
            assert h.sessions and h.sessions[0].started  # the session still starts
            assert status_of(c, col["id"])["note"] != "starting..."
    finally:
        gate.set()


def test_a1_starting_flag_cannot_stick_when_publish_fails(tmp_path):
    calls = {"n": 0}

    def reader(p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk hiccup")
        return None

    h = Harness(tmp_path, handoff_reader=reader, poll_seconds=100)
    with h.client() as c:
        c.post("/api/columns", json={"title": "t", "request": "r"})
        cid = h.registry.list()[0].id
        assert h.app.board.runtimes[cid].starting is False
        assert status_of(c, cid)["note"] != "starting..."


# A2
def test_a2_auth_error_shows_stuck_not_waiting_and_next_message_clears(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        s.push(AssistantText("Invalid API key", NOW))
        s.push(SessionError("Claude API error: authentication_failed", NOW, fatal=False))
        s.push(TurnFinished("sid", NOW, is_error=True))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sid")
        row = status_of(c, col["id"])
        assert row["status"] == "stuck" and "authentication_failed" in row["note"]
        assert "waiting for your reply" not in row["note"]
        types = [e["type"] for e in history_events(h, col["id"])]
        assert "session_error" in types
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            ws.send_json({"type": "message", "text": "try again"})
            wait_for(lambda: s.sent[-1:] == ["try again"])
        row = status_of(c, col["id"])
        assert row["status"] == "working" and "authentication_failed" not in row["note"]


def test_a2_later_clean_turn_clears_recoverable_error(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        s.push(SessionError("turn failed (success, HTTP 429)", NOW, fatal=False))
        s.push(TurnFinished("sid", NOW, is_error=True))
        wait_for(lambda: status_of(c, col["id"])["status"] == "stuck")
        s.push(TurnFinished("sid", NOW, is_error=False))
        wait_for(lambda: status_of(c, col["id"])["status"] == "needs_you")
        assert status_of(c, col["id"])["note"] == "waiting for your reply"


def test_a2_fatal_error_is_not_cleared_by_a_clean_turn(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        s.push(SessionError("event stream broke", NOW))  # fatal by default
        s.push(TurnFinished("sid", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sid")
        assert status_of(c, col["id"])["status"] == "stuck"


# A3
def test_a3_poll_survives_an_exception_and_later_flags_silent_column(tmp_path):
    clock = Clock()
    state = {"raise": False, "raised": 0}

    def reader(p):
        if state["raise"]:
            state["raise"] = False
            state["raised"] += 1
            raise OSError("transient")
        return None

    h = Harness(tmp_path, handoff_reader=reader, clock=clock)
    with h.client() as c:
        col = create(c)
        with wsc(c, "/ws/board") as board:
            assert board.receive_json()["columns"][0]["status"] == "working"
            state["raise"] = True
            wait_for(lambda: state["raised"] == 1)
            clock.now = NOW + __import__("datetime").timedelta(seconds=config.STUCK_AFTER_SECONDS + 30)
            m = with_watchdog(board, lambda: recv_until(board, lambda m: m["columns"][0]["status"] == "stuck"))
        assert m["columns"][0]["id"] == col["id"] and "no activity" in m["columns"][0]["note"]


# A4
def test_a4_reopen_resume_shows_waiting_for_reply(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        assert status_of(c, col["id"])["status"] == "working"  # create() stays Working
        h.sessions[0].push(TurnFinished("sess-1", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-1")
        c.delete(f"/api/columns/{col['id']}")
        r = c.post(f"/api/columns/{col['id']}/reopen").json()
        assert (r["status"], r["note"]) == ("needs_you", "waiting for your reply")


def test_a4_lazy_resume_shows_waiting_for_reply(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(TurnFinished("sess-9", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-9")
    h2 = Harness(tmp_path)
    with h2.client() as c2:
        with wsc(c2, f"/ws/columns/{col['id']}") as ws:
            m = recv_until(ws, lambda m: m["kind"] == "status" and m["status"]["status"] == "needs_you")
        assert m["status"]["note"] == "waiting for your reply"


def test_a4_create_does_not_set_waiting(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        assert h.app.board.runtimes[col["id"]].waiting_for_reply is False


# A5
def test_a5_activity_of_a_later_turn_clears_waiting(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        s.push(TurnFinished("sid", NOW))
        wait_for(lambda: status_of(c, col["id"])["status"] == "needs_you")
        s.push(AssistantText("next turn already running", NOW))  # queued message's turn
        wait_for(lambda: status_of(c, col["id"])["status"] == "working")
        s.push(TurnFinished("sid", NOW))
        wait_for(lambda: status_of(c, col["id"])["status"] == "needs_you")
        s.push(ToolActivity("Read", "Read file_path=x", NOW))
        wait_for(lambda: status_of(c, col["id"])["status"] == "working")


# B2
def _closed_with_session_id(c, h, sid="sess-old"):
    col = create(c)
    h.sessions[0].push(TurnFinished(sid, NOW))
    wait_for(lambda: h.registry.get(col["id"]).session_id == sid)
    c.delete(f"/api/columns/{col['id']}")
    return col


@pytest.mark.parametrize("knob", ["fail_resume", "dead_on_resume"])
def test_b2_reopen_falls_back_to_fresh_session_from_handoff(tmp_path, knob):
    h = Harness(tmp_path, session_kw={knob: True})
    with h.client() as c:
        col = _closed_with_session_id(c, h)
        r = c.post(f"/api/columns/{col['id']}/reopen").json()
        assert len(h.sessions) == 3
        failed, fresh = h.sessions[1], h.sessions[2]
        assert failed.resume == "sess-old" and failed.closed
        assert fresh.resume is None and fresh.started and fresh.alive
        path = h.registry.get(col["id"]).handoff_path
        assert fresh.sent == [COLUMN_RESUME_FALLBACK_PROMPT.format(handoff_path=path)]
        assert str(path) in fresh.sent[0]
        notes = [e for e in history_events(h, col["id"]) if e["type"] == "system_note"]
        assert [n["message"] for n in notes] == [
            "Could not resume the previous session; started a new one from the handoff file."]
        assert r["status"] == "working"


def test_b2_lazy_resume_falls_back_too(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(TurnFinished("sess-9", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-9")
    h2 = Harness(tmp_path, session_kw={"fail_resume": True})
    with h2.client() as c2:
        with wsc(c2, f"/ws/columns/{col['id']}"):
            wait_for(lambda: len(h2.sessions) == 2 and h2.sessions[1].sent)
        assert h2.sessions[1].resume is None
        assert "could not be resumed" in h2.sessions[1].sent[0]
        assert any(e["type"] == "system_note" for e in history_events(h2, col["id"]))


# B3
def test_b3_session_id_persisted_at_first_event_survives_restart(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        h.sessions[0].push(SessionIdKnown("early-sid", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "early-sid")
    restarted = ColumnRegistry(tmp_path / "cols.json", handoff_dir=tmp_path / "handoff")
    assert restarted.get(col["id"]).session_id == "early-sid"
    assert "turn_finished" not in [e["type"] for e in history_events(h, col["id"])]


# B4
def test_b4_message_to_dead_session_resumes_then_sends(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s0 = h.sessions[0]
        s0.push(TurnFinished("sess-4", NOW))
        wait_for(lambda: h.registry.get(col["id"]).session_id == "sess-4")
        s0.alive = False
        s0.push(SessionError("RuntimeError: turn failed", NOW))
        wait_for(lambda: status_of(c, col["id"])["status"] == "stuck")
        h.app.board.runtimes[col["id"]].primed = True
        # connect AFTER death would resume lazily; simulate a socket opened before the death
        rt = h.app.board.runtimes[col["id"]]

        async def go():
            return await h.app.board.on_message(rt, "are you there?")

        problem = c.portal.call(go)
        assert problem is None
        assert len(h.sessions) == 2 and h.sessions[1].resume == "sess-4"
        assert h.sessions[1].sent == ["are you there?"]
        assert status_of(c, col["id"])["status"] == "working"


# C1 (server side)
def test_c1_unknown_or_answered_permission_gets_error_frame(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            ws.send_json({"type": "permission", "request_id": "ghost", "allow": True})
            err = recv_until(ws, lambda m: m["kind"] == "error")
            assert err["error"] == "permission request no longer pending"
            s.push(PermissionRequest("r1", "Bash", "Bash command=ls", NOW))
            recv_until(ws, lambda m: m["kind"] == "event" and m["event"]["type"] == "permission_request")
            ws.send_json({"type": "permission", "request_id": "r1", "allow": False})
            recv_until(ws, lambda m: m["kind"] == "event" and m["event"]["type"] == "permission_answer")
            ws.send_json({"type": "permission", "request_id": "r1", "allow": True})  # second answer
            err2 = recv_until(ws, lambda m: m["kind"] == "error")
            assert err2["error"] == "permission request no longer pending"
        assert s.answers == [("r1", False)]
        answers = [e for e in history_events(h, col["id"]) if e["type"] == "permission_answer"]
        assert len(answers) == 1


def test_c1_status_messages_carry_pending_ids(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        s = h.sessions[0]
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            first = recv_until(ws, lambda m: m["kind"] == "status")
            assert first["pending"] == []
            s.push(PermissionRequest("r1", "Bash", "x", NOW))
            m = recv_until(ws, lambda m: m["kind"] == "status" and m["pending"])
            assert m["pending"] == ["r1"]
        with wsc(c, f"/ws/columns/{col['id']}") as ws2:  # replay completion
            done = recv_until(ws2, lambda m: m["kind"] == "status")
            assert done["pending"] == ["r1"]


# C2
async def test_c2_retire_during_publish_await_gives_error_not_exception(tmp_path):
    h = Harness(tmp_path)
    board = h.app.board
    col = h.registry.add("t")
    rt = await board.primed(col)
    s = ScriptedSession([])
    await s.start()

    async def retiring_publish(rt_):
        rt_.session = None  # retire() ran while we were awaiting
        s.alive = False

    board.publish = retiring_publish
    rt.session = s
    assert await board.on_message(rt, "hi") == "session is not running"  # no AttributeError
    s.alive = True
    rt.session = s
    rt.pending["r1"] = "Bash"
    assert await board.on_permission(rt, "r1", True) == "session is not running"
    assert s.sent == [] and s.answers == []  # nothing went to a retired session


def test_c2_retire_during_message_sends_error_frame(tmp_path):
    h = Harness(tmp_path)
    with h.client() as c:
        col = create(c)
        board = h.app.board
        real_publish = board.publish

        async def retiring_publish(rt_):
            await board.retire(rt_)
            await real_publish(rt_)

        board.publish = retiring_publish
        with wsc(c, f"/ws/columns/{col['id']}") as ws:
            recv_until(ws, lambda m: m["kind"] == "status")
            ws.send_json({"type": "message", "text": "hello"})
            err = recv_until(ws, lambda m: m["kind"] == "error")
        assert err["error"] == "session is not running"


# C3
async def test_c3_safe_close_swallows_disconnect():
    class WS:
        def __init__(self, exc):
            self.exc = exc

        async def close(self, code=1000):
            raise self.exc

    for exc in (WebSocketDisconnect(1006), RuntimeError("closed"), OSError("gone")):
        await server._safe_close(WS(exc))  # must not raise


def test_c3_endpoints_use_safe_close():
    import inspect
    src = inspect.getsource(server.create_app)
    assert src.count("await _safe_close(ws)") == 2
    assert "await ws.close()" not in src


# D5
def _bad_settings(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"permissions": {"allow": ["mcp__claude_ai_Linear__save_issue"]}}))
    return p


def test_d5_server_refuses_to_start_with_unsafe_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USE_FAKE_SESSIONS", False)
    h = Harness(tmp_path, settings_paths=[_bad_settings(tmp_path)])
    with pytest.raises(RuntimeError) as e:
        with h.client():
            pass
    assert "mcp__claude_ai_Linear__save_issue" in str(e.value)
    c = h.client()  # lifespan never ran: creating a column must still be refused
    r = c.post("/api/columns", json={"title": "t", "request": "r"})
    assert r.status_code == 503 and h.sessions == []


def test_d5_clean_settings_start_normally(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USE_FAKE_SESSIONS", False)
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps({"permissions": {"allow": ["Read"]}}))
    h = Harness(tmp_path, settings_paths=[clean, tmp_path / "missing.json"])
    with h.client() as c:
        create(c)


def test_d5_fake_sessions_skip_the_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USE_FAKE_SESSIONS", True)
    h = Harness(tmp_path, settings_paths=[_bad_settings(tmp_path)])
    with h.client() as c:
        create(c)


# R21 wiring: the default factory gives each session exactly its own handoff rule
def test_r21_default_factory_passes_the_column_handoff_rule(tmp_path, monkeypatch):
    made = []

    class Recorder(ScriptedSession):
        def __init__(self, repo_lines, extra_allowed_tools=None):
            super().__init__(repo_lines)
            self.extra = extra_allowed_tools
            made.append(self)

    monkeypatch.setattr(config, "USE_FAKE_SESSIONS", False)
    monkeypatch.setattr(server, "ClaudeSession", Recorder)
    reg = ColumnRegistry(tmp_path / "cols.json", handoff_dir=tmp_path / "handoff")
    app = server.create_app(registry=reg, snapshotter=ok_snap, handoff_reader=lambda p: None,
                            history_dir=tmp_path / "history", settings_paths=[], poll_seconds=100)
    with TestClient(app, base_url=BASE) as c:
        a, b = create(c, title="A"), create(c, title="B")
    assert [m.extra for m in made] == [
        [handoff_write_rule(reg.get(a["id"]).handoff_path)],
        [handoff_write_rule(reg.get(b["id"]).handoff_path)]]
    assert made[0].extra != made[1].extra
