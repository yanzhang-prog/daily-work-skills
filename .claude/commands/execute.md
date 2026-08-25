Execute the active implementation plan step by step. Delegates to the `execute-plan` protocol in `.claude/skills/workflow/execute-plan/SKILL.md`.

**Usage:** `/execute` | `/execute <plan-name>`

- No argument → identify the active plan in `.claude/docs/plans/` from the current branch ticket
- `<plan-name>` → load that specific plan file from `.claude/docs/plans/`

Runs one step at a time, confirms with user between steps. Baseline tests must pass before starting.

Follow the full protocol in `.claude/skills/workflow/execute-plan/SKILL.md`.
