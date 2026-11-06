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

- Repos in `config.REPOS` are read-only: sessions read `origin/<default>` after `git fetch`.
- Write tools for Slack, Notion, Gmail, Drive, Calendar and Claude Docs are hard-blocked, as
  are `git add`, `git clone` and package installs (also inside subagents).
- Only an explicit list of read tools is pre-approved; everything else, including every Linear
  write, raises a permission prompt shown as "Needs you". Sessions never skip permissions.
- Permission answers only count on the column that raised the request.
- The server binds to 127.0.0.1 and rejects foreign Host and Origin headers.
- Chat is rendered as plain text; errors are redacted before display.

## Known limitations (seen in the end-to-end run)

- The handoff file write is not pre-approved. If it is outside the session's directories,
  Claude Code prompts "allow Write?" and the phase tracker only advances after you allow it.
- `git -C <repo> fetch` and `git -C <repo> show ...` do not match the allowed `git fetch:*` and
  `git show:*` patterns, and neither do piped or chained shell commands. Sessions that use
  those forms prompt for permission.
- A session resumed after a restart shows Working (no activity) until you send a message, and
  turns Stuck after `STUCK_AFTER_SECONDS`. A turn cut off by a restart has no turn-finished event.
- A client disconnect can log a harmless `WebSocketDisconnect` traceback from `ws.close()`.
- Headless Chrome with `--virtual-time-budget` shows an empty chat; use `--timeout=8000`.
