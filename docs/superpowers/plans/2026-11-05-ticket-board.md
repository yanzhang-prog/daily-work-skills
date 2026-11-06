# Ticket Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A localhost web page that shows several Linear ticket builds side by side, one chat column each, with a status badge and phase tracker per column.

**Architecture:** A small Python server (FastAPI) starts one Claude Agent SDK session per column and streams its messages over a WebSocket to a plain HTML/JS page (no build step). Phase and status come from the handoff files in `~/.claude/linear-work/` plus live session flags. Repos are read through `git fetch` + `origin/<default branch>`, never `git pull`.

**Tech Stack:** Python 3.12, `uv`, FastAPI + uvicorn, `claude-agent-sdk`, pytest, vanilla JS/CSS.

**Spec:** `docs/superpowers/specs/2026-11-05-ticket-board-design.md`

## Global Constraints

- Everything lives in a new folder `ticket-board/` in this repo. Tests in `ticket-board/tests/`.
- Python backend rules from Yan's global instructions: prompts only in `ticket-board/prompts.py`; every tunable in `ticket-board/config.py`; state logic in `ticket-board/states/`; external calls (git, Claude SDK) only in `ticket-board/integrations/`.
- Server binds `127.0.0.1` only. Never `0.0.0.0`.
- Sessions never use `bypassPermissions` or any skip-permissions mode. Linear write tools are never pre-approved.
- Repos are read-only. Git use is limited to `fetch`, `show`, `grep`, `log`, `rev-parse`, `symbolic-ref`, `gh pr view`, `gh pr diff`. Never `pull`, `checkout`, `commit`, `push`.
- Initial repo list: `/Users/yanzhang/daily-work-skills` and `/Users/yanzhang/Desktop/virtual-assistant-agent`. Default branch comes from each repo's `origin/HEAD`, with an optional override.
- Closing a column never deletes its handoff file. Handoff dir is `~/.claude/linear-work/`.
- Status names exactly: **Working**, **Needs you**, **Done**, **Stuck**. Phases exactly: Investigate, Decide, Shape, Draft, Create.
- Page text sizes: ticket name 20px; badge, chat text, reply box 18px; phase tracker 15px; "Needs you" column has an orange border (`#e0a030`, 3px). Working is green, Done grey, Stuck red.
- The skills' own rules are unchanged. `global-skills/validate.sh` must still print `PASS: all skills valid`.
- Yan wants to understand the system: the executor explains each step's mechanism and alternatives as it goes. Commit only when Yan okays it, and never add a Co-Authored-By line.

## Review Focus

1. Handoff file missing, empty or half-written while a session is writing it: the tracker keeps working and shows the last known phase, never crashes. (Task 3)
2. `git fetch` fails (offline, expired credentials): the column says "not searched: <reason>" for that repo and never silently reads stale local files. (Task 4)
3. Two columns with the same ticket title: they get different ids and different handoff paths; closing one does not touch the other. (Task 7)
4. Page reload while a session is mid-reply: history is replayed once, no duplicated messages, status still correct. (Task 8)
5. Server restart with sessions in flight: columns come back as resumable, shown "Stuck" until the session answers, never "Working". (Task 7)

---

### Task 1: Spike — can a server-started session use Yan's connectors?

This is a gate. If it fails, stop and report to Yan. Do not build on a different design.

**Files:**
- Create: `ticket-board/pyproject.toml` (project `ticket-board`, Python `>=3.12`, deps `claude-agent-sdk`, `fastapi`, `uvicorn[standard]`; dev dep `pytest`, `pytest-asyncio`, `httpx`)
- Create: `ticket-board/spikes/connector_check.py` (throwaway, labelled as such)

**Interfaces:**
- Produces: a written answer in `ticket-board/spikes/RESULT.md` to four questions: (a) does a headless SDK session see the `linear-workflow` skills, (b) can it call a read-only Linear tool (`list_teams`), a Slack search and a Notion search, (c) does `can_use_tool` fire for an unlisted tool and can the answer be supplied later (not instantly), (d) does `resume=<session_id>` restore the earlier chat.

- [ ] **Step 1: Scaffold** with `cd ticket-board && uv init --no-readme` then `uv add` the deps above. Confirm `uv run python -c "import claude_agent_sdk"` succeeds.
- [ ] **Step 2: Write `connector_check.py`**: start a `ClaudeSDKClient` with `setting_sources=["user", "project"]`, `cwd` = this repo, and a `can_use_tool` callback that logs the tool name and denies it. Send: "List the names of the Linear teams you can see, then search Slack for 'eval' and Notion for 'DoR', one line each. Then list the skills available to you whose names start with linear-." Print every message type received.
- [ ] **Step 3: Run it** with `uv run python spikes/connector_check.py`. Expected for a pass: tool-use blocks for the three connectors appear (allowed or reaching the permission callback), and the skill list contains `linear-workflow`. Note that tools are denied by the callback, so a pass is "the tools exist and were attempted", which proves access without writing anything.
- [ ] **Step 4: Check resume**: store the `session_id` from the final result message, start a new client with `resume=<id>`, ask "what did I ask you first?". Expected: it answers from the earlier chat.
- [ ] **Step 5: Write `RESULT.md`** with pass/fail per question (a)–(d), the exact SDK option names that worked, and what failed. **If (b) fails, stop here and tell Yan.** If (c) or (d) fail, tell Yan too, because the permission-prompt and reopen behaviours in the spec depend on them.

### Task 2: Config and folder skeleton

**Files:**
- Create: `ticket-board/config.py`, `ticket-board/prompts.py`, `ticket-board/states/__init__.py`, `ticket-board/integrations/__init__.py`, `ticket-board/tests/__init__.py`, `ticket-board/README.md` (how to start; 10 lines)
- Modify: `/Users/yanzhang/daily-work-skills/.gitignore` (add `.superpowers/` and `ticket-board/.venv/`)
- Test: `ticket-board/tests/test_config.py`

**Interfaces:**
- Produces in `config.py`: `HOST: str = "127.0.0.1"`, `PORT: int = 8765`, `HANDOFF_DIR: Path`, `STATE_FILE: Path` (`~/.claude/ticket-board/columns.json`), `REPOS: list[RepoConfig]`, `STUCK_AFTER_SECONDS: int = 300`, `FETCH_TIMEOUT_SECONDS: int = 30`, `ALLOWED_TOOLS: list[str]` (read-only tools plus the git/gh patterns in Global Constraints, no Linear write tools), `MODEL_NAME: str`, and `@dataclass(frozen=True) class RepoConfig: path: Path; default_branch_override: str | None = None`.
- Produces in `prompts.py`: `COLUMN_REPO_CONTEXT_PROMPT: str`, a template with `{repo_list}` placeholder. Text states: these repos are readable; run `git fetch` first; read `origin/<default>` with `git show`/`git grep`, never the files on disk; look at a PR or branch only when Yan asks, and ask Yan when unsure; never edit a repo.

- [ ] **Step 1: Write the failing test** `test_config.py::test_server_binds_localhost_only` (`assert config.HOST == "127.0.0.1"`) and `test_allowed_tools_exclude_linear_writes` (no entry contains `save_issue`, `save_comment`, `save_document`, `delete_`).
- [ ] **Step 2: Run** `uv run pytest tests/test_config.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `config.py` and `prompts.py` as specified.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** (when Yan okays): `feat(ticket-board): config, prompts and skeleton`.

### Task 3: Handoff file parser

**Files:**
- Create: `ticket-board/states/handoff_state.py`
- Test: `ticket-board/tests/test_handoff_state.py`, fixtures in `ticket-board/tests/fixtures/` (copy the shape of `~/.claude/linear-work/2026-11-03-simple-eval-golden-answers-credit-note-fix.md`, with names changed)

**Interfaces:**
- Produces:
  - `PHASES: tuple[str, ...] = ("Investigate", "Decide", "Shape", "Draft", "Create")`
  - `@dataclass(frozen=True) class DraftInfo: title: str; status: str; linear_id: str | None` (status one of `in review`, `blocked`, `approved`, `created`)
  - `@dataclass(frozen=True) class HandoffSummary: current_phase: str` (a phase name or `"Done"`), `completed: tuple[str, ...]`, `drafts: tuple[DraftInfo, ...]`, `needs_user_reason: str | None`
  - `parse_handoff(text: str) -> HandoffSummary`
  - `read_handoff(path: Path) -> HandoffSummary | None` (returns `None` if the file is missing or unreadable)

Rules to implement (they mirror "Pick the phase" in `global-skills/linear-workflow/SKILL.md`): a section that holds only a `<filled by ...>` placeholder counts as empty; the current phase is the first phase whose section is empty (Digest→Investigate, Decision record→Decide, Shape→Shape, Drafts→Draft); drafts `approved` mean Create; every draft `created` means Done. `needs_user_reason` is `"approve drafts"` for `in review`, `"answer needed from requester"` for `blocked`, else `None`.

- [ ] **Step 1: Write failing tests**: `test_empty_file_is_investigate`, `test_placeholder_only_sections_count_as_empty`, `test_digest_only_is_decide`, `test_drafts_in_review_need_user`, `test_all_created_is_done_with_ids` (asserts `linear_id == "VIR-123"`), `test_blocked_draft_reason`, `test_truncated_file_does_not_raise` (file cut mid-heading), `test_read_handoff_missing_returns_none`.
- [ ] **Step 2: Run** `uv run pytest tests/test_handoff_state.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the parser: split on `^## ` headings, then `^### ` blocks under Drafts, reading `status:` and `linear:` lines.
- [ ] **Step 4: Run.** Expected: all PASS.
- [ ] **Step 5: Run the parser on the 10 real files** in `~/.claude/linear-work/` in a throwaway one-liner. Expected: none raise; report any file whose phase looks wrong to Yan.
- [ ] **Step 6: Commit** (when Yan okays).

### Task 4: Git repo integration

**Files:**
- Create: `ticket-board/integrations/git_repos.py`
- Test: `ticket-board/tests/test_git_repos.py` (builds temp git repos with a bare "origin")

**Interfaces:**
- Consumes: `config.RepoConfig`, `config.FETCH_TIMEOUT_SECONDS`.
- Produces:
  - `@dataclass(frozen=True) class RepoSnapshot: path: Path; ref: str | None; sha: str | None; committed_at: datetime | None; error: str | None`
  - `default_ref(repo: RepoConfig) -> str` (e.g. `origin/main`, from `git symbolic-ref refs/remotes/origin/HEAD`, or the override)
  - `fetch_and_snapshot(repo: RepoConfig) -> RepoSnapshot`; on failure returns `error="not searched: <reason>"` and `ref=None`
  - `describe(snapshot: RepoSnapshot) -> str` giving `"virtual-assistant-agent @ origin/main, 3 Nov"` (shown in the column)

- [ ] **Step 1: Write failing tests** `test_snapshot_reports_remote_main_not_stale_local`, `test_fetch_does_not_touch_checked_out_branch_or_dirty_files` (assert `HEAD` and `git status --porcelain` identical before and after), `test_default_branch_from_origin_head_not_assumed_main` (origin default `trunk`), `test_override_wins`, `test_fetch_failure_returns_not_searched`.
- [ ] **Step 2: Run** `uv run pytest tests/test_git_repos.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** with `subprocess.run([...], timeout=...)` and no shell; use only `git fetch --prune origin`, `git symbolic-ref`, `git rev-parse`, `git log -1 --format=%cI <ref>`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Run against the real virtual-assistant-agent clone** in a throwaway one-liner. Expected: `ref == "origin/main"`, and the repo's checked-out branch is unchanged afterwards (`git -C <repo> branch --show-current` before and after).
- [ ] **Step 6: Commit** (when Yan okays).

### Task 5: Repo-search prompt in the skill

**Files:**
- Modify: `global-skills/linear-investigate/references/source-prompts.md` (the "Repo" section only)
- Modify: `global-skills/required-phrases.txt` (add `linear-investigate|origin/` and `linear-investigate|git fetch`)

**Interfaces:**
- Consumes: the repo list and rules in `prompts.COLUMN_REPO_CONTEXT_PROMPT`.

- [ ] **Step 1: Add the failing phrases** to `required-phrases.txt`, run `bash global-skills/validate.sh`. Expected: FAIL naming the two missing phrases.
- [ ] **Step 2: Rewrite the Repo prompt** so it: searches the repos named in the session context (falling back to the current directory when none are named); runs `git fetch` first; reads `origin/<default branch>` instead of files on disk; searches a PR or branch only when the request names one; and returns `not searched: <reason>` per repo when fetch fails. Keep the 25-line digest rule and the `(team)`/`(private)` tags unchanged. Keep the file's other sections untouched.
- [ ] **Step 3: Run** `bash global-skills/validate.sh`. Expected: `PASS: all skills valid`.
- [ ] **Step 4: Dry run**: in the virtual-assistant-agent clone (currently on a feature branch), ask a Claude session to run the Repo prompt for a known file that differs between the branch and `origin/main`. Expected: the digest reflects `origin/main`.
- [ ] **Step 5: Commit** (when Yan okays).

### Task 6: Claude session wrapper

**Files:**
- Create: `ticket-board/integrations/claude_session.py`
- Test: `ticket-board/tests/test_claude_session.py` (fake client implementing the same async interface)

**Interfaces:**
- Consumes: `config.ALLOWED_TOOLS`, `config.REPOS`, `config.MODEL_NAME`, `prompts.COLUMN_REPO_CONTEXT_PROMPT`; the option names recorded in `ticket-board/spikes/RESULT.md`.
- Produces:
  - Event dataclasses (all frozen, each with `at: datetime`): `AssistantText(text: str)`, `ToolActivity(tool: str, summary: str)`, `PermissionRequest(request_id: str, tool: str, summary: str)`, `TurnFinished(session_id: str)`, `SessionError(message: str)`
  - `class ClaudeSession` with `async start(resume: str | None = None) -> None`, `async send(text: str) -> None`, `async answer_permission(request_id: str, allow: bool) -> None`, `events() -> AsyncIterator[Event]`, `async close() -> None`, property `session_id: str | None`
  - Permission rule: tools in `ALLOWED_TOOLS` are allowed at once; anything else becomes a `PermissionRequest` and waits for `answer_permission` with no timeout that auto-allows. The `can_use_tool` callback must never allow by default.

- [ ] **Step 1: Write failing tests**: `test_unlisted_tool_waits_for_answer`, `test_deny_is_returned_to_model`, `test_linear_write_tool_always_asks`, `test_turn_finished_carries_session_id`, `test_sdk_exception_becomes_session_error`.
- [ ] **Step 2: Run** `uv run pytest tests/test_claude_session.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `ClaudeSession` over `ClaudeSDKClient`, loading skills and CLAUDE.md with the setting that worked in Task 1, `cwd` = this repo, `add_dirs` = the other listed repos, and the system prompt addition from `COLUMN_REPO_CONTEXT_PROMPT` (formatted with the repo list).
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** (when Yan okays).

### Task 7: Column registry and status

**Files:**
- Create: `ticket-board/states/column_state.py`
- Test: `ticket-board/tests/test_column_state.py`

**Interfaces:**
- Consumes: `HandoffSummary` and `read_handoff` (Task 3), `config.STATE_FILE`, `config.STUCK_AFTER_SECONDS`, `config.HANDOFF_DIR`.
- Produces:
  - `class Status(StrEnum)`: `WORKING="working"`, `NEEDS_YOU="needs_you"`, `DONE="done"`, `STUCK="stuck"`
  - `@dataclass(frozen=True) class SessionFlags: alive: bool; waiting_for_reply: bool; pending_permission: str | None; last_event_at: datetime | None; error: str | None`
  - `@dataclass(frozen=True) class ColumnStatus: status: Status; note: str`
  - `derive_status(*, handoff: HandoffSummary | None, session: SessionFlags, now: datetime) -> ColumnStatus`
  - `@dataclass class Column: id: str; title: str; session_id: str | None; handoff_path: Path | None; repos_read: list[str]; created_at: datetime`
  - `class ColumnRegistry(path: Path)` with `add(title: str) -> Column`, `get(id: str) -> Column`, `list() -> list[Column]`, `close(id: str) -> None`, `update(column: Column) -> None`; persists to `STATE_FILE` as JSON after every change.

Precedence in `derive_status` (first match wins): dead session or `error` and not Done → **Stuck** (note: the error); `pending_permission` → **Needs you** ("allow <tool>?"); handoff phase `Done` → **Done** (note: created ticket ids); `waiting_for_reply` → **Needs you** (note: `needs_user_reason` or "waiting for your reply"); silent longer than `STUCK_AFTER_SECONDS` while working → **Stuck** ("no activity for N min"); otherwise **Working**.

- [ ] **Step 1: Write failing tests**: `test_permission_prompt_is_needs_you`, `test_all_created_is_done_with_ids`, `test_dead_session_is_stuck_not_working`, `test_silent_session_becomes_stuck`, `test_turn_finished_waiting_is_needs_you`, `test_permission_beats_done`, `test_two_columns_same_title_get_distinct_ids_and_paths`, `test_close_keeps_handoff_file` (file still exists), `test_registry_survives_restart_and_marks_session_not_alive`.
- [ ] **Step 2: Run** `uv run pytest tests/test_column_state.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the module as specified. Column ids are short random strings, never derived from the title alone.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** (when Yan okays).

### Task 8: Server

**Files:**
- Create: `ticket-board/server.py`
- Test: `ticket-board/tests/test_server.py` (FastAPI `TestClient`, a fake `ClaudeSession`)

**Interfaces:**
- Consumes: `ClaudeSession` (Task 6), `ColumnRegistry`, `derive_status` (Task 7), `fetch_and_snapshot`/`describe` (Task 4).
- Produces HTTP/WebSocket API used by the page:
  - `GET /api/columns` → list of `{id, title, status, note, phase, completed, repos_read}`
  - `POST /api/columns` body `{title, request}` → creates the column, runs `fetch_and_snapshot` for each repo, starts a session, sends `request` as the first message
  - `DELETE /api/columns/{id}` → closes the session and removes the column from the page; handoff file untouched
  - `WS /ws/columns/{id}` → on connect, replays stored history once, then streams events; accepts `{"type":"message","text":...}` and `{"type":"permission","request_id":...,"allow":bool}`
  - `WS /ws/board` → pushes the column list whenever any status changes
  - `GET /` and `/static/*` → the page (Task 9)
- Chat history per column is kept in memory in the server and persisted by Claude's own session file; on restart a column is listed as Stuck until `resume` succeeds (use `ClaudeSession.start(resume=...)` when the page first opens it).

- [ ] **Step 1: Write failing tests**: `test_create_column_fetches_repos_then_sends_request`, `test_close_does_not_delete_handoff_file`, `test_reconnect_replays_history_once_without_duplicates`, `test_permission_answer_reaches_session`, `test_status_push_on_change`, `test_server_refuses_non_local_host_config`.
- [ ] **Step 2: Run** `uv run pytest tests/test_server.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** with one asyncio task per column that reads `ClaudeSession.events()`, updates `SessionFlags` and re-derives the status, then pushes to subscribers. Re-read the handoff file whenever an event arrives and every 5 seconds (add `HANDOFF_POLL_SECONDS: int = 5` to `config.py`).
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** (when Yan okays).

### Task 9: The page

**Files:**
- Create: `ticket-board/static/index.html`, `ticket-board/static/app.js`, `ticket-board/static/style.css`

**Interfaces:**
- Consumes: the API from Task 8 exactly as listed.

Build from the approved mockup `.superpowers/brainstorm/35684-1793892691/content/layout-b-detail-v2.html`, using its layout and the sizes and colours in Global Constraints. Do not copy its markup. Required behaviour:
- Top bar: "Ticket Builder", count of open columns, count that need you, "+ New ticket".
- Column header: ticket name, ✕, status badge with note, phase tracker with ticks. Body: chat. Footer: reply box (Enter sends, Shift+Enter newline).
- A permission request renders as a message with Allow and Deny buttons.
- The repos read ("virtual-assistant-agent @ origin/main, 3 Nov") appear under the badge, small.
- New ticket opens a small form asking for a title and the request text.

- [ ] **Step 1: Write `app.js`** with one module per concern: `api.js`-style fetch helpers, column rendering, WebSocket handling. Keep each function short; explain the WebSocket reconnect logic in a comment.
- [ ] **Step 2: Serve and look.** Run `uv run uvicorn server:app --host 127.0.0.1 --port 8765`, open the page, create three columns with a stub session (use an env flag `TICKET_BOARD_FAKE=1` to start fake sessions emitting canned events). Expected: three columns side by side, one orange, text sizes as specified.
- [ ] **Step 3: Check against the mockup** with Yan looking at both. Expected: Yan agrees it matches.
- [ ] **Step 4: Commit** (when Yan okays).

### Task 10: End-to-end check with real sessions

**Files:**
- Modify: `ticket-board/README.md` (add start command, repo list location, how to reopen)

- [ ] **Step 1: Start the server** (no fake flag) and create one real column with a small, safe request such as "Investigate: add a README line about the board" and run it to the Draft phase. Expected: the tracker advances as the handoff file fills; the Repo digest names `origin/main` and the fetch time.
- [ ] **Step 2: Parallel check**: open two more columns while the first is working. Expected: all three update independently; the one that stops to ask turns orange.
- [ ] **Step 3: Approval gate check**: reach `linear-create` with approved drafts and **deny** the Linear write permission prompt. Expected: the prompt appears in the column as "Needs you"; denying creates nothing in Linear (confirm in Linear).
- [ ] **Step 4: Close and reopen**: close a column, reopen it from the list. Expected: chat history returns; the handoff file is still there.
- [ ] **Step 5: Restart check**: kill and restart the server mid-build. Expected: columns return as Stuck, then recover when resumed; none shows Working while dead.
- [ ] **Step 6: Report** to Yan what worked and what did not, with evidence. Run `bash global-skills/validate.sh` and the whole test suite (`uv run pytest -v`) first. Expected: all pass.
- [ ] **Step 7: Commit** (when Yan okays).
