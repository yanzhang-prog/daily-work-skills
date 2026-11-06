# Ticket Board

A localhost page that runs several Claude Code ticket-build sessions side by side, one per
column. Each column drives the `linear-workflow` skill (Investigate, Decide, Shape, Draft,
Create) and shows a status badge, a phase tracker and the repos it read.

## Install and start

    cd ticket-board
    uv sync
    uv run uvicorn server:app --host 127.0.0.1 --port 8765

Open http://127.0.0.1:8765. Environment switches:

- `TICKET_BOARD_FAKE=1`: fake sessions, no Claude calls (for UI work and tests).
- `TICKET_BOARD_DATA_DIR=<dir>`: keep all state under `<dir>` (`linear-work/`, `columns.json`,
  `history/`) instead of `~/.claude`. Use it for experiments.

Tunable settings (port, model, limits, repo list, tool allow/deny lists) are in `config.py`;
prompts are in `prompts.py`.

## Tests

    uv run pytest -q -W error
    node --test tests/js/board.test.mjs     # the directory form fails on Node 24
    bash ../global-skills/validate.sh

## Where state lives

- Columns and session ids: `~/.claude/ticket-board/columns.json`
- Chat history per column: `~/.claude/ticket-board/history/<id>.jsonl`
- Handoff files: `~/.claude/linear-work/` (the board tells each session the exact path)

Closing a column (X) keeps all three. `GET /api/columns?include_closed=true` lists closed
columns and `POST /api/columns/<id>/reopen` brings one back with its history. After a server
restart, columns show Stuck ("session not running") until you open them; then the session
resumes from its stored session id.

## Safety model

- Repos in `config.REPOS` are read-only. The board runs `git fetch origin` (never prunes, no
  gc/maintenance, no credential prompts) when a column starts; sessions read `origin/<default>`.
- Write tools for Slack, Notion, Gmail, Drive, Calendar and Claude Docs are hard-blocked, as
  are `git add`, `git clone` and package installs (also inside subagents).
- Only an explicit list of read tools is pre-approved, plus per session: exact per-repo
  `git -C <repo> show|grep|log|rev-parse ...`, `git -C <repo> fetch [origin]` and the
  origin/HEAD lookup, and a write rule for exactly that column's handoff file
  (`Edit(//<absolute path>)`, which also covers Write). Everything else, including every
  Linear write, raises a permission prompt shown as "Needs you". Sessions never skip permissions.
- Startup guard: with real sessions the server refuses to start if `~/.claude/settings.json`,
  `~/.claude/settings.local.json` or this repo's `.claude/settings*.json` pre-allow a Linear
  write tool (or all of `mcp__claude_ai_Linear`) or set `defaultMode` to `bypassPermissions`.
- Permission answers only count on the column that raised the request, and only while it is
  still pending; the page shows "Allowed"/"Denied" only after the server recorded the answer.
- The server binds to 127.0.0.1 and rejects foreign Host and Origin headers.
- Chat is rendered as plain text; errors are redacted before display.

## Status rules (short)

- Stuck (red): the session died, failed to start within `START_TIMEOUT_SECONDS`, hit an API
  error (auth, billing, rate limit), or was silent for `STUCK_AFTER_SECONDS`. An API error
  clears when you send the next message or the next turn finishes cleanly.
- If a stored session cannot be resumed, the board starts a fresh one that continues from the
  handoff file and says so in the column.

## Known limitations

- Chat is plain text (no Markdown rendering).
- Reads of a repo's files on disk (Read/Grep/Glob on a working tree) are allowed, because the
  skills live in this repo. They are labelled `working tree:` in the tool line but not
  blocked; "read `origin/<default>`" is enforced by the prompt only.
- `git show|grep|log` are allowed with any arguments. Some flags can run commands or write
  files (`git grep -O<cmd>`, `git log --output=<file>`, `--ext-diff`, `--textconv`); a prefix
  rule cannot exclude them. Text pulled from Slack, Linear or Notion could try to trick a
  session into using them (prompt injection). Only the prompt guards against this.
- The Host/Origin allow-list is tied to `config.PORT` (default 8765). Running uvicorn on
  another port returns 403 for everything; change `PORT` instead.
- History files (`history/<id>.jsonl`) grow without limit.
- A failed session is replaced only when you reconnect to the column or send it a message.
- The Repo prompt change in `global-skills/` must be installed with `global-skills/install.sh`
  before sessions see it.
- The handoff-file write rule and the per-repo git rules were checked against the bundled
  Claude Code CLI's rule syntax, not yet in a live session.
- A turn cut off by a server restart has no turn-finished event in the history.
- Headless Chrome screenshots: use `--timeout=8000`. With `--virtual-time-budget` the chat
  stays empty, because WebSocket traffic does not run in virtual time.
