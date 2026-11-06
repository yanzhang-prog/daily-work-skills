"""Board columns: derived status (pure) and the persisted column registry."""

import json
import logging
import os
import re
import secrets
import shutil
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
log = logging.getLogger("ticket_board")


def as_utc(dt: datetime) -> datetime:
    """Naive datetimes (old files, hand edits) are taken as UTC so comparisons never raise."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


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
        silent = (as_utc(now) - as_utc(session.last_event_at)).total_seconds()
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
            created_at=as_utc(datetime.fromisoformat(d["created_at"])),
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
        """Never crash and never lose columns: a bad record is skipped (the rest load); a file
        that cannot be parsed at all is moved to a .bak BEFORE we start empty, so the next
        save cannot overwrite the only copy. A file with skipped records is copied to a .bak
        too, since the next save drops those records."""
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError:
            log.warning("column registry unreadable; starting empty")
            self._backup(move=True)
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
            records = data["columns"]
            if not isinstance(records, list):
                raise TypeError("columns is not a list")
        except (ValueError, KeyError, TypeError, AttributeError):  # UnicodeDecodeError is a ValueError
            log.warning("column registry is not valid JSON; moved aside, starting empty")
            self._backup(move=True)
            return {}
        cols: dict[str, Column] = {}
        bad = 0
        for d in records:
            try:
                c = Column.from_json(d)
            except (ValueError, KeyError, TypeError, AttributeError):
                bad += 1
                continue
            cols[c.id] = c
        if bad:
            log.warning("column registry: skipped %d malformed record(s)", bad)
            self._backup(move=False)
        return cols

    def _backup(self, move: bool) -> Path | None:
        bak = self._path.with_name(self._path.name + ".bak")
        if bak.exists():
            stamp = self._clock().strftime("%Y%m%dT%H%M%S%f")
            bak = self._path.with_name(f"{self._path.name}.{stamp}.bak")
            n = 1
            while bak.exists():
                bak = self._path.with_name(f"{self._path.name}.{stamp}-{n}.bak")
                n += 1
        try:
            if move:
                os.replace(self._path, bak)
            else:
                shutil.copy2(self._path, bak)
        except OSError:
            log.warning("column registry backup failed")
            return None
        return bak

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
