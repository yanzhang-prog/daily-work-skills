# Linear Ticket Workflow Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build six global Claude Code skills that take Yan from "a piece of work" to approved tickets created in Linear, one overview/router skill plus one skill per phase.

**Architecture:** Each skill is a focused `SKILL.md` (plus `references/` for bulk) authored in this repo under `global-skills/` and symlinked into `~/.claude/skills/`. Phases pass results through one handoff file per work item. Fact-gathering runs in subagents and returns digests only. A deterministic `validate.sh` is the test harness: it checks frontmatter rules and that every phrase the spec pins appears in the right skill.

**Tech Stack:** Markdown skills, bash (`validate.sh`, `install.sh`), Linear / Slack / Notion / Google Drive MCP tools at runtime.

**Spec:** `docs/superpowers/specs/2026-10-26-linear-ticket-workflow-design.md`

## Global Constraints

- Skills install globally to `~/.claude/skills/`, never project-level.
- Max **5 SP** per ticket; split anything larger; split parallelisable work.
- DoR fields: Context, Title, Acceptance Criteria, Labels, Value & Justification, Risks & Dependencies, Story Point Estimate. Plus two added fields: **Expected output** (after Context, before AC) and **Out of scope**.
- DoR governs ticket content. DoD is consulted only for: AC states whether unit tests are needed; broken-up tickets have their new tickets already created.
- Never invent missing DoR content; draft a follow-up question for the requester instead.
- Nothing is created in Linear without explicit approval. Never priority Urgent.
- Assignee, cycle and priority are asked per ticket.
- Spike or not: ask Yan every time; a one-line recommendation is allowed, a decision is not.
- Labels are looked up live per team `VIR`, retired labels skipped.
- Team `VIR`, project "Virtual Assistant", state Backlog. Title prefixes `[Spike]`, `[Eval]`, `Epic:`. Estimates 1, 2, 3, 5.
- Epic = native Linear parent issue titled `Epic:` plus sub-issues; parent first, then children. Only leaf tickets are estimated.
- Unreachable source is reported as `not searched: <reason>` in red flags; it never fails the investigation.
- Investigation subagents return digests, never raw content.
- User's global CLAUDE.md: no Claude co-author line in commits; teaching-mode explanations when working with Yan.

## Review Focus

- Linear MCP unavailable or unauthorised: skills say so and stop; they never fabricate ticket IDs.
- A phase skill invoked directly with no handoff file: it creates one from what the user supplies instead of failing.
- Duplicate found by the pre-create re-check after approval: approval reopens for the affected tickets.
- Requester answers arrive in a new session: the skill resumes from tickets marked `blocked: waiting on requester`.
- Run from a directory that is not a git repo: Investigate skips the repo source with `not searched: no repo`.

---

## File Structure

```
global-skills/
  validate.sh                      test harness
  required-phrases.txt             lines "skill|phrase", one pinned requirement each
  install.sh                       symlinks each skill dir into ~/.claude/skills/
  linear-workflow/SKILL.md         router; references/handoff-template.md
  linear-investigate/SKILL.md      references/source-prompts.md, references/agent-system-checklist.md
  linear-decide/SKILL.md
  linear-shape/SKILL.md
  linear-draft/SKILL.md            references/ticket-template.md
  linear-create/SKILL.md
```

Handoff file: `~/.claude/linear-work/<YYYY-MM-DD>-<slug>.md` (builder's call per spec).

---

### Task 1: Test harness and installer

**Files:**
- Create: `global-skills/validate.sh`, `global-skills/required-phrases.txt`, `global-skills/install.sh`

**Interfaces:**
- Produces: `./global-skills/validate.sh` exits 0 only if every skill dir passes all rules; `required-phrases.txt` format `skill|phrase` (case-insensitive grep over that skill's `SKILL.md` and its `references/*.md`); `./global-skills/install.sh` symlinks `global-skills/<name>` to `~/.claude/skills/<name>`.

- [ ] **Step 1: Write `validate.sh` and a first `required-phrases.txt` line** `linear-workflow|handoff`. Rules checked per skill dir: `SKILL.md` exists; frontmatter `name` equals the dir name; `description` starts with `Use when` and is at most 500 chars; `SKILL.md` is at most 200 lines; every `required-phrases.txt` line for that skill matches. Also fail if any dir listed in `required-phrases.txt` is missing.
- [ ] **Step 2: Run `bash global-skills/validate.sh`**. Expected: FAIL, "missing skill: linear-workflow".
- [ ] **Step 3: Write `install.sh`**. Refuses to overwrite a non-symlink at the target; replaces an existing symlink. Prints each link made.
- [ ] **Step 4: Commit** `git add global-skills && git commit -m "Add skill validator and installer"`.

### Task 2: linear-workflow (router) and handoff template

**Files:**
- Create: `global-skills/linear-workflow/SKILL.md`, `global-skills/linear-workflow/references/handoff-template.md`
- Modify: `global-skills/required-phrases.txt`

**Interfaces:**
- Produces: handoff file section names used by all later tasks: `## Request`, `## Entry`, `## Digest`, `## Red flags`, `## Decision record`, `## Shape`, `## Drafts`, `## Log`. Each ticket under `## Drafts` carries `status:` one of `draft | blocked: waiting on requester | approved | created` and `linear:` (ID or none).

- [ ] **Step 1: Add phrases** for `linear-workflow`: `handoff`, `Linear ticket`, `linear-investigate`, `linear-decide`, `linear-shape`, `linear-draft`, `linear-create`, `enter at any phase`, `~/.claude/linear-work`, `does not investigate`, `no handoff file` (Review Focus: direct invocation). Run validate; expect FAIL.
- [ ] **Step 2: Write `SKILL.md`**. Description triggers: planning or creating Linear tickets, epics, or a group of tickets; turning a request or finding into tickets. Body: the five phases and which skill owns each; how to pick the phase from what exists (no handoff file means Investigate; digest but no decision means Decide; and so on); entry A vs B; create the handoff file from the template when none exists. The router investigates and creates nothing.
- [ ] **Step 3: Write `references/handoff-template.md`** containing the section skeleton above.
- [ ] **Step 4: Run validate**. Expected: only the other skills' missing-dir failures remain, none for `linear-workflow`.
- [ ] **Step 5: Commit** `feat: add linear-workflow router and handoff template`.

### Task 3: linear-investigate

**Files:**
- Create: `global-skills/linear-investigate/SKILL.md`, `references/source-prompts.md`, `references/agent-system-checklist.md`
- Modify: `global-skills/required-phrases.txt`

**Interfaces:**
- Consumes: handoff `## Request`.
- Produces: fills `## Digest` and `## Red flags` (`none` when empty; unreachable sources as `not searched: <reason>`). Entry B produces a candidate list in `## Digest` and stops for Yan's pick.

- [ ] **Step 1: Add phrases**: `subagent`, `digest`, `never raw`, `red flags`, `not searched`, `duplicate`, `acceptance criteria`, `scope boundary`, `expected output`, `entry A`, `entry B`, `coverage`, `Google Drive`, `Granola`, `prompts.py`, `integrations`, `not searched: no repo` (Review Focus: not a git repo). Run validate; expect FAIL.
- [ ] **Step 2: Write `SKILL.md`**. Entry A: validate the request, dispatch one general-purpose subagent per source in parallel (repo, Linear, Slack, meeting notes, Notion), merge digests, then list DoR gaps with the three priority gaps first. Entry B: scan repo against the checklist, output candidates, stop for Yan's pick, then continue as entry A. Never load raw source output into the main conversation.
- [ ] **Step 3: Write `references/source-prompts.md`**: one prompt template per source naming what it answers (repo: what exists; Linear: duplicates, related, dependencies, priorities, searched with `list_issues`; Slack and meeting notes via Google Drive and Calendar, plus Notion meeting-notes query, why/who/value; Notion: specs, prior decisions), each capped at a 25-line digest. Granola only if authorised.
- [ ] **Step 4: Write `references/agent-system-checklist.md`** seeded from this repo's `.claude/skills/agent-creation/*` (prompt, agent, tool calling, eval, observability, guardrails, HITL, RAG) plus the global CLAUDE.md layout checks (`prompts.py`, `config.py`, `states/`, `integrations/`).
- [ ] **Step 5: Run validate**. Expected: no failures for `linear-investigate`.
- [ ] **Step 6: Commit** `feat: add linear-investigate`.

### Task 4: linear-decide

**Files:**
- Create: `global-skills/linear-decide/SKILL.md`
- Modify: `global-skills/required-phrases.txt`

**Interfaces:**
- Consumes: `## Digest`, `## Red flags`.
- Produces: `## Decision record` with `Chosen approach`, `Rejected alternatives`, `Not doing`, `Spike`.

- [ ] **Step 1: Add phrases**: `red flags`, `how`, `recommend`, `web search`, `trade-off`, `every time`, `spike ticket`, `inline spike`, `Decision record`, `Not doing`. Run validate; expect FAIL.
- [ ] **Step 2: Write `SKILL.md`**. Open by reading `## Red flags`; if any, confirm with Yan before continuing. Then the primary job: approaches with trade-offs grounded in the digest, live docs or web search for fast-moving frameworks, a recommendation, Yan picks. Spike handling: ask Yan every time, inline or ticket, with an optional one-line recommendation. May dispatch small targeted subagent lookups. Write the decision record.
- [ ] **Step 3: Run validate**; none for `linear-decide`. **Step 4: Commit** `feat: add linear-decide`.

### Task 5: linear-shape

**Files:**
- Create: `global-skills/linear-shape/SKILL.md`
- Modify: `global-skills/required-phrases.txt`

**Interfaces:**
- Consumes: `## Decision record`.
- Produces: `## Shape` listing the chosen form (`single | parent | epic | group`) and the leaf tickets, each with outcome, proposed SP, dependencies, parallel flag.

- [ ] **Step 1: Add phrases**: `5 SP`, `single ticket`, `big ticket`, `Epic:`, `flat group`, `completion condition`, `verifiable outcome`, `leaf`, `parallel`, `recommend`. Run validate; expect FAIL.
- [ ] **Step 2: Write `SKILL.md`**: the four shapes, the "if only half were done, is there value" heuristic, cut by independently verifiable outcome not technical layer, split above 5 SP and for parallel work, estimate leaves only, an epic must state its completion condition. Recommend a shape with reasons; Yan chooses.
- [ ] **Step 3: Run validate; Step 4: Commit** `feat: add linear-shape`.

### Task 6: linear-draft

**Files:**
- Create: `global-skills/linear-draft/SKILL.md`, `references/ticket-template.md`
- Modify: `global-skills/required-phrases.txt`

**Interfaces:**
- Consumes: `## Shape`, `## Decision record`.
- Produces: `## Drafts` entries with all fields, `status:` set as in Task 2.

- [ ] **Step 1: Add phrases**: `Expected output`, `Out of scope`, `Acceptance Criteria`, `Value & Justification`, `Risks & Dependencies`, `Story Point`, `proposed`, `list_issue_labels`, `retired`, `never invent`, `follow-up question`, `blocked: waiting on requester`, `unit tests`, `[Spike]`, `[Eval]`, `Epic:`, `Figma`, `assignee`, `cycle`, `priority`, `resume` (Review Focus: requester answers arrive in a new session), `unavailable` (Review Focus: Linear tools unauthorised). Run validate; expect FAIL.
- [ ] **Step 2: Write `references/ticket-template.md`** in the field order Title, Context, Expected output, Acceptance Criteria (state whether unit tests are needed), Out of scope, Value & Justification, Risks & Dependencies, Story Point (marked proposed), Labels.
- [ ] **Step 3: Write `SKILL.md`**: never invent; a missing required field becomes `blocked: waiting on requester` with a drafted follow-up question (for example a Slack message) for Yan to send or not; labels from `list_issue_labels` filtered by team `VIR`, skipping retired; Figma link only when the work has UI; ask Yan per ticket for assignee, cycle and priority; spike tickets get a conclusion-doc expected output, a time box, and 2 to 3 SP; show all drafts.
- [ ] **Step 4: Run validate; Step 5: Commit** `feat: add linear-draft`.

### Task 7: linear-create

**Files:**
- Create: `global-skills/linear-create/SKILL.md`
- Modify: `global-skills/required-phrases.txt`

**Interfaces:**
- Consumes: `## Drafts` with `status: approved`.
- Produces: Linear issues; updates each draft's `status: created` and `linear:` ID; final summary table.

- [ ] **Step 1: Add phrases**: `explicit approval`, `one approval`, `reopen`, `duplicate`, `list_issues`, `save_issue`, `parent first`, `reverse dependency`, `Backlog`, `Urgent`, `placeholder`, `Provisional: approach pending spike result`, `blocked by`, `summary`, `not created`, `unavailable`, `never fabricate` (Review Focus: Linear tools unauthorised), `re-check` (Review Focus: duplicate after approval). Run validate; expect FAIL.
- [ ] **Step 2: Check the `save_issue` schema** with ToolSearch (`select:mcp__claude_ai_Linear__save_issue`) for the parent, estimate, labels, project, state and relation parameter names, and write those exact names into the skill.
- [ ] **Step 3: Write `SKILL.md`**: one approval of the whole set; edits after approval or a new duplicate from the re-check reopen it for affected tickets; tickets in `blocked: waiting on requester` are not created unless Yan says so; create parent first, then children, reverse dependency order among siblings; Backlog, project "Virtual Assistant", never Urgent; spike placeholders as in the spec, asking each time; final summary of IDs, SP, labels, inferred items. If Linear tools are unavailable, say so and stop.
- [ ] **Step 4: Run validate; expect PASS for all six skills. Step 5: Commit** `feat: add linear-create`.

### Task 8: Install and dry run

**Files:** none created; uses `global-skills/install.sh`.

- [ ] **Step 1: Run `bash global-skills/validate.sh && bash global-skills/install.sh`**. Expected: validate exits 0; six symlinks printed; `ls ~/.claude/skills | grep linear-` lists six names.
- [ ] **Step 2: Dry run, read-only.** In a fresh Claude session in the VIR repo, prompt "I want to add a [small real request]; help me turn it into Linear tickets." Expected: router fires; handoff file appears in `~/.claude/linear-work/`; Investigate dispatches subagents and returns digests; flow stops at the draft review. Do not approve creation.
- [ ] **Step 3: Record any miss** (skill did not fire, raw output leaked into main thread, a field invented) in the handoff file's `## Log`, then fix the owning skill and re-run `validate.sh`.
- [ ] **Step 4: Commit** any fixes `fix: tighten linear skills after dry run`.
