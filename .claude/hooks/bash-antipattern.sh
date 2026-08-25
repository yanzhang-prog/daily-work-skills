#!/usr/bin/env bash
# PreToolUse(Bash) — warns when shell commands duplicate dedicated tool capabilities.
# Advisory only (exit 0): Read replaces cat/head/tail, Edit replaces sed, Glob/Bash replaces find+grep.

source "$(dirname "$0")/lib.sh"

cmd=$(claude_command)

if echo "$cmd" | grep -qE '\bcat\s+[^|<]|\bhead\s+|\btail\s+|\bsed\s+-i|\bawk\s+' 2>/dev/null; then
  warn "Hint: prefer Read/Edit/Grep tools over cat/head/tail/sed/awk — preserves context and avoids antipatterns."
fi

exit 0
