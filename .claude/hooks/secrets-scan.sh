#!/usr/bin/env bash
# PreToolUse(Write|Edit) — blocks writes that contain secrets or credentials.

source "$(dirname "$0")/lib.sh"

content=$(claude_content)
[ -z "$content" ] && exit 0

issues=""

echo "$content" | grep -qE 'AKIA[0-9A-Z]{16}' && issues="$issues  AWS access key\n"
echo "$content" | grep -qiE '(api_key|api_secret|secret_key|auth_token|access_token)\s*=\s*["'"'"'][A-Za-z0-9+/=_-]{20,}["'"'"']' && issues="$issues  API key/token assignment\n"
echo "$content" | grep -qE 'sk-ant-[A-Za-z0-9_-]{20,}' && issues="$issues  Anthropic API key\n"
echo "$content" | grep -qE 'sk-[A-Za-z0-9]{20,}' && issues="$issues  OpenAI-style API key\n"
echo "$content" | grep -qE '(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}' && issues="$issues  GitHub token\n"
echo "$content" | grep -qE 'BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY' && issues="$issues  Private key\n"
echo "$content" | grep -qiE '(password|passwd|pwd)\s*=\s*["'"'"'][^"'"'"']{8,}["'"'"']' && issues="$issues  Hardcoded password\n"

if [ -n "$issues" ]; then
  printf "Secrets scan blocked write:\n%bMove secrets to .env and load via python-dotenv.\n" "$issues" >&2
  exit 2
fi

exit 0
