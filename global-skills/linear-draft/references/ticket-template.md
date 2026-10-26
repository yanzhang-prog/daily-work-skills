# Ticket template (DoR plus two added fields)

Source of truth for the DoR: Notion page "Definition of Ready (DoR) & Definition of Done (DoD)". Field order below.

**Title**: descriptive and unambiguous. Prefix `[Spike]` for spikes, `[Eval]` for eval work, `Epic:` for epic parents.

**Context** (the WHAT): background, who asked, what exists today. Figma flow link only when the work has a UI part.

**Expected output** (added): what exists when this is done, one or two sentences. A delivered thing, not a test. For spikes: a conclusion doc.

**Acceptance Criteria** (the HOW): explicit and testable, with examples. State whether unit tests are needed (the DoD says the AC decide this).

**Out of scope** (added): one line on what this ticket does not do. For spikes: do not build the real feature.

**Value & Justification** (the WHY): user or technical value, and why now.

**Risks & Dependencies**: blockers and cross-team dependencies, if known. Refer to tickets by name, not number.

**Story Point Estimate**: one of 1, 2, 3, 5, marked *proposed* with a one-line reason. Spikes: 2–3 and a time box. Parent tickets and epics: none.

**Labels**: from the live team label list (see SKILL.md).

**Assignee / cycle / priority**: asked per ticket, never filled silently.
