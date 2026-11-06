# Ticket Board

A localhost page that runs several Claude Code sessions side by side, one per column.

1. `cd ticket-board && uv sync`
2. `uv run uvicorn server:app --host 127.0.0.1 --port 8765` (server arrives in a later task)
3. Open http://127.0.0.1:8765
4. Set `TICKET_BOARD_FAKE=1` to use fake sessions (no Claude calls).
5. Tune everything in `config.py`; prompts live in `prompts.py`.
6. Run tests: `uv run pytest`.

Sessions are read-only for repos. Linear writes always ask you first.
The server binds to 127.0.0.1 only.
