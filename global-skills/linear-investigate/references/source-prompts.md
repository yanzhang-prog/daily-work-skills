# Subagent prompts, one per source

Fill the `<...>` parts from the handoff file's `## Request`. Every prompt ends with the same output rule.

**Output rule (append to every prompt):** Return a digest of at most 25 lines: facts only, each with where you found it (file path, ticket ID, link). No raw dumps, no opinions. If you could not reach the source, return exactly `not searched: <reason>`.

## Repo — what already exists
Search the current directory for code, config and docs related to: <request>. Report what already exists that touches this work (files, entry points, existing prompts/tools/evals), and what is clearly missing. If the directory is not a git repo, return `not searched: no repo`.

## Linear — duplicates, related work, dependencies, priorities
Using the Linear tools (`list_issues` with the `query` filter, team `VIR`, include closed and Duplicate states), find tickets related to: <request>. Report: exact or near duplicates (ID, title, status), related tickets, tickets this would depend on or block, and any current priority or cycle that conflicts with it.

## Slack — why, who, value
Search Slack (public and private) for discussion of: <request>. Report: who asked, why it matters, any decisions or constraints stated, and unanswered questions.

## Meeting notes — context from meetings
Search Google Drive (meeting notes documents) and Google Calendar for meetings about: <request>; also try the Notion meeting-notes query. Search Granola only if its connector is authorised. Report decisions, action items and stated reasons, with meeting date and title.

## Notion — specs and prior decisions
Search Notion for specs, ADRs, briefs and decisions about: <request>. Report what is already decided or specified, and any standard the work must follow.
