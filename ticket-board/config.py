"""All tunable settings for the ticket board. Nothing here is hardcoded elsewhere."""
import os
from dataclasses import dataclass
from pathlib import Path

# Server: localhost only, never 0.0.0.0.
HOST: str = "127.0.0.1"
PORT: int = 8765

# Test/dev switch: run fake sessions instead of real Claude sessions.
USE_FAKE_SESSIONS: bool = os.environ.get("TICKET_BOARD_FAKE") == "1"

HANDOFF_DIR: Path = Path.home() / ".claude" / "linear-work"
STATE_FILE: Path = Path.home() / ".claude" / "ticket-board" / "columns.json"

STUCK_AFTER_SECONDS: int = 300
FETCH_TIMEOUT_SECONDS: int = 30

MODEL_NAME: str = "claude-sonnet-5-5"


@dataclass(frozen=True)
class RepoConfig:
    path: Path
    default_branch_override: str | None = None


# Readable by sessions, never edited.
REPOS: list[RepoConfig] = [
    RepoConfig(Path("/Users/yanzhang/daily-work-skills")),
    RepoConfig(Path("/Users/yanzhang/Desktop/virtual-assistant-agent")),
]

def _mcp(prefix: str, names: str) -> list[str]:
    return [prefix + n for n in names.split()]


# Pre-approved (skip the permission prompt): read-only tools, read-only git/gh, and
# explicitly named read-only connector tools (no wildcards). Linear write tools are
# deliberately absent so they reach the permission prompt.
ALLOWED_TOOLS: list[str] = (
    ["Read", "Grep", "Glob", "ToolSearch", "Agent",
     "Bash(git fetch:*)", "Bash(git show:*)", "Bash(git grep:*)", "Bash(git log:*)",
     "Bash(git rev-parse:*)", "Bash(git symbolic-ref:*)",
     "Bash(gh pr view:*)", "Bash(gh pr diff:*)"]
    + _mcp("mcp__claude_ai_Linear__", """get_issue list_issues list_comments list_teams get_team
        list_users get_user whoami list_issue_labels list_issue_statuses get_issue_status
        list_projects get_project list_cycles list_documents get_document list_milestones
        get_milestone list_templates get_template get_attachment extract_images""")
    + _mcp("mcp__claude_ai_Slack__", """slack_read_channel slack_read_thread slack_search_public
        slack_search_public_and_private slack_search_channels slack_search_users
        slack_read_user_profile slack_read_file slack_read_canvas""")
    + _mcp("mcp__claude_ai_Notion__", """notion-search notion-fetch notion-connector-search
        notion-query-meeting-notes notion-query-data-sources notion-get-comments""")
    + _mcp("mcp__claude_ai_Google_Drive__",
           "search_files read_file_content get_file_metadata list_recent_files")
    + _mcp("mcp__claude_ai_Google_Calendar__", "list_events search_events get_event list_calendars")
)


# Hard-blocked even if the user's own settings pre-allow them. Linear is NOT here:
# Linear writes must reach the permission prompt, not be silently blocked.
DISALLOWED_TOOLS: list[str] = (
    ["Bash(git add:*)", "Bash(git clone *)", "Bash(pip install:*)", "Bash(pip3 install:*)",
     "Bash(python3 -m pip install:*)", "Bash(uv add:*)", "Bash(uv pip install:*)"]
    + _mcp("mcp__claude_ai_Slack__", """slack_add_list_record slack_add_reaction
        slack_complete_file_upload slack_create_canvas slack_create_conversation slack_create_list
        slack_get_file_upload_url slack_schedule_message slack_send_message slack_send_message_draft
        slack_update_canvas slack_update_list slack_update_list_record""")
    + _mcp("mcp__claude_ai_Notion__", """notion-calendar-cancel-events notion-calendar-create-events
        notion-calendar-update-events notion-convert-page-to-skill notion-create-attachment
        notion-create-comment notion-create-database notion-create-file-upload notion-create-folder
        notion-create-pages notion-create-suggested-edit notion-create-view notion-delete-comment
        notion-delete-databases notion-delete-pages notion-duplicate-page notion-move-pages
        notion-resolve-suggested-edit notion-restore-pages notion-send-message-to-session
        notion-set-comment-reaction notion-set-discussion-resolved notion-spawn-session
        notion-stop-session notion-update-comment notion-update-data-source notion-update-folder
        notion-update-page notion-update-view notion-upload-skill""")
    + _mcp("mcp__claude_ai_Gmail__", """apply_sensitive_message_label apply_sensitive_thread_label
        create_draft create_label delete_draft delete_label forward label_message label_thread
        mark_message_spam mark_thread_spam reply send_message trash_message trash_thread
        unlabel_message unlabel_thread unmark_message_spam unmark_thread_spam untrash_message
        untrash_thread update_draft update_label update_message_labels""")
    + _mcp("mcp__claude_ai_Google_Calendar__", "create_event delete_event respond_to_event update_event")
    + _mcp("mcp__claude_ai_Google_Drive__", "copy_file create_file share_file trash_file update_file")
    + _mcp("mcp__claude_ai_Claude_Docs__", "batch create delete update")
)


# Where sessions run (the repo holding the linear-* skills). Other REPOS are added as add_dirs.
SESSION_CWD: Path = Path("/Users/yanzhang/daily-work-skills")
