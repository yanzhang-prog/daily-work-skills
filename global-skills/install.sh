#!/usr/bin/env bash
# Symlink each skill dir here into ~/.claude/skills/ (override with SKILLS_DIR).
# Refuses to overwrite anything that is not a symlink; replaces existing symlinks.
set -e
src="$(cd "$(dirname "$0")" && pwd)"
dest="${SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$dest"
for dir in "$src"/*/; do
  name=$(basename "$dir")
  [ -f "$dir/SKILL.md" ] || continue
  target="$dest/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "REFUSING: $target exists and is not a symlink" >&2
    exit 1
  fi
  ln -sfn "${dir%/}" "$target"
  echo "linked $target -> ${dir%/}"
done
