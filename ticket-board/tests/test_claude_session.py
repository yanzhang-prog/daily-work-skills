"""All tests use a fake client with the same async interface as ClaudeSDKClient. No network."""
import asyncio
from datetime import timezone

import pytest
from claude_agent_sdk import AssistantMessage, PermissionResultAllow, PermissionResultDeny, ResultMessage, TextBlock, ToolUseBlock

import config
from integrations.claude_session import (
    AssistantText, ClaudeSession, PermissionRequest, SessionError, ToolActivity, TurnFinished,
)

LINEAR_WRITE = "mcp__claude_ai_Linear__save_issue"


def result(sid="sid-1"):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                         num_turns=1, session_id=sid)


class FakeClient:
    def __init__(self, options, script=None, raises=None, delay=0, connect_raises=None):
        self.options = options
        self.delay = delay
        self.connect_raises = connect_raises
        self.current = None
        self.script = script if script is not None else [result()]
        self.raises = raises
        self.queries = []
        self.disconnected = False

    async def connect(self):
        if self.connect_raises:
            raise self.connect_raises

    async def query(self, text):
        self.queries.append(text)
        self.current = text

    async def receive_response(self):
        if self.raises:
            raise self.raises
        for m in self.script:
            await asyncio.sleep(self.delay)
            if isinstance(m, AssistantMessage):
                m = AssistantMessage(content=[TextBlock(f"{self.current}:{b.text}") if isinstance(b, TextBlock) else b for b in m.content], model="m")
            elif isinstance(m, ResultMessage):
                m = result(f"sid-{self.current}")
            yield m

    async def disconnect(self):
        self.disconnected = True


def make(**client_kw):
    holder = {}

    def factory(options):
        holder["client"] = FakeClient(options, **client_kw)
        return holder["client"]

    s = ClaudeSession(["virtual-assistant-agent: /x/va (read origin/main)"], client_factory=factory)
    return s, holder


async def started(**kw):
    s, holder = make(**kw)
    await s.start()
    return s, holder["client"]


async def next_event(s, timeout=1):
    return await asyncio.wait_for(anext(s.events()), timeout)


async def test_unlisted_tool_waits_for_answer():
    s, c = await started()
    task = asyncio.create_task(c.options.can_use_tool("WebFetch", {"url": "http://x"}, None))
    await asyncio.sleep(0.05)
    assert not task.done()
    req = await next_event(s)
    assert isinstance(req, PermissionRequest) and req.tool == "WebFetch"
    assert req.at.tzinfo == timezone.utc
    await s.answer_permission(req.request_id, True)
    assert isinstance(await asyncio.wait_for(task, 1), PermissionResultAllow)
    await s.close()


async def test_deny_is_returned_to_model():
    s, c = await started()
    task = asyncio.create_task(c.options.can_use_tool("WebFetch", {}, None))
    req = await next_event(s)
    await s.answer_permission(req.request_id, False)
    res = await asyncio.wait_for(task, 1)
    assert isinstance(res, PermissionResultDeny) and res.message
    await s.close()


async def test_linear_write_tool_always_asks():
    assert LINEAR_WRITE not in config.ALLOWED_TOOLS
    s, c = await started()
    task = asyncio.create_task(c.options.can_use_tool(LINEAR_WRITE, {"title": "T"}, None))
    req = await next_event(s)
    assert req.tool == LINEAR_WRITE
    assert not task.done()
    await s.answer_permission(req.request_id, False)
    assert isinstance(await asyncio.wait_for(task, 1), PermissionResultDeny)
    await s.close()


async def test_allowed_tool_is_allowed_at_once():
    assert "Read" in config.ALLOWED_TOOLS
    s, c = await started()
    res = await asyncio.wait_for(c.options.can_use_tool("Read", {"file_path": "/x"}, None), 1)
    assert isinstance(res, PermissionResultAllow)
    await s.close()


async def test_unknown_request_id_is_ignored_not_allowed():
    s, c = await started()
    task = asyncio.create_task(c.options.can_use_tool("WebFetch", {}, None))
    req = await next_event(s)
    await s.answer_permission("no-such-id", True)  # must not raise or release anything
    await asyncio.sleep(0.05)
    assert not task.done()
    await s.answer_permission(req.request_id, False)
    assert isinstance(await asyncio.wait_for(task, 1), PermissionResultDeny)
    await s.close()


async def test_close_denies_pending_requests():
    s, c = await started()
    tasks = [asyncio.create_task(c.options.can_use_tool(t, {}, None)) for t in ("WebFetch", LINEAR_WRITE)]
    await next_event(s)
    await next_event(s)
    await s.close()
    results = await asyncio.wait_for(asyncio.gather(*tasks), 1)
    assert len(results) == 2
    assert all(isinstance(r, PermissionResultDeny) and r.message for r in results)
    assert c.disconnected
    late = await c.options.can_use_tool("WebFetch", {}, None)
    assert isinstance(late, PermissionResultDeny)


async def test_turn_finished_carries_session_id():
    script = [AssistantMessage(content=[TextBlock("hi"), ToolUseBlock("t1", "Read", {"file_path": "/a"})],
                               model="m"), result()]
    s, c = await started(script=script)
    await s.send("hello")
    evs = [await next_event(s) for _ in range(3)]
    assert c.queries == ["hello"]
    assert isinstance(evs[0], AssistantText) and evs[0].text == "hello:hi"
    assert isinstance(evs[1], ToolActivity) and evs[1].tool == "Read"
    assert isinstance(evs[2], TurnFinished) and evs[2].session_id == "sid-hello"
    assert s.session_id == "sid-hello"
    await s.close()


async def test_sdk_exception_becomes_session_error_and_alive_false():
    s, c = await started(raises=RuntimeError("x" * 500))
    assert s.alive
    await s.send("hello")
    ev = await next_event(s)
    assert isinstance(ev, SessionError)
    assert ev.message.startswith("RuntimeError: ") and len(ev.message) == 300
    assert not s.alive
    # iterator still terminates on close
    collected = []

    async def drain():
        async for e in s.events():
            collected.append(e)

    t = asyncio.create_task(drain())
    await asyncio.sleep(0.05)
    await s.close()
    await asyncio.wait_for(t, 1)


async def test_options_use_disallowed_and_allowed_tools_and_no_bypass():
    s, c = await started()
    o = c.options
    assert config.DISALLOWED_TOOLS and config.ALLOWED_TOOLS
    assert o.disallowed_tools == config.DISALLOWED_TOOLS
    assert o.allowed_tools == config.ALLOWED_TOOLS
    assert o.permission_mode == "default"
    assert o.model == config.MODEL_NAME
    assert o.setting_sources == ["user", "project"]
    assert o.cwd == str(config.SESSION_CWD)
    assert o.add_dirs
    assert str(config.SESSION_CWD) not in o.add_dirs
    assert o.add_dirs == [str(r.path) for r in config.REPOS if r.path != config.SESSION_CWD]
    await s.close()


async def test_system_prompt_contains_repo_lines_and_git_fetch_rule():
    s, c = await started()
    sp = c.options.system_prompt
    assert sp["type"] == "preset" and sp["preset"] == "claude_code"
    assert "- virtual-assistant-agent: /x/va (read origin/main)" in sp["append"]
    assert "git fetch" in sp["append"]
    await s.close()


async def test_resume_passes_session_id_to_options():
    s, holder = make()
    await s.start(resume="old-session")
    assert holder["client"].options.resume == "old-session"
    await s.close()


async def test_permission_summary_is_truncated():
    s, c = await started()
    secret = "sk-SECRET-TOKEN"
    inp = {"title": "t" * 1000, "content": "FULLBODY" * 100, "api_token": secret}
    task = asyncio.create_task(c.options.can_use_tool(LINEAR_WRITE, inp, None))
    req = await next_event(s)
    assert len(req.summary) <= 200
    assert req.summary.startswith(LINEAR_WRITE)
    assert "FULLBODY" not in req.summary and secret not in req.summary
    await s.close()
    await asyncio.wait_for(task, 1)


from integrations.claude_session import summarize


async def test_two_quick_sends_are_serialized():
    script = [AssistantMessage(content=[TextBlock("a")], model="m"),
              AssistantMessage(content=[TextBlock("b")], model="m"), result()]
    s, c = await started(script=script, delay=0.02)
    await s.send("one")
    await s.send("two")
    evs = [await next_event(s, 3) for _ in range(6)]
    kinds = [(type(e).__name__, getattr(e, "text", None) or getattr(e, "session_id", None)) for e in evs]
    assert kinds == [("AssistantText", "one:a"), ("AssistantText", "one:b"), ("TurnFinished", "sid-one"),
                     ("AssistantText", "two:a"), ("AssistantText", "two:b"), ("TurnFinished", "sid-two")]
    assert c.queries == ["one", "two"]
    await s.close()


def test_summary_hides_body_but_shows_size_and_title():
    out = summarize(LINEAR_WRITE, {"title": "X", "description": "BODYTEXT" * 150, "teamId": "abc"})
    assert "title=X" in out and "description=1200 chars" in out
    assert "BODYTEXT" not in out


def test_summary_redacts_bearer_token():
    out = summarize("Bash", {"command": 'curl -H "Authorization: Bearer abc123" http://x'})
    assert "<redacted>" in out and "abc123" not in out


def test_summary_redacts_url_credentials():
    out = summarize("WebFetch", {"url": "https://user:pw123@host.example/p"})
    assert "<redacted>" in out and "pw123" not in out


def test_summary_nested_values_show_only_count():
    out = summarize("X", {"labels": ["a", "b"], "payload": {"secret": "hunter2", "k": 1}, "items": [1, 2, 3]})
    assert "payload=2 items" in out and "items=3 items" in out
    assert "hunter2" not in out


def test_summary_redacts_key_value_secret():
    out = summarize("Bash", {"command": "export API_KEY=sk-zzz && run"})
    assert "sk-zzz" not in out and "<redacted>" in out


async def test_close_is_idempotent_single_sentinel():
    s, c = await started()
    await s.close()
    await s.close()
    seen = [e async for e in s.events()]
    assert seen == []
    assert s._queue.empty()


async def test_send_after_close_emits_session_error():
    s, c = await started()
    await s.close()
    await s.send("hi")
    assert c.queries == []
    seen = [e async for e in s.events()]
    assert len(seen) == 1
    assert isinstance(seen[0], SessionError) and seen[0].message == "session is not running"


async def test_send_after_failure_emits_session_error():
    s, c = await started(raises=RuntimeError("boom"))
    await s.send("one")
    assert isinstance(await next_event(s), SessionError)
    await s.send("two")
    ev = await next_event(s)
    assert isinstance(ev, SessionError) and ev.message == "session is not running"
    await s.close()


async def test_start_failure_emits_error_and_events_end_on_close():
    s, holder = make(connect_raises=ConnectionError("no cli"))
    await s.start()
    assert not s.alive
    ev = await next_event(s)
    assert isinstance(ev, SessionError) and "ConnectionError" in ev.message
    await s.close()
    assert [e async for e in s.events()] == []
