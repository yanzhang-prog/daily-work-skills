"""Parse a linear-workflow handoff file into a small summary.

Mirrors the "Pick the phase" rule in global-skills/linear-workflow/SKILL.md.
Pure and forgiving: real files do not always follow the template, so parsing
never raises. Unrecognised text just means "section empty".
"""

import re
from dataclasses import dataclass
from pathlib import Path

PHASES: tuple[str, ...] = ("Investigate", "Decide", "Shape", "Draft", "Create")

_PLACEHOLDER = re.compile(r"^<[^>]*>?$")  # `<filled by ...>` (tolerates a cut-off one)
_LINEAR_ID = re.compile(r"^[A-Za-z]+-\d+$")


@dataclass(frozen=True)
class DraftInfo:
    title: str
    status: str  # "in review" | "blocked" | "approved" | "created"
    linear_id: str | None


@dataclass(frozen=True)
class HandoffSummary:
    current_phase: str  # a name from PHASES, or "Done"
    completed: tuple[str, ...]
    drafts: tuple[DraftInfo, ...]
    needs_user_reason: str | None


def _split_sections(text: str) -> dict[str, list[str]]:
    """Map '## Heading' (lowercased) to its body lines. First heading wins."""
    # Not handled (YAGNI): `## ` lines inside fenced code blocks count as headings.
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            current = []
            sections.setdefault(m.group(1).lower(), current)
            if sections[m.group(1).lower()] is not current:
                current = None  # duplicate heading: ignore its body
        elif current is not None:
            current.append(line)
    return sections


_BULLET = re.compile(r"^[-*]\s+([^:]+):\s*(.*)$")
# The template's unfilled choice lines. Matched as literal values (simple and
# exact) rather than guessing "looks like a list of options": a real value such
# as `single` or `none` never equals these strings.
_UNFILLED_CHOICES = {"single | parent | epic | group", "<none | inline | ticket>"}


def _is_placeholder(line: str) -> bool:
    if _PLACEHOLDER.match(line):  # (a) `<...>` line, incl. cut-off `<...`
        return True
    m = _BULLET.match(line)
    if not m:
        return False
    value = m.group(2)
    return (
        not value  # (b) `- Label:` with nothing after it
        or bool(_PLACEHOLDER.match(value))  # (c) value is only `<...>`
        or value in _UNFILLED_CHOICES  # (d) unfilled template choice
    )


def _meaningful(lines: list[str]) -> list[str]:
    """Body lines minus blanks and template scaffold/placeholders."""
    return [s for s in (ln.strip() for ln in lines) if s and not _is_placeholder(s)]


def _normalize_status(raw: str) -> str:
    s = raw.strip().lower()
    if s.startswith("blocked"):
        return "blocked"
    if s in ("approved", "created", "in review"):
        return s
    return "in review"


def _parse_drafts(lines: list[str]) -> tuple[DraftInfo, ...]:
    blocks: list[tuple[str, list[str]]] = []
    for line in lines:
        m = re.match(r"^###\s+(.*?)\s*$", line)
        if m:
            blocks.append((m.group(1), []))
        elif blocks:
            blocks[-1][1].append(line)

    drafts = []
    for title, body in blocks:
        status_raw, linear_raw = "", ""
        is_draft = False  # a `### ` block is a draft only with a status/type line
        for ln in body:
            m = re.match(r"^\s*-\s*(status|linear|type)\s*:\s*(.*?)\s*$", ln, re.I)
            if not m:
                continue
            key = m.group(1).lower()
            if key in ("status", "type"):
                is_draft = True
            if key == "status" and not status_raw:
                status_raw = m.group(2)
            elif key == "linear" and not linear_raw:
                linear_raw = m.group(2)
        if not is_draft or _PLACEHOLDER.match(title):  # `### <ticket title>` scaffold
            continue
        linear_id = linear_raw if _LINEAR_ID.match(linear_raw) else None
        drafts.append(DraftInfo(title, _normalize_status(status_raw), linear_id))
    return tuple(drafts)


def _needs_user(statuses: set[str]) -> str | None:
    if "in review" in statuses:
        return "approve drafts"
    if "approved" in statuses and "blocked" in statuses:
        return "choose: create approved drafts now or wait for answers"
    if "blocked" in statuses:
        return "answer needed from requester"
    return None


def parse_handoff(text: str) -> HandoffSummary:
    sections = _split_sections(text)

    def body(name: str) -> list[str]:
        return _meaningful(sections.get(name, []))

    drafts = _parse_drafts(sections.get("drafts", [])) if body("drafts") else ()
    statuses = {d.status for d in drafts}

    if not body("digest"):
        phase = "Investigate"
    elif not body("decision record"):
        phase = "Decide"
    elif not body("shape"):
        phase = "Shape"
    elif not drafts:
        phase = "Draft"
    elif "in review" in statuses:
        phase = "Draft"
    elif "approved" in statuses:
        phase = "Create"
    elif "blocked" in statuses:
        phase = "Draft"
    else:
        phase = "Done"

    completed = PHASES if phase == "Done" else PHASES[: PHASES.index(phase)]
    return HandoffSummary(phase, completed, drafts, _needs_user(statuses))


def read_handoff(path: Path) -> HandoffSummary | None:
    try:
        return parse_handoff(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
