import config
import prompts


def test_server_binds_localhost_only():
    assert config.HOST == "127.0.0.1"


def test_allowed_tools_exclude_linear_writes():
    for tool in config.ALLOWED_TOOLS:
        for bad in ("save_issue", "save_comment", "save_document", "delete_"):
            assert bad not in tool


def test_disallowed_tools_block_notion_writes_but_not_linear():
    assert "mcp__claude_ai_Notion__notion-create-pages" in config.DISALLOWED_TOOLS
    assert "mcp__claude_ai_Notion__notion-update-page" in config.DISALLOWED_TOOLS
    assert not any(t.startswith("mcp__claude_ai_Linear__") for t in config.DISALLOWED_TOOLS)


def test_allowed_and_disallowed_do_not_overlap():
    assert not set(config.ALLOWED_TOOLS) & set(config.DISALLOWED_TOOLS)


def test_repo_prompt_formats_with_repo_list():
    text = prompts.COLUMN_REPO_CONTEXT_PROMPT.format(repo_list="x")
    assert "x" in text
    assert "fetch origin" in text  # the board fetches; sessions refetch only on request
    assert "origin/" in text


READONLY_BASH = {
    "Bash(git fetch)", "Bash(git fetch origin)",
    "Bash(git show:*)", "Bash(git grep:*)", "Bash(git log:*)", "Bash(git rev-parse:*)",
    "Bash(git symbolic-ref --short refs/remotes/origin/HEAD)",
    "Bash(gh pr view:*)", "Bash(gh pr diff:*)",
}


def test_allowed_bash_patterns_are_exactly_the_readonly_git_gh_set():
    assert {t for t in config.ALLOWED_TOOLS if t.startswith("Bash(")} == READONLY_BASH


def test_allowed_tools_have_no_linear_write_tools():
    verbs = ("save_", "delete_", "create_", "merge_", "share_", "unshare_")
    linear = [t for t in config.ALLOWED_TOOLS if "claude_ai_Linear__" in t]
    assert linear, "filter matched nothing; test would be vacuous"
    for tool in linear:
        assert not any(v in tool for v in verbs), tool


def test_allowed_tools_include_linear_reads_and_toolsearch():
    for t in ("mcp__claude_ai_Linear__list_issues", "mcp__claude_ai_Linear__get_issue",
              "ToolSearch", "Agent"):
        assert t in config.ALLOWED_TOOLS


def test_disallowed_includes_pip_variants():
    for t in ("Bash(pip3 install:*)", "Bash(python3 -m pip install:*)",
              "Bash(uv add:*)", "Bash(uv pip install:*)"):
        assert t in config.DISALLOWED_TOOLS


def test_data_dir_env_override_moves_all_state(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("TICKET_BOARD_DATA_DIR", str(tmp_path))
    try:
        reloaded = importlib.reload(config)
        assert reloaded.HANDOFF_DIR == tmp_path / "linear-work"
        assert reloaded.STATE_FILE == tmp_path / "columns.json"
        assert reloaded.HISTORY_DIR == tmp_path / "history"
    finally:
        monkeypatch.delenv("TICKET_BOARD_DATA_DIR")
        importlib.reload(config)


def test_data_dir_default_is_under_home_claude(monkeypatch):
    import importlib
    from pathlib import Path
    monkeypatch.delenv("TICKET_BOARD_DATA_DIR", raising=False)
    try:
        reloaded = importlib.reload(config)
        assert reloaded.HANDOFF_DIR == Path.home() / ".claude" / "linear-work"
        assert reloaded.STATE_FILE == Path.home() / ".claude" / "ticket-board" / "columns.json"
        assert reloaded.HISTORY_DIR == Path.home() / ".claude" / "ticket-board" / "history"
    finally:
        importlib.reload(config)


def test_r22_repo_prompt_rules():
    text = prompts.COLUMN_REPO_CONTEXT_PROMPT.format(repo_list="x")
    assert "one git command per Bash call" in text
    assert "no pipes" in text and "no chaining" in text and "no redirects" in text
    assert "git -C <repo path>" in text
    assert "already fetched" in text and "only need to fetch again if Yan asks" in text
    assert "not searched" in text and "tell Yan" in text


def test_b2_resume_fallback_prompt_has_handoff_path_field():
    text = prompts.COLUMN_RESUME_FALLBACK_PROMPT.format(handoff_path="/x/y.md")
    assert "/x/y.md" in text and "could not be resumed" in text


def test_a1_timeouts_configured():
    assert config.START_TIMEOUT_SECONDS == 60
    assert config.CLOSE_LOCK_TIMEOUT_SECONDS == 5
    assert config.SNAPSHOT_BUDGET_SECONDS > 0


def test_d5_settings_files_list():
    from pathlib import Path
    home = Path.home() / ".claude"
    assert config.SETTINGS_FILES == [
        home / "settings.json", home / "settings.local.json",
        config.SESSION_CWD / ".claude" / "settings.json",
        config.SESSION_CWD / ".claude" / "settings.local.json"]
