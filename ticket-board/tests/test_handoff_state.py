from pathlib import Path

from states.handoff_state import PHASES, parse_handoff, read_handoff

FIX = Path(__file__).parent / "fixtures"


def fx(name: str):
    return parse_handoff((FIX / name).read_text())


def test_empty_file_is_investigate():
    s = parse_handoff("")
    assert s.current_phase == "Investigate"
    assert s.completed == ()
    assert s.drafts == ()
    assert s.needs_user_reason is None


def test_placeholder_only_sections_count_as_empty():
    s = fx("placeholders_only.md")
    assert s.current_phase == "Investigate"
    assert s.drafts == ()


def test_digest_only_is_decide():
    s = parse_handoff("## Digest\n- a fact\n\n## Decision record\n<filled by linear-decide>\n")
    assert s.current_phase == "Decide"
    assert s.completed == ("Investigate",)


def test_drafts_in_review_need_user():
    s = fx("drafts_in_review.md")
    assert s.current_phase == "Draft"
    assert s.needs_user_reason == "approve drafts"
    assert [d.status for d in s.drafts] == ["in review", "approved"]
    assert s.completed == PHASES[:3]


def test_all_created_is_done_with_ids():
    s = fx("all_created.md")
    assert s.current_phase == "Done"
    assert s.completed == PHASES
    assert s.needs_user_reason is None
    assert [d.linear_id for d in s.drafts] == ["VIR-123", None]


def test_blocked_draft_reason():
    s = parse_handoff(_with_drafts("### T\n- status: blocked: waiting on requester\n- linear: none\n"))
    assert s.current_phase == "Draft"
    assert s.needs_user_reason == "answer needed from requester"


def test_approved_and_blocked_mixed_goes_to_create_and_asks_user():
    s = parse_handoff(
        _with_drafts("### A\n- status: approved\n### B\n- status: blocked: waiting on requester\n")
    )
    assert s.current_phase == "Create"
    assert s.needs_user_reason == "choose: create approved drafts now or wait for answers"


def test_blocked_status_text_is_normalized():
    s = parse_handoff(_with_drafts("### B\n- status: blocked: waiting on requester\n"))
    assert s.drafts[0].status == "blocked"
    s = parse_handoff(_with_drafts("### C\n- status: ???\n"))
    assert s.drafts[0].status == "in review"


def test_truncated_file_does_not_raise():
    full = (FIX / "drafts_in_review.md").read_text()
    for cut in range(0, len(full), 7):
        parse_handoff(full[:cut])
    parse_handoff("## Digest\nfact\n\n## Decis")


def test_free_form_file_parses_as_investigate():
    s = fx("free_form.md")
    assert s.current_phase == "Investigate"
    assert s.drafts == ()


def test_read_handoff_missing_returns_none(tmp_path):
    assert read_handoff(tmp_path / "nope.md") is None


def test_read_handoff_reads_file():
    assert read_handoff(FIX / "all_created.md").current_phase == "Done"


def _with_drafts(drafts: str) -> str:
    return "## Digest\nx\n## Decision record\nx\n## Shape\nx\n## Drafts\n" + drafts
