from states.history_state import HistoryStore


def ev(seq, text="x"):
    return {"seq": seq, "type": "assistant_text", "at": "2026-11-06T12:00:00+00:00", "text": text}


def test_seq_starts_at_one_and_survives_new_instance(tmp_path):
    a = HistoryStore(tmp_path)
    assert a.next_seq("c1") == 1
    a.append("c1", ev(1))
    a.append("c1", ev(a.next_seq("c1")))
    assert a.next_seq("c1") == 3
    b = HistoryStore(tmp_path)  # "restart"
    assert b.next_seq("c1") == 3
    assert b.next_seq("other") == 1


def test_read_after_returns_only_later_events_in_order(tmp_path):
    h = HistoryStore(tmp_path)
    for i in range(1, 6):
        h.append("c1", ev(i, f"t{i}"))
    assert [e["seq"] for e in h.read_after("c1", 2)] == [3, 4, 5]
    assert h.read_after("c1", 5) == []
    assert h.read_after("missing", 0) == []


def test_torn_last_line_ignored_and_not_glued_to_next_append(tmp_path):
    h = HistoryStore(tmp_path)
    h.append("c1", ev(1))
    with (tmp_path / "c1.jsonl").open("ab") as f:
        f.write(b'{"seq": 2, "type": "assist')  # crash mid-write
    h2 = HistoryStore(tmp_path)
    assert [e["seq"] for e in h2.read_after("c1")] == [1]
    assert h2.next_seq("c1") == 2
    h2.append("c1", ev(2, "after"))
    assert [(e["seq"], e["text"]) for e in HistoryStore(tmp_path).read_after("c1")] == [(1, "x"), (2, "after")]


def test_bad_column_id_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        HistoryStore(tmp_path).next_seq("../evil")
