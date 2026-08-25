#!/usr/bin/env bash
# PreToolUse(Write|Edit|Bash) — enforce canonical evals/ directory layout.
#
# Canonical top-level dirs under evals/:  graders  metrics  pipelines  reports
# Any other immediate subdirectory (e.g. evals/runners/, evals/services/) is blocked.

source "$(dirname "$0")/lib.sh"

ALLOWED_EVALS_DIRS="graders metrics pipelines reports"

check_path() {
  local fpath="$1"
  fpath="${fpath#./}"   # strip leading ./

  # Only care about paths under evals/
  [[ "$fpath" == evals/* ]] || return 0

  # Extract the immediate subdirectory: evals/<subdir>/...
  local subdir
  subdir=$(echo "$fpath" | cut -d'/' -f2)
  [[ -z "$subdir" ]] && return 0

  for allowed in $ALLOWED_EVALS_DIRS; do
    [[ "$subdir" == "$allowed" ]] && return 0
  done

  block "BLOCKED: evals/$subdir/ is not in the canonical layout.
Canonical dirs under evals/: $ALLOWED_EVALS_DIRS
Move this code into one of the existing subtrees instead of creating a new one."
}

tool="${CLAUDE_TOOL_NAME:-}"

# Write / Edit / MultiEdit — check file_path
if [[ "$tool" == "Write" || "$tool" == "Edit" || "$tool" == "MultiEdit" ]]; then
  fpath=$(claude_path)
  [[ -n "$fpath" ]] && check_path "$fpath"
fi

# Bash — look for mkdir calls that target evals/
if [[ "$tool" == "Bash" ]]; then
  cmd=$(claude_command)
  # Extract any evals/... path tokens from the command
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] && check_path "$candidate"
  done < <(echo "$cmd" | grep -oE 'evals/[^ ;|&"\047]+' || true)
fi

exit 0
