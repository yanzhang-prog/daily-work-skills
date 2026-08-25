#!/usr/bin/env bash
# PreToolUse(Bash) — blocks git commit when branch name lacks a Linear issue ID (vir-NNN).

set -euo pipefail

source "$(dirname "$0")/lib.sh"

cmd=$(claude_command)
echo "$cmd" | grep -qE '(^|[[:space:]])git commit([[:space:]]|$)' || exit 0

branch=$(git branch --show-current 2>/dev/null || true)
[ -z "$branch" ] && exit 0
echo "$branch" | grep -qE '^(main|master)$' && exit 0
echo "$branch" | grep -qiE 'vir-[0-9]+' && exit 0

block "Branch naming guard: branch must include vir-{id} for Linear auto-linking. Current branch: $branch"
