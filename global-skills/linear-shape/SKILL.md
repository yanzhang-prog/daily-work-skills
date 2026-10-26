---
name: linear-shape
description: Use when the approach for Linear work is decided and you need to choose the ticket structure (single ticket, big ticket with sub-tickets, epic with sub-tickets, or a flat group) and size each ticket.
---

# Shape

Phase 3 of `linear-workflow`. Input: `## Decision record`. Output: `## Shape` in the handoff file.

## The four shapes

1. **Single ticket**: one Expected output, at most 5 SP, one person.
2. **Big ticket with sub-tickets**: one deliverable broken into steps. Usually short-lived, about one sprint.
3. **Epic with sub-tickets**: a theme with several deliverables, typically several sprints. The epic is a parent issue titled `Epic:` plus a name. A theme may define an epic, but it must state a **completion condition** (what makes it done) so it does not become a bucket that never closes.
4. **Flat group**: independent tickets with no shared deliverable. A coverage audit often produces this.

Shapes 2 and 3 are the same structure in Linear (native parent issue with sub-issues). The difference is scale and lifetime.

## How to choose

- **Half-done test:** if only half the pieces were finished, would there still be value? Yes: flat group. No: parent or epic.
- Cut tickets by **independently verifiable outcome**, not by technical layer. "A prompt plus its eval" is better than "all prompts" and "all evals" as separate tickets, because each ticket can be accepted on its own.
- **5 SP is the ceiling.** Split anything bigger. Also split work that can run in parallel, even when each piece is small.
- Estimate only **leaf** tickets. A parent carries no estimate, so points are not counted twice. Accepted values: 1, 2, 3, 5.
- Put the dependency order and a parallel flag on each leaf.
- If the decision record chose a spike ticket, the shape includes the spike plus placeholder follow-ups blocked by it (see `linear-create`).

## Steps

1. Read `## Decision record`. The chosen approach decides the split: "build our own eval pipeline" and "adopt an existing eval tool" produce different tickets.
2. Propose a shape and give the reasons. **Recommend** one; the user chooses.
3. Write `## Shape`: Form, Epic completion condition (if epic), and the leaf tickets as `outcome · proposed SP · depends on · parallel?`.
4. Ask whether anything is wrong. Next phase: `linear-draft`.
