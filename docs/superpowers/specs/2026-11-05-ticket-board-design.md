# Ticket Board: a web page for running several Linear ticket builds at once

Date: 2026-11-05
Status: draft, awaiting approval

## Intent and why

Yan builds Linear tickets with the `linear-workflow` skills (investigate, decide, shape, draft, create). Each build starts with a slow investigation phase, so Yan opens another Claude Code chat window in VS Code and starts the next ticket while the first one works. Yan routinely has at least 3 ticket builds in flight.

The problem is not the workflow. It is that several VS Code chat windows are messy to switch between, and Yan loses track of which ticket is in which window, what stage it is at, and which one is waiting for an answer.

The fix is one web page that shows all in-flight ticket builds side by side, lets Yan reply to each one right there, and makes it obvious which one needs attention.

## What it is

A web page, used only by Yan, running on Yan's Mac (localhost). Nothing is hosted or shared at this stage.

### Layout (chosen by Yan: "layout B")

- One column per open ticket build, columns side by side across the page.
- Each column has its own chat: message history plus a reply box. Yan replies inside the column.
- A "+ New ticket" control adds a column. An "x" on a column closes it. Yan can open and close columns freely.
- A top bar shows the number of open tickets and how many need Yan.

### What each column header shows (confirmed by Yan)

- Ticket name.
- Status badge: **Working** (green, with a short note such as "reading Slack"), **Needs you** (orange, with what is needed such as "approve drafts"), **Done** (grey, with the created Linear ID).
- Phase tracker: Investigate, Decide, Shape, Draft, Create, with finished phases ticked and the current one in bold.
- A column that needs Yan has an orange border so it stands out at a glance.

### Look and feel (confirmed by Yan)

Large text. The approved mockup used roughly: ticket name 20px, badge, chat text and reply box 18px, phase tracker 15px. Yan said the size "looks good"; treat these numbers as the minimum. Light theme as in the mockup is fine; Yan did not specify a theme (builder's call).

Mockups: `.superpowers/brainstorm/35684-1793892691/content/layout-b-detail-v2.html`. The mockups are throwaway; do not build on their markup.

## How it works behind the page

Items marked **(my call)** were decided by the design author, not by Yan. Yan should check them.

1. **Each column is a real Claude Code session (my call).** The skills rely on subagents and on the Linear, Slack, Notion and Google connectors, so a plain chat box would not do the job. A small local server starts one Claude Code session per column (the installed `claude` CLI, version 2.1.241 on this Mac, or the Claude Agent SDK) and streams its messages to the page. Whether sessions started this way get the same connector access as Yan's VS Code window is not yet verified and must be checked first.
2. **Phase and status come from the handoff files (my call).** Each ticket build keeps a handoff file at `~/.claude/linear-work/<date>-<slug>.md`. Its sections (Digest, Decision record, Shape, Drafts, Log) fill in order, and `linear-workflow/SKILL.md` already defines how to read the current phase from them, including draft statuses `in review`, `approved`, `blocked: waiting on requester`, and `created`. The page reads these files for the tracker. Whether a draft's `in review` status reliably means "waiting on Yan" is not yet verified. Wait for the session to be idle and ask the user for a reply is the likely signal for "Needs you"; the builder decides how to detect it.
3. **The approval gate must stay visible and safe (my call).** `linear-create` writes to Linear only after Yan's explicit approval. The page must show that question clearly and must never create tickets without it. The page must not add any shortcut that skips or auto-answers it. Yan's answers go to the session as normal chat messages.
4. **Nothing in the skills' rules changes.** Rules in `global-skills/linear-workflow/SKILL.md` still apply: no invented DoR content, never write story points to Linear, max 5 SP per ticket, spike-or-not is Yan's call.

### Repos a ticket build can read

- A short list of repos in a config file: this repo and the virtual system repo. The virtual system repo's path on this Mac is **not yet known**; it was not found in the home directory and Yan has not given it.
- Access is **read-only (my call)**. A ticket build never edits these repos. Its only writes are the handoff file and, after approval, Linear tickets.
- **Fetch, never pull (my call).** Before an investigation, run `git fetch` on each listed repo. That updates remote branches and PRs without touching the working folder, the checked-out branch, or uncommitted work.
- **Default to the remote main branch (confirmed by Yan, mechanism is my call).** Read `origin/main` directly (for example with `git show` / `git grep` on the ref) instead of the files on disk, so results are current whatever Yan has checked out.
- **Branches and PRs (confirmed by Yan).** The build searches a PR or branch only when Yan says so or when Yan answers a question about it. When the build is unsure whether a branch or PR matters, it asks Yan for more information; it does not guess. `gh` (version 2.96.0) is installed and can read PRs.
- **Automatic choice of repo (confirmed by Yan).** Yan does not want to pick a repo per ticket. The build decides which listed repos look relevant to the request and searches those.
- **Visibility (my call).** Each column shows which repos and refs it read, for example "virtual-system @ origin/main, 3 Nov" or "PR #482", so Yan can notice when it searched the wrong place.
- This needs a change to `global-skills/linear-investigate/references/source-prompts.md`: the "Repo" prompt currently searches only "the current directory" as it is on disk. It must be changed to the behaviour above.

## Where it lives

In this repo (`daily-work-skills`), in its own folder (name is the builder's call). Yan keeps one source of truth here and may share it with colleagues later if it works well. The virtual system repo also holds a copy of the skills; how that copy relates to this repo is unknown, and keeping it in sync is out of scope. Add `.superpowers/` to `.gitignore` (it is currently empty).

Yan's global instructions: prompts belong in a `prompts.py`, settings in a `config.py`, state in a `states/` folder, and external calls under `integrations/`, for Python backends. If the server is written in Python, follow those rules; if the builder chooses another language, the project-level conventions apply instead. Language and framework are the builder's call (Node 24 and Python 3.12 are installed).

## Goals

- See every in-flight ticket build on one page and tell, in a glance, which one needs Yan.
- Reply to any ticket build without leaving the page.
- Add and close ticket builds freely.
- The same quality of ticket output as the current workflow: same skills, same connectors, same approval gate.
- Always current repo information (fetched main) without disturbing Yan's working folders.

## Non-goals

- Multi-user use, login, hosting, or deployment. Single user, localhost.
- Building or changing the ticket workflow itself (phases, DoR rules).
- Editing any repo other than writing the handoff file; the page never commits or pushes.
- Replacing Claude Code for other work.
- Keeping the virtual system copy of the skills in sync.

## Anti-goals (failures even if the page technically works)

- A ticket created in Linear without Yan's explicit approval.
- A ticket build working from stale or wrong-branch repo content without saying so.
- Yan's local branch, uncommitted changes or working folder being changed by a fetch or a search.
- The page showing "Working" or "Done" when a build is actually stuck or waiting on Yan, so Yan stops noticing.
- Yan losing a conversation when closing or reloading the page: closing a column must not delete the handoff file, and reopening an existing ticket build should resume it (the handoff file is designed for resuming in a fresh session).

## Constraints

- Runs on Yan's Mac only; uses Yan's existing `claude` login and connector access.
- Skills stay in `global-skills/` and are installed via `install.sh`.
- Tickets are created in Linear team `VIR`, project "Virtual Assistant" by the existing `linear-create` skill; this design does not change that.

## Left to the builder

- Language, framework and how the server talks to Claude (CLI vs Agent SDK), once connector access is verified.
- Exact signal for "Needs you" and for the short "Working" note.
- Folder name, config format, how a closed column is reopened, theme.
- How many columns fit before scrolling (Yan usually has about 3; more should still work).

## Calls made after the builder check (all **my call**, Yan to review)

- **First task is a spike on connector access.** Before building the page, start one headless Claude session from a script and check it can reach Linear, Slack and Notion. If it cannot, stop and report to Yan before building anything else; do not silently switch to a different design.
- **Reopening a column restores the chat.** Reuse the Claude session id so the chat history comes back. If that session can no longer be resumed, start a fresh session that reads the handoff file, and say so in the column.
- **A fourth status, "Stuck".** Shown in red when a session has died, errored, or has been silent for a long time. Time limit is the builder's call.
- **Permission prompts are shown, not skipped.** Sessions never run with permissions skipped. A tool-permission prompt shows in the column as "Needs you" for Yan to answer. Linear write tools are not pre-approved, so Claude Code's own permission prompt is a second gate on top of the skill's approval step.
- **Default branch per repo.** Detect it from the repo's `origin/HEAD`, with an optional override in the config. Do not assume `main`.
- **Test for the repo-search change.** A dry run: search a repo that has a stale local main and confirm the result matches `origin/main`.

## Virtual system repo (resolved)

- Path: `/Users/yanzhang/Desktop/virtual-assistant-agent`, a local clone with `origin` = `https://github.com/ageras-com/virtual-assistant-agent.git`. Default branch is `origin/main`. When checked, the local folder was on a feature branch (`vir-907-ws4-...`), which is exactly why the build reads `origin/main` instead of the files on disk. No clone step needed.
- **My call:** the initial repo list holds only this repo and `daily-work-skills`. Other repos on the Mac (for example `~/Desktop/va-agents`, a different repo `ageras-com/va-agents`) can be added in the config later.
