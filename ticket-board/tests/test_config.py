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
    assert not any("__Linear__" in t for t in config.DISALLOWED_TOOLS)


def test_allowed_and_disallowed_do_not_overlap():
    assert not set(config.ALLOWED_TOOLS) & set(config.DISALLOWED_TOOLS)


def test_repo_prompt_formats_with_repo_list():
    text = prompts.COLUMN_REPO_CONTEXT_PROMPT.format(repo_list="x")
    assert "git fetch" in text
    assert "origin/" in text


READONLY_BASH = {
    "Bash(git fetch:*)", "Bash(git show:*)", "Bash(git grep:*)", "Bash(git log:*)",
    "Bash(git rev-parse:*)", "Bash(git symbolic-ref:*)",
    "Bash(gh pr view:*)", "Bash(gh pr diff:*)",
}


def test_allowed_bash_patterns_are_exactly_the_readonly_git_gh_set():
    assert {t for t in config.ALLOWED_TOOLS if t.startswith("Bash(")} == READONLY_BASH


def test_allowed_tools_have_no_linear_write_tools():
    verbs = ("save_", "delete_", "create_", "merge_", "share_", "unshare_")
    for tool in config.ALLOWED_TOOLS:
        if "__Linear__" in tool:
            assert not any(v in tool for v in verbs), tool


def test_allowed_tools_include_linear_reads_and_toolsearch():
    for t in ("mcp__claude_ai_Linear__list_issues", "mcp__claude_ai_Linear__get_issue",
              "ToolSearch", "Agent"):
        assert t in config.ALLOWED_TOOLS


def test_disallowed_includes_pip_variants():
    for t in ("Bash(pip3 install:*)", "Bash(python3 -m pip install:*)",
              "Bash(uv add:*)", "Bash(uv pip install:*)"):
        assert t in config.DISALLOWED_TOOLS
