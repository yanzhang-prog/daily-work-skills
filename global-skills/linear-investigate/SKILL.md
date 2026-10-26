---
name: linear-investigate
description: Use when starting work on a Linear ticket request or finding and you need the facts first (current repo state, existing or duplicate Linear tickets, Slack and meeting-note context, Notion docs), or when auditing an agent system for gaps before deciding what to build.
---

# Investigate

Phase 1 of `linear-workflow`. Gathers facts and writes a compact **digest** plus **red flags** into the handoff file (`~/.claude/linear-work/<date>-<slug>.md`). It decides nothing; deciding is `linear-decide`.

**Why subagents:** reading a repo, Slack threads and Notion pages produces far more text than the later phases need. Each source is searched by its own subagent and returns a short digest. Raw source output never enters the main conversation (never raw).

## Entry A: a concrete request or finding

1. Read `## Request` in the handoff file. If there is no handoff file, create one from `../linear-workflow/references/handoff-template.md`.
2. Dispatch one general-purpose subagent per source, in parallel, using the prompts in `references/source-prompts.md`: repo, Linear, Slack, meeting notes, Notion. Set the model explicitly (a mid-tier model is enough).
3. Merge the digests into `## Digest`, one short block per source.
4. Fill `## Red flags`: duplicate or conflicting Linear tickets, conflict with team priorities, anything blocking. Write `none` if none. A source that could not be reached is listed as `not searched: <reason>`; it never fails the investigation. In a directory that is not a git repo, write `not searched: no repo`.
5. Check the request against the DoR and list the gaps under `## Digest` as "DoR gaps". Put these three first because they are what the requester usually leaves out: **acceptance criteria**, **scope boundary**, **expected output**. Do not invent the missing content.

## Entry B: coverage audit of an agent system

1. Scan the repo against `references/agent-system-checklist.md` (one subagent is enough).
2. Write the candidate work items (each: the gap, the evidence in the repo, why it matters) into `## Digest` under "Candidates".
3. Stop and let the user pick. The chosen candidate continues as entry A from step 2, with the other sources.

## Sources

- **Repo**: what already exists.
- **Linear**: duplicates, related tickets, dependencies, team priorities. Team `VIR`.
- **Slack and meeting notes**: why this work, who asked, the value. Meeting notes live in Google Drive (and Calendar); Notion's meeting-notes query also works. Granola is only searched if its connector is authorised.
- **Notion**: specs, prior decisions, the DoR page.

## When done

Tell the user the red flags first, then the three or four facts that matter most, and offer to show the rest. Next phase: `linear-decide`.
