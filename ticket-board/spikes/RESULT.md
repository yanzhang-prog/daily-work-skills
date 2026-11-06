# Spike result: can a server-started session use Yan's connectors?

Run: `uv run python spikes/connector_check.py` (SDK `claude-agent-sdk` 0.2.178+, Python 3.12). Read-only: `can_use_tool` denied every tool it was asked about.

## Verdict: (a) PASS, (b) PASS, (c) PASS, (d) PASS. One safety concern (see end).

| Q | Result | Evidence |
|---|--------|----------|
| (a) sees `linear-workflow` skills | PASS | `init` system message `skills` list: linear-create, linear-decide, linear-draft, linear-investigate, linear-shape, linear-workflow |
| (b) Linear / Slack / Notion read tools | PASS | Tool-use blocks seen: `mcp__claude_ai_Linear__list_teams` and `mcp__claude_ai_Slack__slack_search_public` (both reached `can_use_tool`, denied), `mcp__claude_ai_Notion__notion-search` (ran for real, returned 5 DoR pages, titles matched Yan's workspace, so the logged-in connector account is Yan's). Linear and Slack were attempted but denied by design, so access is shown by "tool exists and was called", not by results. |
| (c) `can_use_tool` can answer late | PASS | Callback awaited an `asyncio.Event` set 4 s later by another task. Logged waits: Linear 4.0 s, Slack 4.0 s. Session paused, then continued after the deny and the model reported the denial message. Two calls were issued in parallel and both waited. |
| (d) `resume=<session_id>` | PASS | New client with `resume=a6534dd8-...` (same id returned) answered: "Your first request was this: 'List the names of the Linear teams...'". |

## Real SDK option names (all worked as the plan guessed)
`ClaudeAgentOptions(setting_sources=["user","project"], cwd=<repo>, can_use_tool=<async fn>, resume=<session_id>)`. Also present: `add_dirs`, `permission_mode`, `allowed_tools`, `disallowed_tools`, `mcp_servers`, `fork_session`, `hooks`, `skills`, `agents`.
- `can_use_tool(tool_name, tool_input, context)` is async; return `PermissionResultDeny(message=...)` or `PermissionResultAllow`.
- Session id comes from `ResultMessage.session_id` (also in the `init` SystemMessage).
- `ClaudeSDKClient` as async context manager; `query()` then `receive_response()`.
- Message types seen: SystemMessage (init, commands_changed, thinking_tokens), HookEventMessage, RateLimitEvent, AssistantMessage (TextBlock, ThinkingBlock, ToolUseBlock), UserMessage (tool results), ResultMessage.

## Findings and caveats
1. **Connector tools are deferred.** The init `tools` list has no `mcp__` tools (30 total); the model fetched them with `ToolSearch` first (3 calls), then called them. Works, just adds a step.
2. **SAFETY: `can_use_tool` is NOT called for tools already allowed by settings.** `notion-search` never reached the callback because Yan's `~/.claude/settings.json` `permissions.allow` lists it. That file also pre-allows WRITE tools: `mcp__claude_ai_Notion__notion-create-pages`, `mcp__claude_ai_Notion__notion-update-page`, plus `Bash(git add:*)`, `Bash(git clone *)`, `Bash(pip install:*)`, `Read(//Users/yanzhang/**)`. With `setting_sources=["user", ...]` those bypass the callback, so a spike (or the board) cannot rely on the callback to block Notion writes. For the real board, the spec's approval gate for Linear is not affected (no Linear tool is pre-allowed), but consider `disallowed_tools` for unwanted writes, or dropping `"user"` from setting_sources only if skills can be supplied another way.
3. Warning printed at start: project `.claude/settings.json` `permissions.allow` (37 entries) ignored because the workspace is "not trusted" for non-interactive runs (`hasTrustDialogAccepted` not set in `~/.claude.json`). The user-level settings were honoured. Project-level allowances will not apply to the board's sessions unless that is set.
4. Project `.claude` hooks ran (6 hook start/response events per session start); harmless here but the board will see them.
5. Python: `uv init` picked 3.14; pinned to 3.12 (`.python-version`, `requires-python >=3.12`). `.venv` is not committed (no .gitignore was created by uv).
