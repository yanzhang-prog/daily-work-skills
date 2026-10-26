#!/usr/bin/env bash
# Test harness for the global Linear skills.
# Rules per skill dir: SKILL.md exists, frontmatter name == dir name,
# description is one line starting "Use when" and <= 500 chars, SKILL.md <= 200 lines.
# Plus every "skill|phrase" line in required-phrases.txt must appear
# (case-insensitive, fixed string) in that skill's SKILL.md or references/*.md.
cd "$(dirname "$0")" || exit 1
fail=0
bad() { echo "FAIL: $*"; fail=1; }

for dir in */; do
  name=${dir%/}
  [ -f "$name/SKILL.md" ] || continue
  f="$name/SKILL.md"
  fm_name=$(awk '/^---$/{c++; next} c==1 && /^name:/{sub(/^name:[ ]*/,""); print; exit}' "$f")
  desc=$(awk '/^---$/{c++; next} c==1 && /^description:/{sub(/^description:[ ]*/,""); print; exit}' "$f")
  [ "$fm_name" = "$name" ] || bad "$name: frontmatter name '$fm_name' != dir name"
  case "$desc" in "Use when"*) ;; *) bad "$name: description must start with 'Use when'";; esac
  [ ${#desc} -le 500 ] || bad "$name: description is ${#desc} chars (max 500)"
  [ "$(wc -l < "$f")" -le 200 ] || bad "$name: SKILL.md over 200 lines"
done

while IFS='|' read -r skill phrase; do
  case "$skill" in ''|'#'*) continue;; esac
  if [ ! -f "$skill/SKILL.md" ]; then
    case " $reported " in *" $skill "*) ;; *) bad "missing skill: $skill"; reported="$reported $skill";; esac
    continue
  fi
  if ! cat "$skill/SKILL.md" "$skill"/references/*.md 2>/dev/null | grep -qiF -- "$phrase"; then
    bad "$skill: missing phrase '$phrase'"
  fi
done < required-phrases.txt

[ $fail -eq 0 ] && echo "PASS: all skills valid"
exit $fail
