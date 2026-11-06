import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from states.column_state import (
    Column,
    ColumnRegistry,
    ColumnStatus,
    SessionFlags,
    Status,
    derive_status,
)
from states.handoff_state import DraftInfo, HandoffSummary

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def flags(**kw):
    base = dict(
        alive=True,
        waiting_for_reply=False,
        pending_permission=None,
        last_event_at=NOW,
        error=None,
    )
    base.update(kw)
    return SessionFlags(**base)


def handoff(phase="Draft", drafts=(), reason=None):
    return HandoffSummary(phase, (), tuple(drafts), reason)


def derive(h, s):
    return derive_status(handoff=h, session=s, now=NOW)


# ---------- derive_status ----------


def test_permission_prompt_is_needs_you():
    r = derive(handoff(), flags(pending_permission="mcp__linear__save_issue"))
    assert r == ColumnStatus(Status.NEEDS_YOU, "allow mcp__linear__save_issue?")


def test_all_created_is_done_with_ids():
    drafts = [
        DraftInfo("A", "created", "VA-1"),
        DraftInfo("B", "created", "VA-2"),
        DraftInfo("C", "created", None),
    ]
    r = derive(handoff("Done", drafts), flags())
    assert r.status is Status.DONE
    assert r.note == "created: VA-1, VA-2"


def test_done_without_ids_says_done():
    r = derive(handoff("Done", [DraftInfo("A", "created", None)]), flags())
    assert r == ColumnStatus(Status.DONE, "done")


def test_dead_session_is_stuck_not_working():
    r = derive(handoff("Shape"), flags(alive=False))
    assert r.status is Status.STUCK
    assert r.note == "session not running"


def test_error_is_stuck_with_truncated_note():
    r = derive(handoff(), flags(error="x" * 500))
    assert r.status is Status.STUCK
    assert r.note == "x" * 120


def test_silent_session_becomes_stuck():
    old = NOW - timedelta(seconds=config.STUCK_AFTER_SECONDS + 120)
    r = derive(handoff(), flags(last_event_at=old))
    assert r.status is Status.STUCK
    assert r.note == f"no activity for {(config.STUCK_AFTER_SECONDS + 120) // 60} min"


def test_recent_activity_is_not_stuck():
    recent = NOW - timedelta(seconds=config.STUCK_AFTER_SECONDS - 1)
    assert derive(handoff(), flags(last_event_at=recent)).status is Status.WORKING


def test_turn_finished_waiting_is_needs_you():
    r = derive(handoff(reason="approve drafts"), flags(waiting_for_reply=True))
    assert r == ColumnStatus(Status.NEEDS_YOU, "approve drafts")
    r = derive(handoff(reason=None), flags(waiting_for_reply=True))
    assert r == ColumnStatus(Status.NEEDS_YOU, "waiting for your reply")
    r = derive(None, flags(waiting_for_reply=True))
    assert r == ColumnStatus(Status.NEEDS_YOU, "waiting for your reply")


def test_permission_beats_done():
    r = derive(handoff("Done"), flags(pending_permission="Write"))
    assert r.status is Status.NEEDS_YOU
    assert r.note == "allow Write?"


def test_done_survives_dead_session():
    r = derive(handoff("Done", [DraftInfo("A", "created", "VA-9")]), flags(alive=False))
    assert r == ColumnStatus(Status.DONE, "created: VA-9")


def test_working_note_includes_phase():
    assert derive(handoff("Shape"), flags()) == ColumnStatus(Status.WORKING, "working: Shape")


def test_missing_handoff_is_working_not_crash():
    assert derive(None, flags()) == ColumnStatus(Status.WORKING, "working")


# ---------- registry ----------


def make_reg(tmp_path, clock=lambda: NOW):
    return ColumnRegistry(
        tmp_path / "state" / "columns.json", clock=clock, handoff_dir=tmp_path / "handoffs"
    )


def test_two_columns_same_title_get_distinct_ids_and_paths(tmp_path):
    reg = make_reg(tmp_path)
    a, b = reg.add("Same title"), reg.add("Same title")
    assert a.id != b.id
    assert a.handoff_path != b.handoff_path
    assert len(a.id) == 8
    assert a.handoff_path == tmp_path / "handoffs" / f"2026-11-06-same-title-{a.id}.md"
    assert a.created_at == NOW and a.session_id is None and a.repos_read == []
    assert a.closed is False


def test_slug_rules(tmp_path):
    reg = make_reg(tmp_path)

    def slug(title):
        c = reg.add(title)
        return c.handoff_path.name.removeprefix("2026-11-06-").removesuffix(f"-{c.id}.md")

    assert slug("  Fix: the (bug)!! in  VA/agent  ") == "fix-the-bug-in-va-agent"
    assert slug("Café résumé 日本語") == "caf-r-sum"
    assert slug("") == "ticket"
    assert slug("!!! ???") == "ticket"
    assert slug("日本語") == "ticket"
    long = slug("word " * 40)
    assert len(long) <= 50 and not long.endswith("-") and long.startswith("word-word")


def test_close_keeps_handoff_file(tmp_path):
    reg = make_reg(tmp_path)
    col = reg.add("Keep me")
    col.handoff_path.parent.mkdir(parents=True)
    col.handoff_path.write_text("# handoff", encoding="utf-8")
    reg.close(col.id)
    assert col.handoff_path.exists()
    assert col.handoff_path.read_text(encoding="utf-8") == "# handoff"
    assert reg.get(col.id).closed is True


def test_closed_columns_hidden_by_default_and_reopen_restores(tmp_path):
    reg = make_reg(tmp_path)
    a, b = reg.add("A"), reg.add("B")
    reg.close(a.id)
    assert [c.id for c in reg.list()] == [b.id]
    assert {c.id for c in reg.list(include_closed=True)} == {a.id, b.id}
    reopened = reg.reopen(a.id)
    assert reopened.closed is False
    assert [c.id for c in reg.list()] == [a.id, b.id]


def test_registry_survives_restart_and_marks_session_not_alive(tmp_path):
    reg = make_reg(tmp_path)
    col = reg.add("Restart")
    col.session_id = "sess-123"
    col.repos_read = ["daily-work-skills"]
    reg.update(col)
    reg.close(reg.add("Closed one").id)

    reg2 = make_reg(tmp_path)
    got = reg2.get(col.id)
    assert got.session_id == "sess-123"
    assert got.repos_read == ["daily-work-skills"]
    assert got.handoff_path == col.handoff_path
    assert got.created_at == NOW
    assert len(reg2.list(include_closed=True)) == 2
    # No live session after a restart: never Working while dead.
    r = derive(handoff("Shape"), flags(alive=False))
    assert r.status is Status.STUCK


def test_corrupt_state_file_starts_empty(tmp_path):
    path = tmp_path / "columns.json"
    for junk in ("", "{not json", "[1, 2]", '{"columns": [{"id": 1}]}'):
        path.write_text(junk, encoding="utf-8")
        reg = ColumnRegistry(path, handoff_dir=tmp_path)
        assert reg.list(include_closed=True) == []
    assert ColumnRegistry(tmp_path / "missing.json").list() == []
    # and it still works afterwards
    reg.add("fresh")
    assert len(ColumnRegistry(path, handoff_dir=tmp_path).list()) == 1


def test_state_is_written_atomically_no_partial_file(tmp_path):
    reg = make_reg(tmp_path)
    reg.add("one")
    reg.add("two")
    files = sorted(p.name for p in (tmp_path / "state").iterdir())
    assert files == ["columns.json"]
    data = json.loads((tmp_path / "state" / "columns.json").read_text(encoding="utf-8"))
    assert len(data["columns"]) == 2


def test_updates_persist(tmp_path):
    reg = make_reg(tmp_path)
    col = reg.add("Persist")
    col.session_id = "abc"
    col.title = "Renamed"
    reg.update(col)
    again = make_reg(tmp_path).get(col.id)
    assert again.session_id == "abc" and again.title == "Renamed"


def test_default_handoff_dir_comes_from_config(tmp_path):
    reg = ColumnRegistry(tmp_path / "c.json", clock=lambda: NOW)
    assert reg.add("x").handoff_path.parent == config.HANDOFF_DIR
