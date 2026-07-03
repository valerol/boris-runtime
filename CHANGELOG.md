# Changelog

All notable changes to BORIS Runtime are tracked here.

Format: newest changes first. Future work should be added under `Unreleased`
before each commit.

## Unreleased

- Added LLM-first semantic interpretation before BOIS/SIMA/Gap Loop.
- Added structured semantic interpretation output for LLM-backed and local
  no-key operation.
- Updated the schema-driven flow to run semantic interpretation, then BOIS,
  then SIMA, then Gap Loop decision.
- Removed hardcoded self-introspection trigger maps from runtime routing.
- Added tests for semantic interpretation shape, schema ordering, and LLM
  interpretation vs final-answer call boundaries.

## 2026-07-03 - Runtime decision gate enforcement

Commit: `359fbfd Enforce runtime decision gate`

- Renamed the runtime engine decision method to `decision_gate`.
- Ensured engine decision/output routing respects the gate result only.
- Kept BOIS/SIMA/GAP modules as signal providers rather than final response
  authorities.

## 2026-07-03 - Kernel decision gate consolidation

Commit: `1550635 Unify kernel decision gate`

- Added a single kernel-level decision gate for Epistemic Hierarchy, Gap Loop,
  question memory, and self-description routing.
- Preserved the runtime response contract while centralizing final type
  selection.

## 2026-07-03 - Roadmap governance layer

Commit: `ac93269 Add roadmap governance ledger`

- Added audit-only roadmap governance layer via `core/roadmap.json`.
- Added controlled roadmap loading/saving/completion helpers.
- Added tests that roadmap is not imported by runtime decision code.

## 2026-07-03 - Epistemic gap loop and question memory

Commit: `7972838 Add epistemic gap loop question memory`

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
