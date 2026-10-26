# Agent-system coverage checklist (entry B)

Seeded from the `agent-creation/*` skills in this repo (`new-agent`, `add-hitl`, `add-guardrails`, `add-rag`, `add-eval`) and from the global CLAUDE.md layout rules. For each item report: present, thin, or missing, with the file that shows it.

## Capabilities
- **Prompts**: every agent prompt defined once, by name, in a dedicated `prompts.py` next to its agent (no inline prompts).
- **Agents**: each agent has one clear responsibility and a named prompt.
- **Tool calling**: tools defined with clear schemas; error and empty-result behavior defined; external calls only through `integrations/`.
- **Eval**: eval sets, evaluators and a baseline exist and can be run.
- **Observability**: tracing, logging and alerts cover agent and tool calls; cost and latency visible.
- **Guardrails**: scope guard, input/output checks, refusal behavior.
- **Human in the loop**: escalation or approval points where actions are risky.
- **RAG / retrieval**: sources, chunking, freshness and evaluation, if the agent uses retrieval.
- **Session and state**: history, TTL and turn limits live in `states/`.

## Layout rules (from the global CLAUDE.md)
- Tunable values (model name, temperature, limits, TTL) in `config.py`, not inline.
- State and memory logic in `states/`.
- All external API calls under `integrations/`.
