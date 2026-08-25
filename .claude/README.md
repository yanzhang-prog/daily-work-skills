# .claude/ Reference

Claude Code workflow configuration for galactus. This directory is for agent
workflow, session discipline, hooks, and ticket-scoped research/plans. Durable
technical knowledge belongs in the repo-root `docs/` tree.

> **Note on portability:** this `.claude/` folder was copied out of a
> company repo. Most skills are generic, but a few carry hardcoded paths or
> tooling from the original author's machine and need customization before
> they'll run for you — e.g. `/sync-sessions`
> (`skills/knowledge-creation/sync-sessions/SKILL.md`) points at a specific
> person's local `librarian`/`cartographer` setup under `/Users/ramsey.wise/...`.
> Check a skill's `SKILL.md` for absolute paths before invoking it.

## Daily AI Engineering Workflow

This repo uses `.claude/skills/` as a **daily workflow automation layer for AI engineering**. Each skill is a reusable Claude command that encodes how agent work should happen: investigate first, plan explicitly, change code in small verified steps, run evals/tests, review the diff, update docs, and only then commit or open a PR.

The workflow is for **software engineers building AI systems**. It keeps normal engineering discipline — tests, PR hygiene, debugging, architecture review, docs, and release readiness — but specializes the automation around agents, RAG, guardrails, grounding, eval datasets, graders, LangGraph/ADK parity, and stakeholder-ready reports.

The daily loop looks like this:

| Moment | What the skills automate | Typical commands |
|---|---|---|
| Intake and scoping | Turn fuzzy work into a clear initiative, spike, plan, or ticket backlog. | `/design-sprint`, `/scope-initiative`, `/linear-spike`, `/doc-to-linear-tickets` |
| Research | Explore code and docs, compare approaches, preserve findings as durable research notes. | `/research-review`, `/prototype`, `/shared-language` |
| Planning | Convert findings into an executable implementation plan with acceptance criteria and test commands. | `/plan-review`, `/feature-spec` |
| Implementation | Execute the plan step by step, or use a tighter loop for bugs and risky behavior changes. | `/execute-plan`, `/tdd`, `/code-debug` |
| AI-system buildout | Add or upgrade agents, retrieval, guardrails, HITL, eval harnesses, and TS/Python parity checks. | `/new-support-agent`, `/add-rag`, `/add-guardrails`, `/add-eval`, `/add-hitl`, `/ts-agent-parity` |
| Evaluation | Add graders/metrics/datasets, run agent evals, regenerate reports, and promote notebook experiments into the eval pipeline. | `/eval-pipeline`, `/va-eval`, `/nbk-to-eval`, `/eval-docs` |
| Quality gate | Run DoD, structural review, security review, plan-fidelity review, PR review, and proactive codebase scans. | `/dod-check`, `/run-code-review`, `/review-pr`, `/akira` |
| Shipping | Commit, open PRs, resolve conflicts, checkpoint the session, and preserve knowledge for future agents. | `/quick-commit`, `/quick-pr`, `/compact-session`, `/knowledge-share`, `/tooling-deck` |

Compared with generic "real engineering" skill packs such as Matt Pocock's `mattpocock/skills`, this setup is more specialized and production-context-aware. Generic packs emphasize reusable fundamentals like alignment interviews, TDD, disciplined diagnosis, architecture review, and issue triage. Galactus keeps those fundamentals, but applies them to AI-product work: support-agent scaffolding, Bedrock KB retrieval, CRAG, grounding, prompt/version tracking, eval harnesses, grader calibration, Langfuse/LangSmith, report generation, and agent parity across Python and TypeScript.

The rule of thumb: use a galactus skill when the task affects agents, evals, RAG, guardrails, reports, planning, or delivery. Use the skill as the workflow, not just as a prompt.

## Claude Skills Overview

Use this index to pick the right command. The full delivery loop is for substantial work; the focused loops are for narrow bugs, spikes, tests, reviews, and docs.

### Main Delivery Loop

| Phase | Skill | Purpose |
|---|---|---|
| Research | `/research-review` | Explore code, investigate bugs, compare approaches, and write `.claude/docs/research/...` artifacts. |
| Plan | `/plan-review` | Create, review, or refine implementation plans in `.claude/docs/plans/`; includes execute-readiness checks. |
| Execute | `/execute-plan` | Implement the active plan step by step, testing each step and marking progress in the plan. |
| Done gate | `/dod-check` | Check acceptance criteria, tests, Linear linkage, docs, and deployment readiness before PR. |
| Review | `/run-code-review` | Full pre-PR quality gate: verify, simplify, structural review, security, plan fidelity, DoD, docs. |
| PR | `/quick-pr` | Stage, commit, push, open PR, resolve conflicts, and merge when requested. |
| Commit only | `/quick-commit` | Create a feature branch and commit without opening a PR. |
| Checkpoint | `/compact-session` | Save session notes/artifacts, commit/push when appropriate, and compact context for continuation. |

### Focused Engineering Loops

| Skill | Use when |
|---|---|
| `/tdd` | You want red-green-refactor for risky behavior changes, regression fixes, agents, evals, graders, retrieval, or reporting. |
| `/code-debug` | Something is broken: build a reproducible feedback loop, reproduce, hypothesize, instrument, fix, regression-test. |
| `/prototype` | You need a throwaway spike to answer a feasibility/API/design question before production implementation. |
| `/akira` | You want proactive quality review: `kiyoko` for exploratory questions, `kaneda` for parallel scan, `dao/satori` for triaged fixes. |
| `/review-pr` | You need to review an existing PR against project standards and task acceptance criteria. |

### Planning And Product Ops

| Skill | Use when |
|---|---|
| `/design-sprint` | Starting a new product, feature, or platform initiative from scratch. |
| `/define-milestones` | Group initiatives by release/product goal or plan a milestone/quarter. |
| `/scope-initiative` | Turn an agreed initiative into a Linear-ready technical backlog. |
| `/doc-to-linear-tickets` | Convert a planning doc/spec into Linear issues. |
| `/execute-tasks` | Work through `TASKS.md` or planned milestone tasks. |
| `/linear-spike` | Create a time-boxed Linear spike for research or prototyping. |
| `/github-projects` | Sync issue state with GitHub Projects V2. |

### Agent And Eval Creation

| Skill | Use when |
|---|---|
| `/new-agent` | Scaffold a framework-agnostic LangGraph or ADK agent. |
| `/new-support-agent` | Scaffold a galactus support agent with RAG, guardrails, eval harness, and docs. |
| `/add-rag` | Add or upgrade Bedrock KB retrieval and optional CRAG loop. |
| `/add-guardrails` | Wire the 5-layer safeguard pipeline into an agent. |
| `/add-eval` | Add an eval harness, dataset, and graders to an agent. |
| `/add-hitl` | Add human-in-the-loop interrupt gates to a LangGraph agent. |
| `/ts-agent-parity` | Check TS agent repos such as `va-agents` against galactus Python schemas, prompts, guardrails, evals, and smoke tests. |
| `/eval-pipeline` | Add a grader, dataset, metric, or pipeline entry point under `evals/`. |
| `/nbk-to-eval` | Promote a notebook-developed grader into `evals/graders/`. |
| `/eval-docs` | Regenerate/update canonical eval documentation from reports and data. |
| `/va-eval` | Add or run VA multi-agent evals for ADK routing, LangSmith experiments, or chat quality scoring. |

### Knowledge, Docs, And Meta

| Skill | Use when |
|---|---|
| `/shared-language` | Capture glossary terms for recurring agent/eval/RAG language in existing docs. |
| `/knowledge-share` | Create stakeholder-facing Notion/Drive/Slides artifacts from repo state. |
| `/tooling-deck` | Update the repo tooling overview after new tooling lands. |
| `/skill-creator` | Create or improve a reusable skill. |
| `/sync-sessions` | Sync Claude sessions into librarian/raw sessions and run weekly insights analysis. |
| `/claude-insights` | Generate or validate cartographer HTML insights from session notes/JSONL. |
| `/feature-spec` | Write a targeted single-function/algorithm spec before implementation. |

### Skill Evaluation

| Skill | Use when |
|---|---|
| `/skill-eval-grader` | Grade a skill execution transcript against expectations. |
| `/skill-eval-comparator` | Blind-compare two skill outputs. |
| `/skill-eval-analyzer` | Unblind a winning comparison and explain why it won. |

## Current Command Surface

```bash
# Setup
make install
make install-dev
make hooks-install

# Tests
uv run pytest tests/ -q --tb=short -W ignore::DeprecationWarning
make test-smoke
make test-agents
make test-integration

# Support agents
make sa-up
make sa-adk-bedrock-up
make sa-smoke
make sa-eval-quality

# Article corpus
make articles-fetch
make articles-to-jsonl
make corpus-ingest
make corpus-refresh

# Eval front door
uv run python -m evals.pipelines.run stats --dir data/datasets/bkh/eval_sets/
uv run python -m evals.pipelines.run quality --dataset <responses.jsonl> --tier calibrated --limit 20
uv run python -m evals.pipelines.run live --run-name smoke --jsonl <dataset.jsonl> --endpoint http://localhost:8011/chat --tier heuristic
uv run python -m evals.pipelines.run langfuse --run-name hc-adk --dataset hc-support-agents-golden-597 --endpoint http://localhost:8011/chat
uv run python -m evals.pipelines.run render <report-data.json>

# LangFuse prompt admin
make migrate-prompts
make check-prompt-sync
```

Prefer the `uv run python -m evals.pipelines.run ...` dispatcher for eval
experiments. The Makefile intentionally stays thin.

## Directory Map

```text
.claude/
├── README.md
├── CLAUDE.md                 # Claude-specific session conventions
├── settings.json             # Project permissions and hook wiring
├── commands/                 # Thin wrappers around workflow skills
├── docs/
│   ├── plans/                # Active/recent implementation plans
│   └── research/             # Ticket-scoped investigations
├── hooks/                    # PreToolUse/PostToolUse/Stop shell guards
└── skills/
    ├── agent-creation/       # Support-agent scaffolding and capabilities
    ├── eval-creation/        # Eval datasets, graders, reports
    ├── workflow/             # research → plan → execute → review → PR
    ├── planning/             # Linear/GitHub planning helpers
    ├── knowledge-creation/   # Docs/session/skill knowledge workflows
    └── skill-eval/           # Meta-evaluation of skills
```

## Workflow Loop

```text
/research → /plan → plan review → /execute → /run-code-review → /quick-pr
```

- Research artifacts live in `.claude/docs/research/`.
- Plans live in `.claude/docs/plans/`.
- Promote durable lessons into `docs/` when a result is no longer ticket-local.
- Archive or mark completed plans with a `## Done` note and Linear ticket link.

## What To Load First

| Task | Read first |
|---|---|
| Run or extend evals | `evals/README.md`, `evals/graders/README.md` |
| Data ingestion/preprocessing | `core/README.md`, `data/README.md` |
| Support-agent behavior | `docs/support-agents/invocation-flow.md` |
| Guardrails | `docs/support-agents/safeguards-architecture.md`, `src/support_agents/guardrails/README.md` |
| RAG/corpus work | `docs/rag/hc-rag-pipeline.md`, `docs/rag/bedrock-kb.md` |
| Agent comparison | `docs/frameworks/agent-feature-parity.md` |
| Repo-wide tooling map | `docs/OVERVIEW.md` |

## Hooks

Project hooks enforce safety and structure around Claude Code tool use:

- `structure-guard.sh` keeps `evals/` limited to `graders/`, `metrics/`, `pipelines/`, and `reports/`.
- `secrets-scan.sh` blocks obvious secrets in edits.
- `risky-git-guard.sh` blocks destructive git commands.
- `branch-guard.sh` enforces ticket-style branch names for commits.
- `dor-guard.sh` and `dod-guard.sh` provide plan/readiness checks.
- Additional hooks in `settings.json` cover tests-before-commit, ruff reminders, notifications, and pre-compact checkpoints.

Keep hook docs in sync with `docs/dev/hooks-architecture.md`.
