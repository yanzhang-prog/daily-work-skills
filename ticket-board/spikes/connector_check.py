"""THROWAWAY SPIKE - not part of the product.

Checks whether a server-started Claude Agent SDK session can see Yan's skills and
connectors, whether can_use_tool can answer late, and whether resume works.
READ-ONLY: can_use_tool denies every tool, after a deliberate delay.
"""
import asyncio
import time

from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKClient, PermissionResultDeny,
    AssistantMessage, ResultMessage, SystemMessage, UserMessage, ToolUseBlock, TextBlock,
)

REPO = "/Users/yanzhang/daily-work-skills"
DELAY = 4.0
calls: list[tuple[str, float]] = []


async def resolve_later(ev: asyncio.Event):
    await asyncio.sleep(DELAY)
    ev.set()


async def can_use_tool(name, tool_input, context):
    t0 = time.monotonic()
    print(f"  [can_use_tool] {name} -> waiting {DELAY}s before deny")
    ev = asyncio.Event()
    asyncio.create_task(resolve_later(ev))
    await ev.wait()
    calls.append((name, time.monotonic() - t0))
    return PermissionResultDeny(message="Spike is read-only; denied by design.")


def opts(**kw):
    return ClaudeAgentOptions(
        setting_sources=["user", "project"], cwd=REPO, can_use_tool=can_use_tool, **kw
    )


async def drain(client):
    sid = None
    async for m in client.receive_response():
        kind = type(m).__name__
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    print(f"{kind}: tool_use {b.name}")
                elif isinstance(b, TextBlock):
                    print(f"{kind}: text {b.text[:600]!r}")
                else:
                    print(f"{kind}: {type(b).__name__}")
        elif isinstance(m, ResultMessage):
            sid = m.session_id
            print(f"{kind}: session_id={sid} is_error={m.is_error} result={str(m.result)[:600]!r}")
        elif isinstance(m, SystemMessage):
            d = getattr(m, "data", {}) or {}
            print(f"{kind}: subtype={m.subtype} keys={list(d)[:8]}")
            if m.subtype == "init":
                tools = d.get("tools", [])
                print("   init tools (connector-ish):", [t for t in tools if t.startswith("mcp__")][:15], "total", len(tools))
                print("   init skills:", [s for s in d.get("skills", []) if "linear" in str(s)])
        else:
            print(kind)
    return sid


async def main():
    prompt = ("List the names of the Linear teams you can see, then search Slack for 'eval' and "
              "Notion for 'DoR', one line each. Then list the skills available to you whose names start with linear-.")
    async with ClaudeSDKClient(opts()) as c:
        await c.query(prompt)
        sid = await drain(c)
    print("\n=== can_use_tool calls (name, seconds waited) ===")
    for n, s in calls:
        print(f"  {n}: {s:.1f}s")
    print("\n=== RESUME ===")
    async with ClaudeSDKClient(opts(resume=sid)) as c:
        await c.query("What did I ask you first in this conversation?")
        await drain(c)


asyncio.run(main())
