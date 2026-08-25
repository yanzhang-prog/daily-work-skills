#!/usr/bin/env bash
# PreToolUse(Bash) — blocks destructive git commands.

set -euo pipefail

source "$(dirname "$0")/lib.sh"

cmd=$(claude_command)
echo "$cmd" | grep -qE '(^|[[:space:]])git([[:space:]]|$)' || exit 0

if echo "$cmd" | grep -qE 'push[[:space:]]+--force(-with-lease)?|push[[:space:]]+-f|reset[[:space:]]+--hard|clean[[:space:]]+-fd|rebase[[:space:]]+-i|rebase[[:space:]]+--interactive|branch[[:space:]]+-D|checkout[[:space:]]+-f|switch[[:space:]]+-f'; then
  block "Blocked: destructive git command. Confirm intent before proceeding."
fi

exit 0
