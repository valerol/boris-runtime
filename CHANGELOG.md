# Changelog

All notable changes to BORIS Runtime are tracked here.

Format: newest changes first. Future work should be added under `Unreleased`
before each commit.

## Unreleased

- Added Step 2 Gap Loop foundation driven by `core/epistemic_hierarchy.json`.
- Added minimal question memory for asked clarifications, per-topic counts, and
  recent inputs.
- Enforced DOMAIN -> MEMORY -> RUNTIME_STATE -> LLM priority order from JSON.
- Prevented LLM calls during gap clarification decisions.
- Added tests for hierarchy loading, LLM-last behavior, and repeated
  clarification prevention.

## 2026-07-03 - Static domain introspection layer

Commit: `92b1de4 Add static domain introspection layer`

- Added static DOMAIN descriptor fields for capabilities, limitations, version,
  and success criteria.
- Added read-only self-introspection via `kernel/self_introspection.py`.
- Added `SELF_DESCRIPTION` to the runtime response contract.
- Routed explicit introspection prompts through the kernel composition layer.
- Verified normal runtime queries still use the runtime engine path.

## 2026-07-03 - CLI terminal input boundary

Commit: `39efb69 Guard CLI terminal input boundary`

- Added local CLI guards for `quit`, `exit`, `q`, empty input, and `quite`.
- Prevented non-semantic CLI input from being sent into the runtime.
- Improved clarification output so `need_more_input` remains internal trace
  data instead of user-facing text.
- Added regression coverage for answer-to-clarification leakage.

## 2026-07-03 - State machine audit fixes

Commit: `762dd8b Apply state machine audit fixes`

- Clarified that `kernel/runtime.py` is the kernel composition root, not the
  state machine engine.
- Removed unused `ASK_OPERATOR` / `next_true` schema transition from
  `core/schema.json`.
- Made the OpenAI SDK import lazy so local stub mode works without `openai`
  installed.
- Added tests for state-machine ownership and schema transition cleanup.

## 2026-07-03 - State machine closure

Commit: `262af52 Close runtime state machine cycle`

- Added explicit runtime phases: `INPUT`, `ANALYZE`, `DECIDE`, and `FINALIZE`.
- Added a single decision point for terminal runtime responses.
- Ensured one user input resolves to one terminal response.
- Prevented blank CLI prompts from triggering runtime clarification cycles.
- Added tests for normal, empty, and ambiguous input closure behavior.

## 2026-07-03 - LLM test isolation

Commit: `41e04fc Make LLM tests independent of local env`

- Made LLM tests independent from local `.env` values.
- Added explicit no-key test construction for local stub mode.
- Normalized JSON-like OpenAI responses into plain user-facing answers.
- Preserved live OpenAI behavior when `OPENAI_API_KEY` and the SDK are present.

## 2026-07-03 - Runtime v1 response contract

Commit: `9071fc2 Stabilize runtime v1 response contract`

- Added minimal `physiology/` package with default domain physiology.
- Added `runtime/contracts.py` for structured response construction.
- Separated user-facing `answer` from internal `trace`, `state`, and `actions`.
- Kept `content` as a compatibility alias for existing adapters.
- Added domain information to runtime trace/state without changing decisions.
- Added tests for response shape, domain loading, and answer/trace separation.

## 2026-07-02 - Bootable runtime MVP

Commit: `ccb3f66 CODEx edit`

- Added package markers for adapters, core, kernel, and runtime.
- Made schema loading path-relative.
- Added `.env` loading and OpenAI missing-key stub behavior.
- Wired kernel dependencies through the schema-driven runtime engine.
- Added CLI, web, and Telegram adapter contracts.
- Added FastAPI health/event endpoints.
- Added README setup/run instructions and initial tests.

## 2026-07-02 - Initial project skeleton

Commit: `390331d Initial commit`

- Created the initial BORIS Runtime repository structure.
- Added kernel modules for BOIS, SIMA, memory, LLM, gap detection, and runtime
  wiring.
- Added schema-driven runtime engine skeleton and core schema loader.
- Added CLI and web adapter entry points.
- Added initial server, requirements, and environment example.
