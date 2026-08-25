#!/usr/bin/env bash
# PreToolUse(Bash) — DoD gate on git push.
# Blocks on functional stubs only: raise NotImplementedError / bare pass on critical paths.
# Does NOT block on # TODO or # FIXME comments — those are intentional notes.

source "$(dirname "$0")/lib.sh"

cmd=$(claude_command)

# Only fire on git push
echo "$cmd" | grep -qE '(^|[[:space:]])git push([[:space:]]|$)' || exit 0

# Don't gate on main/master (already protected by risky-git-guard)
branch=$(git branch --show-current 2>/dev/null || true)
echo "$branch" | grep -qE '^(main|master)$' && exit 0

# Check for functional stubs in the Python diff vs main (not comments)
stubs=$(git diff main...HEAD --unified=0 -- '*.py' 2>/dev/null \
  | grep -E '^\+' \
  | grep -v '^+++' \
  | grep -v '^\+\s*#' \
  | grep -E '\braise NotImplementedError\b' \
  || true)

if [ -n "$stubs" ]; then
  block "DoD gate: unimplemented stubs found in diff — resolve before pushing.

$stubs

Run /dod-check for the full DoD checklist."
fi

exit 0
