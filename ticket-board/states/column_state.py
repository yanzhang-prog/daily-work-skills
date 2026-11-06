"""Board columns: derived status (pure) and the persisted column registry."""

import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable

import config
from states.handoff_state import HandoffSummary

_NOTE_MAX = 120
_SLUG_MAX = 50


class Status(StrEnum):
    WORKING = "working"
    NEEDS_YOU = "needs_you"
    DONE = "done"
    STUCK = "stuck"


@dataclass(frozen=True)
class SessionFlags:
    alive: bool
    waiting_for_reply: bool
    pending_permission: str | None  # tool name being asked about
    last_event_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class ColumnStatus:
    status: Status
    note: str


def derive_status(
    *, handoff: HandoffSummary | None, session: SessionFlags, now: datetime
) -> ColumnStatus:
    """First match wins. A column restored from disk has no live session, so it
    is Stuck (never Working) unless its handoff already says Done."""
    done = handoff is not None and handoff.current_phase == "Done"

    if not done and (not session.alive or session.error):
        return ColumnStatus(Status.STUCK, (session.error or "")[:_NOTE_MAX] or "session not running")

    if session.pending_permission is not None:
        return ColumnStatus(Status.NEEDS_YOU, f"allow {session.pending_permission}?")

    if done:
        ids = [d.linear_id for d in handoff.drafts if d.linear_id]
        return ColumnStatus(Status.DONE, "created: " + ", ".join(ids) if ids else "done")

    if session.waiting_for_reply:
        reason = handoff.needs_user_reason if handoff else None
        return ColumnStatus(Status.NEEDS_YOU, reason or "waiting for your reply")

    if session.last_event_at is not None:
        silent = (now - session.last_event_at).total_seconds()
        if silent > config.STUCK_AFTER_SECONDS:
            return ColumnStatus(Status.STUCK, f"no activity for {max(1, int(silent // 60))} min")

    return ColumnStatus(Status.WORKING, f"working: {handoff.current_phase}" if handoff else "working")


@dataclass
class Column:
    id: str
    title: str
    session_id: str | None
    handoff_path: Path | None
    repos_read: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed: bool = False

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "session_id": self.session_id,
            "handoff_path": str(self.handoff_path) if self.handoff_path else None,
            "repos_read": list(self.repos_read),
            "created_at": self.created_at.isoformat(),
            "closed": self.closed,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Column":
        hp = d.get("handoff_path")
        repos = d.get("repos_read", [])
        if not isinstance(d["id"], str) or not isinstance(d["title"], str):
            raise ValueError("bad column")
        if not isinstance(repos, list):
            raise ValueError("bad repos_read")
        return cls(
            id=d["id"],
            title=d["title"],
            session_id=d.get("session_id"),
            handoff_path=Path(hp) if hp else None,
            repos_read=[str(r) for r in repos],
            created_at=datetime.fromisoformat(d["created_at"]),
            closed=bool(d.get("closed", False)),
        )


def slugify(title: str) -> str:
    """ASCII-only slug: safe in filenames. Non-ASCII letters collapse like punctuation."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:_SLUG_MAX].strip("-")
    return slug or "ticket"


class ColumnRegistry:
    def __init__(
        self,
        path: Path,
        clock: Callable[[], datetime] | None = None,
        handoff_dir: Path | None = None,
    ):
        self._path = Path(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._handoff_dir = Path(handoff_dir) if handoff_dir else config.HANDOFF_DIR
        self._columns: dict[str, Column] = self._load()

    def _load(self) -> dict[str, Column]:
        # Tolerant by design: a missing/corrupt file means "start empty", never a crash.
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            cols = [Column.from_json(d) for d in data["columns"]]
            return {c.id: c for c in cols}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {}

    def _save(self) -> None:
        # Temp file in the same directory + os.replace: the swap is atomic, so a
        # crash leaves either the old file or the new one, never half of one.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"columns": [c.to_json() for c in self._columns.values()]}, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".columns-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def add(self, title: str) -> Column:
        col_id = secrets.token_hex(4)
        while col_id in self._columns:
            col_id = secrets.token_hex(4)
        now = self._clock()
        name = f"{now.strftime('%Y-%m-%d')}-{slugify(title)}-{col_id}.md"
        col = Column(
            id=col_id,
            title=title,
            session_id=None,
            handoff_path=self._handoff_dir / name,
            repos_read=[],
            created_at=now,
        )
        self._columns[col_id] = col
        self._save()
        return col

    def get(self, id: str) -> Column:
        return self._columns[id]

    def list(self, include_closed: bool = False) -> list[Column]:
        return [c for c in self._columns.values() if include_closed or not c.closed]

    def close(self, id: str) -> None:
        """Hide the column. Never touches the handoff file."""
        self._columns[id].closed = True
        self._save()

    def reopen(self, id: str) -> Column:
        col = self._columns[id]
        col.closed = False
        self._save()
        return col

    def update(self, column: Column) -> None:
        if column.id not in self._columns:
            raise KeyError(column.id)
        self._columns[column.id] = column
        self._save()
