#!/usr/bin/env bash
# PreToolUse(Bash) — advisory DoR check on new branch creation.
# Non-blocking: warns Claude when no plan file exists for the Linear ticket.

source "$(dirname "$0")/lib.sh"

cmd=$(claude_command)

# Only fire on new branch creation
echo "$cmd" | grep -qE 'git (checkout -b|switch -c)' || exit 0

# Extract ticket ID (vir-NNN or VIR-NNN)
ticket=$(echo "$cmd" | grep -oiE 'vir-[0-9]+' | head -1)
[ -z "$ticket" ] && exit 0

ticket_lower=$(echo "$ticket" | tr '[:upper:]' '[:lower:]')

# Check if a plan file references this ticket
plan_found=$(grep -rl "$ticket_lower" .claude/docs/plans/ 2>/dev/null | head -1)

if [ -z "$plan_found" ]; then
  warn "DoR advisory: no plan found for $ticket in .claude/docs/plans/.
Run /plan before starting work. DoR requires: plan exists, AC defined, scope sized ≤8 steps."
fi

exit 0
