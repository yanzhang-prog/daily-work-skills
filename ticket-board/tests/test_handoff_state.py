import re
from pathlib import Path

from states.handoff_state import PHASES, parse_handoff, read_handoff

FIX = Path(__file__).parent / "fixtures"


def fx(name: str):
    return parse_handoff((FIX / name).read_text(encoding="utf-8"))


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
    full = (FIX / "drafts_in_review.md").read_text(encoding="utf-8")
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


def _scaffold() -> str:
    return (FIX / "template_scaffold.md").read_text(encoding="utf-8")


def _fill(text: str, heading: str, content: str) -> str:
    """Replace the `<filled by ...>` line under heading; leave scaffold bullets."""
    pat = re.compile(rf"(## {heading}\n)<filled by [^\n]*>", re.M)
    assert pat.search(text)
    return pat.sub(lambda m: m.group(1) + content, text, count=1)


def test_real_template_untouched_is_investigate():
    assert parse_handoff(_scaffold()).current_phase == "Investigate"


def test_digest_filled_only_is_decide_with_real_template():
    t = _fill(_scaffold(), "Digest", "- a fact (team)")
    assert parse_handoff(t).current_phase == "Decide"


def test_digest_and_decision_filled_is_shape():
    t = _fill(_fill(_scaffold(), "Digest", "- fact"), "Decision record", "- Chosen approach: use X")
    assert parse_handoff(t).current_phase == "Shape"


def test_shape_filled_drafts_placeholder_is_draft_without_drafts():
    t = _scaffold()
    t = _fill(t, "Digest", "- fact")
    t = _fill(t, "Decision record", "- Chosen approach: use X")
    t = _fill(t, "Shape", "- Form: single")
    s = parse_handoff(t)
    assert s.current_phase == "Draft"
    assert s.drafts == ()


def test_real_value_bullet_counts_as_content():
    s = parse_handoff("## Digest\nx\n## Decision record\n- Chosen approach: use X\n")
    assert s.current_phase == "Shape"


def test_non_draft_subheading_is_ignored():
    s = parse_handoff(
        _with_drafts("### Notes\nsome text\n### A\n- type: Chore\n- status: created\n")
    )
    assert [d.title for d in s.drafts] == ["A"]
    assert s.current_phase == "Done"


def test_draft_without_status_line_defaults_to_in_review():
    s = parse_handoff(_with_drafts("### A\n- type: Chore\n"))
    assert s.drafts[0].status == "in review"
    assert s.needs_user_reason == "approve drafts"


def test_crlf_line_endings():
    for name in ("drafts_in_review.md", "all_created.md"):
        text = (FIX / name).read_text(encoding="utf-8")
        assert parse_handoff(text.replace("\n", "\r\n")) == parse_handoff(text)


def test_create_phase_without_blocked():
    s = parse_handoff(_with_drafts("### A\n- status: approved\n"))
    assert s.current_phase == "Create"
    assert s.needs_user_reason is None


def _with_drafts(drafts: str) -> str:
    return "## Digest\nx\n## Decision record\nx\n## Shape\nx\n## Drafts\n" + drafts
