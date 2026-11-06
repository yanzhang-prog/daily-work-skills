"""settings_guard reads only the tmp files given here; never the real ~/.claude."""
import json

import pytest

from integrations.settings_guard import scan_settings


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(data if isinstance(data, str) else json.dumps(data))
    return p


def test_clean_settings_have_no_problems(tmp_path):
    p = write(tmp_path, "s.json", {"permissions": {
        "allow": ["Read", "mcp__claude_ai_Linear__list_issues", "mcp__claude_ai_Notion__notion-create-pages"],
        "defaultMode": "default"}})
    assert scan_settings([p]) == []


@pytest.mark.parametrize("entry", [
    "mcp__claude_ai_Linear__save_issue", "mcp__claude_ai_Linear__delete_comment",
    "mcp__claude_ai_Linear__create_attachment", "mcp__claude_ai_Linear__update_diff",
    "mcp__claude_ai_Linear__merge_diff", "mcp__claude_ai_Linear__resolve_diff_thread",
    "mcp__claude_ai_Linear__prepare_file_upload", "mcp__claude_ai_Linear__mark_notification",
    "mcp__claude_ai_Linear__*", "mcp__claude_ai_Linear",
])
def test_linear_write_allow_is_a_problem(tmp_path, entry):
    p = write(tmp_path, "s.json", {"permissions": {"allow": ["Read", entry]}})
    problems = scan_settings([p])
    assert len(problems) == 1
    assert entry in problems[0] and str(p) in problems[0]


def test_bypass_permissions_default_mode_is_a_problem(tmp_path):
    p = write(tmp_path, "s.json", {"permissions": {"defaultMode": "bypassPermissions"}})
    problems = scan_settings([p])
    assert len(problems) == 1 and "bypassPermissions" in problems[0]


def test_missing_malformed_and_odd_files_are_skipped(tmp_path):
    bad = write(tmp_path, "bad.json", "{not json")
    odd = write(tmp_path, "odd.json", {"permissions": {"allow": "not-a-list"}})
    lst = write(tmp_path, "list.json", [1, 2])
    real = write(tmp_path, "real.json", {"permissions": {"allow": ["mcp__claude_ai_Linear__save_issue"]}})
    problems = scan_settings([tmp_path / "missing.json", bad, odd, lst, real])
    assert len(problems) == 1 and "real.json" in problems[0]


def test_read_only_scan_does_not_modify_files(tmp_path):
    p = write(tmp_path, "s.json", {"permissions": {"allow": ["mcp__claude_ai_Linear__save_issue"]}})
    before = p.read_bytes()
    scan_settings([p])
    assert p.read_bytes() == before
