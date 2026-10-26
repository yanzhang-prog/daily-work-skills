---
name: linear-decide
description: Use when a Linear ticket request has been investigated and you need to decide how to do the work (technical approach, tool or library choice) before shaping or drafting tickets, including whether to run a spike.
---

# Explore / Decide

Phase 2 of `linear-workflow`, and the one that runs in the main conversation with the user. Input: `## Digest` and `## Red flags` in the handoff file. Output: `## Decision record`.

The main question is **how** to do the work. Whether to do it, and how big, was usually settled by whoever asked; it only comes up here when the red flags say so.

**Handoff file:** `~/.claude/linear-work/<date>-<slug>.md`. If none exists, create it from `../linear-workflow/references/handoff-template.md` and fill the input sections from what the user supplies. If several exist, list the recent ones and ask which.

## Steps

1. **Read `## Red flags` first.** If it lists a duplicate, a conflict or a priority mismatch, confirm with the user whether to continue, and at what size, before anything else. If it says `none`, say so in one line and move on.
2. **Lay out the feasible approaches** (usually two or three). For each: what it is, the trade-offs, and what it means for the repo as it stands today (use the digest). Say why, not just what, because the user wants to understand the choice.
3. **Verify fast-moving parts.** For agent frameworks, eval tools and observability tools, check current documentation or run a web search instead of relying on training data.
4. **Recommend one** and say why in a sentence. The user picks.
5. **Fill gaps with targeted lookups.** If the discussion exposes a missing fact, dispatch one small subagent for that single question and bring back a digest. Do not repeat the whole investigation.
6. **Write `## Decision record`** in the handoff file: Chosen approach, Rejected alternatives (and why), Not doing, Spike. Write it so `linear-shape` can split work directly from it and `linear-draft` can derive each ticket's "Out of scope" from "Not doing".

## Spikes: ask every time

Before writing the decision record, always state the spike call, whichever way it goes. If no spike seems needed, say "no spike proposed because <reason>; want one?" If the approach cannot be settled by discussion and reading and needs hands-on trying, ask the user which they want:

- an **inline spike**: a quick throwaway check now, result recorded in the decision record, or
- a **spike ticket**: a `[Spike]` ticket with its own Expected output (a conclusion doc), a time box and 2–3 SP, with the follow-up work created as placeholders blocked by it.

You may add one line of recommendation and the reason (for example "about a day and needs data access, so a ticket"). Never decide for them, and never skip the question. Record the user's answer in `Spike:`; never write `Spike: none` without having asked.

## When done

Summarise the decision record in a few lines and ask if anything is wrong. Next phase: `linear-shape`.
