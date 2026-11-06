"""Startup guard (ruling R25): the board's permission gate relies on Claude Code's own
permission prompt for Linear writes. A settings file that pre-allows a Linear write tool, or
that sets defaultMode "bypassPermissions", would silently remove that gate, so the server
refuses to start real sessions while either is present.

Read-only. Missing, unreadable or malformed files are skipped (they cannot pre-allow anything
the CLI would honour either, and the guard must never crash startup on them).
"""
import json
import re
from pathlib import Path

LINEAR = "mcp__claude_ai_Linear"
_WRITE_VERBS = ("save_", "delete_", "create_", "merge_", "share_", "unshare_", "update_",
                "submit_", "resolve_", "mark_", "retire_", "restore_", "prepare_")
# Whole-server forms: `mcp__claude_ai_Linear`, `mcp__claude_ai_Linear__*`, `mcp__claude_ai_Linear__`
_SERVER_WIDE = re.compile(rf"^{LINEAR}(__\*?)?$")


def _is_linear_write(entry: str) -> bool:
    e = entry.strip()
    if _SERVER_WIDE.match(e):
        return True
    prefix = LINEAR + "__"
    if not e.startswith(prefix):
        return False
    name = e[len(prefix):]
    return "*" in name or name.startswith(_WRITE_VERBS)


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def scan_settings(paths) -> list[str]:
    """Human-readable problems found in these settings files; [] means safe to start."""
    problems = []
    for path in paths:
        data = _read(path)
        perms = data.get("permissions") if data else None
        if not isinstance(perms, dict):
            continue
        allow = perms.get("allow")
        for entry in allow if isinstance(allow, list) else []:
            if isinstance(entry, str) and _is_linear_write(entry):
                problems.append(f"{path}: permissions.allow pre-approves Linear write {entry!r}")
        if perms.get("defaultMode") == "bypassPermissions":
            problems.append(f"{path}: permissions.defaultMode is bypassPermissions")
    return problems
