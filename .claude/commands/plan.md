Start or continue a planning phase. Delegates to the `plan-review` protocol in `.claude/skills/workflow/plan-review/SKILL.md`.

**Usage:** `/plan <name>` | `/plan review` | `/plan refine` | `/plan refactor`

- No argument → ask for a plan name
- `<name>` → start a new plan at `.claude/docs/plans/{ticket-or-date}-{name}.md`, reading matching research from `.claude/docs/research/`
- `review` → check the active plan against research for alignment, completeness, sequencing
- `refine` → apply feedback from conversation, edit the plan surgically
- `refactor` → code quality pass on a codebase area: propose improvements in a risk table, apply after approval

Follow the full protocol in `.claude/skills/workflow/plan-review/SKILL.md`.
