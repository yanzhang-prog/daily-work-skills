---
name: linear-workflow
description: Use when planning or creating Linear tickets, an epic with sub-tickets, or a group of tickets from a request, a finding, or a gap in an agent system. Routes through the investigate, decide, shape, draft and create phases.
---

# Linear Ticket Workflow

Turns "a piece of work" into approved Linear tickets that meet the team's Definition of Ready (DoR). This skill is the router: it **does not investigate and does not create tickets**. It works out which phase you are in and hands over to that phase's skill.

Each phase is its own skill because some phases read a lot of material and must not share one context window. Phases pass results through a **handoff file**, so any phase can be re-entered in a fresh session.

## Phases

| # | Phase | Skill | Output in the handoff file |
|---|-------|-------|----------------------------|
| 1 | Investigate (gather facts, in subagents) | `linear-investigate` | `## Digest`, `## Red flags` |
| 2 | Explore / Decide (how to do it, with the user) | `linear-decide` | `## Decision record` |
| 3 | Shape (one ticket, big ticket, epic, or group) | `linear-shape` | `## Shape` |
| 4 | Draft (DoR fields plus Expected output and Out of scope) | `linear-draft` | `## Drafts` |
| 5 | Create (only after explicit approval) | `linear-create` | Linear issues, IDs in `## Drafts` |

You can enter at any phase if you already have its input (for example, jump to Shape when the approach is already decided).

## Pick the phase

1. Find the handoff file: `~/.claude/linear-work/<YYYY-MM-DD>-<slug>.md`. If the user names a work item, look for its file; otherwise list recent files and ask which one.
2. **No handoff file:** create one from `references/handoff-template.md`, fill `## Request` and `## Entry` from what the user said, then start at the phase whose input the user already has.
3. With a file, start at the first section that is empty. A section that still holds only the template's `<filled by ...>` placeholder text counts as empty:
   - no `## Digest` → Investigate
   - Digest but no `## Decision record` → Decide
   - Decision record but no `## Shape` → Shape
   - Shape but no drafts → Draft
   - drafts with `status: approved` → Create
   - drafts marked `blocked: waiting on requester` → resume Draft once the requester's answer is in
   - mixed approved and blocked drafts → go to Create for the approved ones (it asks the user whether to create them now); the blocked ones wait for Draft

## Entry points (set in `## Entry`)

- **A: a concrete request or finding** (the common case). Someone asked for it, or the user noticed it while working.
- **B: system-checklist coverage audit.** The user wants to find gaps in an agent system (prompt, agent, tool calling, eval, observability, ...). `linear-investigate` produces candidates; the chosen one continues as entry A.

## Rules every phase follows

- Never invent missing DoR content. Ask, or draft a follow-up question for the requester.
- Nothing is created in Linear without explicit approval.
- Spike or not is the user's call, asked every time.
- Max 5 SP per ticket. Split larger work, and split work that can run in parallel.
- Explain the reasoning as you go. The user wants to understand the system, not just receive output.
