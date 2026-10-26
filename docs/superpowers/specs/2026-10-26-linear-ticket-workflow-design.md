# Linear Ticket Workflow Skills — Design

Date: 2026-10-26
Status: Draft for approval

## 1. Intent and why

Yan Zhang (agent-system engineer, team PreAccounting-VirtualAssistant, Linear key `VIR`) creates Linear tickets as part of a daily workflow. Today, work arrives as someone's request, an optimisation spotted during daily work, or a gap in the agent system (prompt, agent, tool calling, eval, observability, ...). Turning that into good tickets takes investigation, a technical decision, a decision about ticket shape, and drafting to the team's Definition of Ready (DoR).

Recurring pain points (stated by Yan):
- Incoming requests are usually missing **acceptance criteria**, **scope boundary**, and **expected output**, and Yan has to chase them.
- Ticket structure gets re-done: in Linear, "Epic: VA Evaluation" (VIR-473) and the WS1 tickets (VIR-903/928/929) ended as Duplicate and were replaced by other parents. (Observation from reading Linear, not stated by Yan.)

Goal: a set of **global** Claude Code skills (in `~/.claude/skills/`, not project-level) that walk from "I have a piece of work" to "approved tickets created in Linear", with the right gates, without flooding one context window.

## 2. Goals, non-goals, anti-goals

**Goals**
- Investigate current state across repo, Linear, Slack, meeting notes (Google Meet / Granola-style), and Notion before deciding anything.
- Help Yan decide **how** to do the work (primary) and, when flagged, whether/how big (secondary).
- Choose a ticket shape and size tickets sensibly.
- Draft every ticket to the DoR plus two extra fields, show drafts, create in Linear only after approval.
- Work for the two real entry cases: a concrete request/finding (common), and a system-checklist coverage audit (less common).

**Non-goals**
- Not an implementation/coding skill. It stops at tickets in Linear.
- Not tied to the HC/VA Eval workstream or its label taxonomy (unlike the existing `doc-to-linear-tickets` in this repo).
- Not managing Linear Initiatives or Projects (those are the OKR level used by other teams). Tickets go into the existing "Virtual Assistant" project.

**Anti-goals (failure even if it technically works)**
- Inventing missing DoR content (why, AC, scope) instead of asking.
- Creating anything in Linear without explicit approval.
- Loading raw investigation output (long Slack/Notion/repo dumps) into the main conversation.
- Auto-deciding whether to create a spike ticket.
- Creating duplicates of existing tickets.

## 3. Constraints

- Global install location: `~/.claude/skills/`. This repo (`daily-work-skills`) holds the design doc and may also hold a copy of the skills for versioning (builder's call).
- Linear access via the Linear MCP tools (`list_issues`, `list_issue_labels`, `save_issue`, etc.). Sources: repo (local), Linear, Slack, meeting notes, Notion via their MCP connectors.
- DoR source of truth: Notion page "Definition of Ready (DoR) & Definition of Done (DoD)" (https://app.notion.com/p/374f148b3ab7808b8a78c9a7a8a088a4). DoR fields: Context (WHAT, incl. Figma flow link where applicable), Title, Acceptance Criteria (HOW), Labels, Value & Justification (WHY), Risks & Dependencies, Story Point Estimate. The DoD also constrains tickets: Linear ID in branch name, and "if a ticket is extended or broken up, the new tickets are already created".
- Max **5 SP** per ticket. Anything larger is split. Work that can proceed in parallel is split even when small.
- The DoR governs ticket content. The DoD is consulted only where it shapes a ticket: AC must say whether unit tests are needed, and tickets that are broken up must have their new tickets already created. Branch-name rules are not a ticket-creation concern.
- Follow user's global CLAUDE.md: when doing hands-on work, explain mechanism and reasoning (teaching mode). No Claude co-author line in commits made on Yan's behalf.

## 4. Decided structure

One thin **overview/router skill** plus one skill per phase. Rationale (Yan's): some phases consume a lot of context, so they must not live in one skill.

- **Overview skill**: describes the whole workflow, works out which phase the user is in, routes to the phase skill. Does no investigating and creates nothing.
- **Handoff file** between phases (the builder chooses location and format; one file per work item that phases read from and append to, so any phase can be re-entered in a fresh window). *This is my proposal, not Yan's decision.*
- Each phase can be entered directly if the user already has that phase's input (e.g. jump straight to Shape).

### Phase 1 — Investigate (fact gathering)
Runs in **subagents** (can be parallel per source). Each returns a compressed digest, never raw content, into the handoff file. Sources and what each mainly answers (my mapping, to be refined by the builder):
- Repo: what already exists.
- Linear: duplicates/related tickets, dependencies, team priorities.
- Slack and meeting notes: why this work, who asked, context and value.
- Notion: specs, prior decisions, the DoR itself.

Two entry points:
- **A. Concrete request or finding** (the common case). Validate: search for duplicates and related work, understand current state, gather background, then check the request against the DoR and list gaps. The three gaps that matter most to Yan: acceptance criteria, scope boundary, expected output.
- **B. System-checklist coverage audit** (replaces "no idea" mode, which Yan says is rare). Scan the repo against an agent-system checklist (prompt, agent, tool calling, eval, observability, guardrails, HITL, RAG, ...). Output candidate work items for Yan to pick from; the chosen one continues as entry A. The existing `agent-creation/*` skills (`add-eval`, `add-guardrails`, `add-hitl`, `add-rag`) in this repo are the starting point for the checklist. Also useful as checks: the global CLAUDE.md layout rules (prompts in `prompts.py`, settings in `config.py`, state in `states/`, external calls in `integrations/`).

Output of Investigate includes a **red flags** section (duplicate or conflicting tickets, conflict with team priorities). "None" if none. A separate scope-check step was deliberately not added; red flags cover it.

### Phase 2 — Explore / Decide (interactive, main conversation)
Not optional; Yan needs it often. Primary job: decide **how** (technical approach, tool/library choice). Secondary: if Investigate raised red flags, first confirm with Yan whether to proceed and at what size.
- Lay out feasible approaches with trade-offs, grounded in the repo's current state.
- Verify fast-moving frameworks and tools with live docs / web search rather than relying on training data.
- Give a recommendation; Yan picks.
- May dispatch small targeted subagent lookups when the discussion exposes a gap.
- **Spikes: ask Yan every time** whether to run a quick throwaway check inline or create a spike ticket. The skill may add a one-line recommendation with reasoning but never decides. (Yan: "每次都问我".)
- Output: a **decision record** in the handoff file: chosen approach, rejected alternatives and why, what is explicitly not being done. Written so Shape can use it directly and so "Out of scope" can be derived from it.

### Phase 3 — Shape
Four shapes (Yan confirmed an epic is not always needed):
1. **Single ticket**: one expected output, ≤5 SP.
2. **Big ticket with sub-tickets**: one deliverable broken into steps; usually short-lived (about one sprint).
3. **Epic with sub-tickets**: a theme with several deliverables, typically multiple sprints. Epic = parent issue titled with an `Epic:` prefix, as the team does today (e.g. VIR-472, VIR-615). Themes may define an epic, but the epic must state a completion condition so it does not become a bucket that never closes.
4. **Flat group** of independent tickets with no shared deliverable (a coverage audit may produce this).

Shapes 2 and 3 are the same Linear structure (parent issue plus sub-issues); the difference is scale and lifetime.

Heuristics (my proposal): if only half the pieces were done, would there still be value? Yes means flat group; no means parent/epic. Cut tickets by independently verifiable outcome rather than by technical layer (e.g. "a prompt plus its eval" rather than "all prompts" and "all evals" as separate tickets). Split any ticket over 5 SP; split parallelisable work. Estimate only leaf tickets, not parents (to avoid double counting). The skill recommends a shape with reasons; Yan chooses.

### Phase 4 — Draft
Each ticket gets all DoR fields **plus two added with Yan's approval**:
- **Expected output**: what exists when this is done (one or two sentences, placed after Context, before Acceptance Criteria). Distinct from AC: expected output is what is delivered; AC are the testable conditions that prove it.
- **Out of scope**: one line stating what this ticket does not do.

Rules:
- Never invent missing content. If a field is missing (especially AC, scope boundary, expected output), draft a follow-up question for the requester (e.g. a Slack message) for Yan to send or not.
- **Labels are looked up live every time** with the Linear label list for the team (`VIR`), skipping retired labels, because new labels get added. (A team-less label query returns only org-level retired labels; the team filter is required.)
- Observed team conventions to follow unless Yan says otherwise: title prefixes `[Spike]`, `[Eval]`, `Epic:`; spikes sized 2–3 SP with an expected output of a conclusion doc and a time box; tickets live under the "Virtual Assistant" project; estimates of 2, 3, 5.
- Show all drafts to Yan.

### Phase 5 — Create
- Only after explicit approval.
- Check for duplicates again immediately before creating.
- Reuse the safe parts of the existing `doc-to-linear-tickets` skill: reverse dependency order so the next actionable ticket sits at the top of the backlog, Backlog state, priority never Urgent, reference dependencies by name not number.
- After a spike ticket is agreed, the dependent follow-up tickets are created as **placeholders** in Linear: Backlog, blocked by the spike, with a first line "Provisional: approach pending spike result, to be refined" followed by an outline (goal, expected scope, open questions). This also satisfies the DoD rule that new tickets exist when work is broken up. Ask Yan each time whether to create placeholders in Linear or keep the outline only in the handoff file. After the spike result is known, the placeholders are refined to full DoR and re-approved.
- Finish with a summary: ticket IDs, SP, labels, anything inferred that needs review.

## 5. Left to the builder

- Skill names and exact file layout under `~/.claude/skills/`.
- Handoff file location and format.
- How each source (Slack, meeting notes, Notion) is searched, and which connector tools to use.
- Exact contents of the agent-system checklist for entry B.
- Whether to mirror the skills into this repo for versioning.
- Trigger descriptions so the right skill fires from natural requests.

## 6. Calls made without Yan (flag for review)

1. Handoff file between phases.
2. Mapping of sources to questions in Investigate.
3. Parents not estimated, only leaves.
4. Cut tickets by verifiable outcome, not technical layer.
5. After a spike ticket, follow-ups become Linear placeholders blocked by the spike (combining two options Yan suggested; asked each time).
6. Using `agent-creation/*` skills and global CLAUDE.md layout rules as the basis for the entry-B checklist.
7. Reading of the DoD rule about broken-up tickets: satisfied by creating placeholders (see Create phase).

## 7. Details settled after the builder check (all my calls unless noted)

- **Parent/child mechanism.** Linear native sub-issues (`parentId`), as the existing VIR tickets use. Create makes the parent first, then its children. Reverse-dependency ordering (most-blocked first) applies among siblings and among top-level tickets, not across parent and child.
- **Missing DoR field blocks per ticket.** A ticket with a gap in a required field is not created. It is marked "blocked, waiting on requester" in the handoff file, together with the drafted follow-up question. The other tickets in the set may be created only if Yan says so. A later session resumes from the handoff file.
- **Approval.** One approval covers the whole draft set. Any edit after approval, or a new duplicate found by the pre-create re-check, reopens the approval for the affected tickets.
- **Story points.** Draft proposes an estimate with a one-line reason and marks it "proposed". Yan confirms or changes it when approving. Accepted values follow the team's usage (1, 2, 3, 5); anything above 5 means split.
- **Ticket length.** Tickets must not be too long: no essays, about 300 words at most, one to three lines per field, at most five AC bullets, detail linked rather than pasted (added at Yan's request; Yan said 200 words was too few, the 300-word ceiling is my call).
- **Figma link.** Asked for only when the work has a UI part. Not applicable to most agent-system tickets.
- **Other Linear fields.** Team `VIR`, project "Virtual Assistant", state Backlog. **Assignee, cycle and priority are asked per ticket**; the skill proposes nothing silently (Yan's instruction). Never Urgent.
- **Meeting notes.** Yan's source is Google meeting notes, so search Google Drive and Calendar. Notion's meeting-notes query is also available. Granola needs authorization and is skipped unless authorized.
- **Unavailable source.** A source that cannot be reached is listed in red flags as "not searched: <reason>". It does not fail the whole investigation.
- **Why VIR-473 / VIR-903 were replaced.** Unknown; the skill does not depend on it.
