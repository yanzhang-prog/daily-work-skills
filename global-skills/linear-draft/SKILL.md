---
name: linear-draft
description: Use when Linear tickets have been shaped and you need to draft each one to the Definition of Ready (plus Expected output and Out of scope), look up labels, and chase missing details from the requester before showing the drafts for approval.
---

# Draft

Phase 4 of `linear-workflow`. Input: `## Shape` and `## Decision record`. Output: one block per ticket under `## Drafts` in the handoff file (`~/.claude/linear-work/<date>-<slug>.md`). Use the field order in `references/ticket-template.md`.

**Handoff file:** `~/.claude/linear-work/<date>-<slug>.md`. If none exists, create it from `../linear-workflow/references/handoff-template.md` and fill the input sections from what the user supplies. If several exist, list the recent ones and ask which.

## Rules

- **Never invent** missing content. If a required field is missing, especially acceptance criteria, scope boundary or expected output, set the ticket's `status: blocked: waiting on requester` and draft a **follow-up question** for the requester (for example a Slack message). Show the draft message; the user decides whether to send it. Do not send it yourself.
- **Keep tickets short.** A ticket that is too long does not get read. No essays: use short bullets and short sentences, never long paragraphs. About 300 words in total is a ceiling, not a target; if a ticket is over, cut it. Roughly: Context in two or three sentences, Expected output in one or two, at most five Acceptance Criteria bullets, and one line each for Out of scope, Value & Justification and Risks & Dependencies. Link to the Notion page or the handoff file for detail instead of pasting it.
- **Out of scope** comes from "Not doing" in the decision record. **Expected output** is a delivered thing, **Acceptance Criteria** are the testable conditions. They are different fields.
- **Acceptance Criteria** state whether unit tests are needed (DoD rule).
- **Story Point**: propose one of 1, 2, 3, 5 with a one-line reason and mark it *proposed*. The user confirms or changes it at approval. Only leaf tickets get points.
- **Labels are looked up live every time**: call `list_issue_labels` with team `VIR` (without the team filter you only get old org-level labels), skip any label with `retiredAt` set, and pick from what remains. Labels change, so never reuse a remembered list. If nothing fits, say so and ask.
- **Figma link**: ask only when the work has a UI part.
- **Assignee, cycle and priority**: ask the user for each ticket. Do not propose silently. Never priority Urgent.
- **Conventions seen in the team**: title prefixes `[Spike]`, `[Eval]`, `Epic:`; spikes are 2–3 SP with a conclusion doc as expected output and a time box; tickets live in the "Virtual Assistant" project.
- If the Linear tools are unavailable (not authorised), say so, finish the drafts from what is in the handoff file, and tell the user labels could not be looked up.

## Steps

1. Read `## Shape`. For each ticket, fill all fields from the digest, the decision record and the shape.
2. Mark any ticket with a gap `blocked: waiting on requester` and write its follow-up question.
3. Look up labels and ask the per-ticket questions.
4. Show all drafts together, with the proposed estimates and any inferred items called out.
5. To **resume** after the requester answers (possibly in a new session): read the handoff file, find tickets marked `blocked: waiting on requester`, fill the answers, set `status: draft`, and show them again.
6. When the user approves, set `status: approved` on each ticket that is not blocked. Approval never changes a blocked ticket's status: it stays `blocked: waiting on requester` until the missing answer is filled in. Next phase: `linear-create`.
