# Theme 05 Agent Context Pack

This folder is designed to be copied into the implementation repository before giving the task to a coding agent.

## How to use

1. Copy the entire contents into the repository root.
2. Give the coding agent the text from `MASTER_AGENT_PROMPT.md`.
3. Tell it to obey `AGENTS.md`.
4. Let it implement in the order in `docs/08_IMPLEMENTATION_WORKFLOW.md`.
5. Keep `docs/STATUS.md` under version control so work can continue across agent sessions.
6. When Samsung releases/provides the official evaluation kit, add it to the repository and tell the agent to run it immediately.

## Documents

- `AGENTS.md` — permanent repository-level coding instructions.
- `MASTER_AGENT_PROMPT.md` — the first prompt to give the coding agent.
- `docs/00_REQUIREMENTS_SOURCE_OF_TRUTH.md` — official challenge requirements.
- `docs/01_PRODUCT_SCOPE.md` — what is being built / not built.
- `docs/02_ARCHITECTURE.md` — recommended architecture.
- `docs/03_PROTOCOL_AND_DATA_MODELS.md` — internal typed contracts.
- `docs/04_STATE_INTERRUPTION_AND_SAFETY.md` — core interruption and idempotency logic.
- `docs/05_MULTIMODAL.md` — audio/vision architecture.
- `docs/06_TOOL_SYSTEM.md` — dynamic tool manifests and lifecycle.
- `docs/07_TESTING_AND_EVALUATION.md` — deterministic/adversarial testing plan.
- `docs/08_IMPLEMENTATION_WORKFLOW.md` — exact implementation order and gates.
- `docs/09_DEMO_AND_SUBMISSION.md` — demo/deck/submission requirements.
- `docs/10_DEFINITION_OF_DONE.md` — completion checklist.
- `docs/11_FAILURE_MODES_AND_REVIEW_CHECKLIST.md` — code review traps.
- `docs/STATUS.md` — living progress/decision log.

## Provenance

The official-requirement sections were derived from the user-provided:

- Samsung Theme 05 guide, v1.0.0, pages 1–3.
- Samsung PRISM GenAI Hackathon 3rd Edition 2026–27 guide, especially pages 9–13.

Engineering architecture in the remaining documents is a recommended implementation strategy designed to satisfy those requirements; it is not claimed to be mandated by Samsung.
