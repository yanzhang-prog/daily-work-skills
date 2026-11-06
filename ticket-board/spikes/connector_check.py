"""THROWAWAY SPIKE - not part of the product.

Checks whether a server-started Claude Agent SDK session can see Yan's skills and
connectors, whether can_use_tool can answer late, and whether resume works.

What is enforced for read-only-ness (two layers, both needed):
  1. disallowed_tools (below) hard-blocks the write-style tools by name, including the
     ones Yan's ~/.claude/settings.json pre-allows (those skip can_use_tool).
  2. can_use_tool denies every tool that is NOT pre-allowed by settings, after a delay.
NOT enforced: pre-allowed READ tools (e.g. notion-search) still run for real, and any
write tool missing from the lists below that is pre-allowed would also run.
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


def _p(prefix, names):
    return [prefix + n for n in names]


DISALLOWED = (
    ["Bash", "Write", "Edit", "NotebookEdit",
     "Bash(git add:*)", "Bash(git clone *)", "Bash(pip install:*)", "Bash(pip3 install:*)"]
    + _p("mcp__claude_ai_Linear__", """create_attachment create_attachment_from_upload create_initiative_label
        create_issue_label delete_attachment delete_comment delete_customer delete_customer_need
        delete_diff_comment delete_status_update mark_notification merge_diff prepare_attachment_upload
        prepare_file_upload resolve_diff_thread restore_initiative_label restore_issue_label
        restore_project_label retire_initiative_label retire_issue_label retire_project_label
        save_comment save_customer save_customer_need save_diff_comment save_document save_initiative
        save_initiative_label save_issue save_issue_label save_milestone save_project save_project_label
        save_release save_release_note save_status_update share_issue submit_diff_review unshare_issue
        update_diff""".split())
    + _p("mcp__claude_ai_Slack__", """slack_add_list_record slack_add_reaction slack_complete_file_upload
        slack_create_canvas slack_create_conversation slack_create_list slack_get_file_upload_url
        slack_schedule_message slack_send_message slack_send_message_draft slack_update_canvas
        slack_update_list slack_update_list_record""".split())
    + _p("mcp__claude_ai_Notion__", """notion-calendar-cancel-events notion-calendar-create-events
        notion-calendar-update-events notion-convert-page-to-skill notion-create-attachment
        notion-create-comment notion-create-database notion-create-file-upload notion-create-folder
        notion-create-pages notion-create-suggested-edit notion-create-view notion-delete-comment
        notion-delete-databases notion-delete-pages notion-duplicate-page notion-move-pages
        notion-resolve-suggested-edit notion-restore-pages notion-send-message-to-session
        notion-set-comment-reaction notion-set-discussion-resolved notion-spawn-session
        notion-stop-session notion-update-comment notion-update-data-source notion-update-folder
        notion-update-page notion-update-view notion-upload-skill""".split())
    + _p("mcp__claude_ai_Gmail__", """apply_sensitive_message_label apply_sensitive_thread_label create_draft
        create_label delete_draft delete_label forward label_message label_thread mark_message_spam
        mark_thread_spam reply send_message trash_message trash_thread unlabel_message unlabel_thread
        unmark_message_spam unmark_thread_spam untrash_message untrash_thread update_draft update_label
        update_message_labels""".split())
    + _p("mcp__claude_ai_Google_Calendar__", "create_event delete_event respond_to_event update_event".split())
    + _p("mcp__claude_ai_Google_Drive__", "copy_file create_file share_file trash_file update_file".split())
    + _p("mcp__claude_ai_Claude_Docs__", "batch create delete update".split())
)


def opts(**kw):
    return ClaudeAgentOptions(
        setting_sources=["user", "project"], cwd=REPO, can_use_tool=can_use_tool,
        disallowed_tools=DISALLOWED, **kw
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
