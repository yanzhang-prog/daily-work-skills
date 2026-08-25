Start or continue a research phase. Delegates to the `research-review` protocol in `.claude/skills/workflow/research-review/SKILL.md`.

**Usage:** `/research <name>` | `/research review` | `/research refine` | `/research argue`

- No argument → ask for a research name
- `<name>` → start a new research artifact at `.claude/docs/research/{ticket-or-date}-{name}.md`
- `review` → re-read the active research file, flag gaps and unsupported conclusions
- `refine` → apply feedback from conversation, edit the file surgically
- `argue` → steel-man the opposite conclusion for each key finding

Follow the full protocol in `.claude/skills/workflow/research-review/SKILL.md`.
