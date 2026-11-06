"""All LLM prompts for the ticket board."""

COLUMN_REPO_CONTEXT_PROMPT = """\
These repos are readable for context in this session:
{repo_list}

Rules for reading them:
- Run `git fetch` first so you see current remote state.
- Read the default branch as `origin/<default>` using `git show origin/<default>:<path>` or \
`git grep <pattern> origin/<default>`. Never read the files on disk: the working tree may be \
on a stale or unrelated branch.
- Look at a PR or branch only when Yan asks you to. If you are unsure whether to, ask Yan.
- Never edit, create, or delete anything in a repo. They are read-only.
"""
