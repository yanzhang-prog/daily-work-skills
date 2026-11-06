"""All LLM prompts for the ticket board."""

COLUMN_REPO_CONTEXT_PROMPT = """\
These repos are readable for context in this session:
{repo_list}

Rules for reading them:
- The board already fetched these repos when this column started (see the ref and date on \
each line). You only need to fetch again if Yan asks for fresh data; then run \
`git -C <repo path> fetch origin`.
- If a repo line says "not searched", do not read that repo; tell Yan.
- Use one git command per Bash call: no pipes, no chaining, no redirects. Always use \
`git -C <repo path> ...` instead of `cd`.
- Read the default branch as `origin/<default>` using \
`git -C <repo path> show origin/<default>:<path>` or \
`git -C <repo path> grep <pattern> origin/<default>`. Never read the files on disk: the working tree may be \
on a stale or unrelated branch.
- Look at a PR or branch only when Yan asks you to. If you are unsure whether to, ask Yan.
- Never edit, create, or delete anything in a repo. They are read-only.
"""

COLUMN_FIRST_MESSAGE_PROMPT = """\
Use the linear-workflow skill for the request below.

Use EXACTLY this file path as this work item's handoff file: {handoff_path}
If the file does not exist, create it from the handoff template. Do not use any other path.

Request:
{request}
"""

COLUMN_RESUME_FALLBACK_PROMPT = """\
The previous session for this work item could not be resumed, so this is a new session.
Continue the work item from its handoff file at EXACTLY this path: {handoff_path}
Read that file first and pick up from the phase it records. Do not use any other handoff path.
Tell Yan briefly where you are picking up.
"""
