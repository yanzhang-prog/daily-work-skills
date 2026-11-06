"""Append-only per-column event history (JSONL), so a page reload or server restart can replay it.

One file per column: <dir>/<column id>.jsonl, one JSON object per line, each with a per-column
`seq` that starts at 1 and only increases. A torn last line (crash mid-write) is ignored on read
and never glued to the next record on append.
"""
import json
from pathlib import Path

import config


class HistoryStore:
    def __init__(self, directory: Path | None = None):
        self._dir = Path(directory) if directory else config.HISTORY_DIR
        self._next: dict[str, int] = {}

    def _file(self, column_id: str) -> Path:
        if not column_id.isalnum():  # ids are hex; never let one escape the directory
            raise ValueError("bad column id")
        return self._dir / f"{column_id}.jsonl"

    def _scan(self, column_id: str) -> list[dict]:
        events = []
        try:
            with self._file(column_id).open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue  # torn or corrupt line
                    if isinstance(ev, dict) and isinstance(ev.get("seq"), int):
                        events.append(ev)
        except OSError:
            pass
        return events

    def next_seq(self, column_id: str) -> int:
        """The seq the next appended event gets. Cached after the first read of the file."""
        if column_id not in self._next:
            self._next[column_id] = max((e["seq"] for e in self._scan(column_id)), default=0) + 1
        return self._next[column_id]

    def append(self, column_id: str, event: dict) -> None:
        """Append an event that already carries its seq (from next_seq)."""
        path = self._file(column_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with path.open("ab+") as f:
            if f.tell() > 0:
                f.seek(-1, 2)
                if f.read(1) != b"\n":
                    f.write(b"\n")  # terminate a torn line so it cannot swallow this record
            f.write(line.encode("utf-8"))
        self._next[column_id] = max(self._next.get(column_id, 1), event["seq"] + 1)

    def read_after(self, column_id: str, after_seq: int = 0) -> list[dict]:
        return sorted((e for e in self._scan(column_id) if e["seq"] > after_seq), key=lambda e: e["seq"])
