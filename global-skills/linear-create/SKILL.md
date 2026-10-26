---
name: linear-create
description: Use when Linear ticket drafts have been reviewed and the user has approved creating them, including an epic or big ticket with sub-tickets, spike placeholders, and a final summary of what was created.
---

# Create

Phase 5 of `linear-workflow`. Input: `## Drafts` in the handoff file (`~/.claude/linear-work/<date>-<slug>.md`) with `status: approved`. This is the only phase that writes to Linear.

## Gate: explicit approval

- **One approval** covers the whole draft set. The user must say so explicitly; silence or "looks fine so far" is not approval.
- Any edit after approval reopens it for the affected tickets. Show the change and get approval again.
- Tickets marked `blocked: waiting on requester` are **not created** unless the user says to create them anyway. List them as not created in the summary.
- If the Linear tools are unavailable (not authorised), say so and stop. **Never fabricate** ticket IDs or pretend a ticket exists.

## Steps

1. **Duplicate re-check immediately before creating.** Call `list_issues` (team `VIR`, `query` with the ticket's key words, including Duplicate and Done states). If a new duplicate or near-duplicate has appeared since the investigation, stop and reopen the approval for those tickets with the finding. This re-check is the last line of defence against the anti-goal "no duplicates".
2. **Create parent first, then children.** Create the parent or epic issue, note its ID, then create each child with `parentId` set to it. Among siblings, and among top-level tickets, use **reverse dependency order** (most-blocked first, least-blocked last) so the next actionable ticket ends up at the top of the backlog.
3. Use `save_issue` with: `team` = `VIR`, `project` = "Virtual Assistant", `state` = `Backlog`, `title`, `description` (the draft, as Markdown with real newlines), `estimate` (leaf tickets only, confirmed by the user), `labels` (from the approved draft), and `assignee`, `cycle`, `priority` only if the user gave them for that ticket. **Never Urgent.** Express dependencies with `blockedBy` using issue IDs, and refer to tickets by name in the description text, not number.
4. After each create, set that draft's `status: created` and `linear: <ID>` in the handoff file, so a crash or a new session does not create it twice.

## Spike placeholders

When a spike ticket was agreed, the follow-up tickets are created as **placeholders**, but ask the user each time whether to create them in Linear or keep the outline only in the handoff file. A placeholder is in Backlog, `blockedBy` the spike, and its description starts with the line `Provisional: approach pending spike result, to be refined`, followed by an outline (goal, expected scope, open questions). After the spike result is known, refine each placeholder to the full DoR and get approval again before updating it.

## Finish with a summary

Show a table: ticket title, Linear ID, SP, labels, parent. Then list separately: tickets **not created** (and why), placeholders, and anything that was inferred and should be reviewed. Append a dated line to `## Log` in the handoff file.
