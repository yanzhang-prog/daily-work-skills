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
    def __init__(self, options, script=None, raises=None):
        self.options = options
        self.script = script if script is not None else [result()]
        self.raises = raises
        self.queries = []
        self.disconnected = False

    async def connect(self):
        pass

    async def query(self, text):
        self.queries.append(text)

    async def receive_response(self):
        if self.raises:
            raise self.raises
        for m in self.script:
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
                               model="m"), result("abc-123")]
    s, c = await started(script=script)
    await s.send("hello")
    evs = [await next_event(s) for _ in range(3)]
    assert c.queries == ["hello"]
    assert isinstance(evs[0], AssistantText) and evs[0].text == "hi"
    assert isinstance(evs[1], ToolActivity) and evs[1].tool == "Read"
    assert isinstance(evs[2], TurnFinished) and evs[2].session_id == "abc-123"
    assert s.session_id == "abc-123"
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
    assert o.permission_mode not in ("bypassPermissions", "acceptEdits", "dontAsk", "auto")
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
