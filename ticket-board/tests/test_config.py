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
