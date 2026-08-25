# daily-work-skills

Personal collection of Claude Code skills, commands, and hooks for daily engineering work.

Originally from Galactus repo, Ramsey and Yan. 

## Contents

- [.claude/skills/](.claude/skills/) — reusable Claude Code skills covering planning, agent/eval creation, research/plan/execute workflows, and knowledge management.
- [.claude/commands/](.claude/commands/) — thin command wrappers around the workflow skills.
- [.claude/hooks/](.claude/hooks/) — PreToolUse/PostToolUse/Stop shell guards (secrets scanning, git safety, structure checks).
- [.claude/settings.json](.claude/settings.json) — permissions and hook wiring for this setup.

See [.claude/README.md](.claude/README.md) for the full workflow reference and skill index.

## Note on portability

Some skills were adapted from a company repo and may still contain paths or assumptions specific to that project. Check a skill's `SKILL.md` before invoking it in a new project.
