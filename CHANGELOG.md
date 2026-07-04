# Changelog

All notable changes to BOIS / SIMA / BORIS Middleware SDK are tracked here.

## [Unreleased]

Future entries will track:
- protocol changes
- middleware updates
- adapter additions
- breaking changes

## 2026-07-04 - Phase 3 protocol engine

Commits: `55d5409 Implement phase 3 protocol engine`, `7df755a Remove pre-LLM semantic decisions`, `9464e20 Fix Phase 3 LLM invocation tracing`

- Implemented Phase 3 Protocol Engine with RuntimeSession-bound immutable Core.
- Removed pre-LLM semantic decision logic from Protocol Engine.
- Added Phase 3 LLM invocation tracing in protocol metadata
- Ensured new non-exit inputs call the configured LLM adapter
- Marked duplicate cached responses with `llm_called: false`
- Made mock adapter return `ANSWER` by default instead of echoing `QUESTION`
- Made `BOIS_LLM=openai` fail loudly when OpenAI configuration is missing

## 2026-07-04 - Middleware SDK foundation

Commits: `1fd0c23 Implement phase 1 strict CLI runtime`, `0918633 Implement phase 2 core loader system`, `bbc431e Document runtime session lifecycle`, `5beacf8 Normalize middleware SDK documentation`

- Implemented Phase 1 CLI MVP v0.1 strict protocol runtime.
- Implemented Phase 2 deterministic Core Loader System.
- Documented RuntimeSession lifecycle and immutable Core ownership.
- Initial structure created.
- BOIS Middleware SDK roadmap introduced.
- Documentation normalized under `/docs`.
- Broken `ARCHITECTURE.md` / `SDK_SPEC.md` references removed.
- Middleware SDK docs split into vision, architecture, protocol, sdk_api,
  adapters, roadmap, and archive.

## 2026-07-03 - Epistemic gap loop and question memory

Commit: `7972838 Add epistemic gap loop question memory`

- Added Step 2 Gap Loop foundation driven by `core/epistemic_hierarchy.json`.
- Added minimal question memory for asked clarifications, per-topic counts, and
  recent inputs.
- Enforced DOMAIN -> MEMORY -> RUNTIME_STATE -> LLM priority order from JSON.
- Prevented LLM calls during gap clarification decisions.
- Added tests for hierarchy loading, LLM-last behavior, and repeated
  clarification prevention.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-03 - Static domain introspection layer

Commit: `92b1de4 Add static domain introspection layer`

- Added static DOMAIN descriptor fields for capabilities, limitations, version,
  and success criteria.
- Added read-only self-introspection via `kernel/self_introspection.py`.
- Added `SELF_DESCRIPTION` to the runtime response contract.
- Routed explicit introspection prompts through the kernel composition layer.
- Verified normal runtime queries still use the runtime engine path.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-03 - CLI terminal input boundary

Commit: `39efb69 Guard CLI terminal input boundary`

- Added local CLI guards for `quit`, `exit`, `q`, empty input, and `quite`.
- Prevented non-semantic CLI input from being sent into the runtime.
- Improved clarification output so `need_more_input` remains internal trace
  data instead of user-facing text.
- Added regression coverage for answer-to-clarification leakage.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-03 - State machine audit fixes

Commit: `762dd8b Apply state machine audit fixes`

- Clarified that `kernel/runtime.py` is the kernel composition root, not the
  state machine engine.
- Removed unused `ASK_OPERATOR` / `next_true` schema transition from
  `core/schema.json`.
- Made the OpenAI SDK import lazy so local stub mode works without `openai`
  installed.
- Added tests for state-machine ownership and schema transition cleanup.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-03 - State machine closure

Commit: `262af52 Close runtime state machine cycle`

- Added explicit runtime phases: `INPUT`, `ANALYZE`, `DECIDE`, and `FINALIZE`.
- Added a single decision point for terminal runtime responses.
- Ensured one user input resolves to one terminal response.
- Prevented blank CLI prompts from triggering runtime clarification cycles.
- Added tests for normal, empty, and ambiguous input closure behavior.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-03 - LLM test isolation

Commit: `41e04fc Make LLM tests independent of local env`

- Made LLM tests independent from local `.env` values.
- Added explicit no-key test construction for local stub mode.
- Normalized JSON-like OpenAI responses into plain user-facing answers.
- Preserved live OpenAI behavior when `OPENAI_API_KEY` and the SDK are present.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-03 - Runtime v1 response contract

Commit: `9071fc2 Stabilize runtime v1 response contract`

- Added minimal `physiology/` package with default domain physiology.
- Added `runtime/contracts.py` for structured response construction.
- Separated user-facing `answer` from internal `trace`, `state`, and `actions`.
- Kept `content` as a compatibility alias for existing adapters.
- Added domain information to runtime trace/state without changing decisions.
- Added tests for response shape, domain loading, and answer/trace separation.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-02 - Bootable runtime MVP

Commit: `ccb3f66 CODEx edit`

- Added package markers for adapters, core, kernel, and runtime.
- Made schema loading path-relative.
- Added `.env` loading and OpenAI missing-key stub behavior.
- Wired kernel dependencies through the schema-driven runtime engine.
- Added CLI, web, and Telegram adapter contracts.
- Added FastAPI health/event endpoints.
- Added README setup/run instructions and initial tests.
- Archived v0 implementation artifacts under `archive/v0-runtime`.

## 2026-07-02 - Initial project skeleton

Commit: `390331d Initial commit`

- Created the initial BORIS Runtime repository structure.
- Added kernel modules for BOIS, SIMA, memory, LLM, gap detection, and runtime
  wiring.
- Added schema-driven runtime engine skeleton and core schema loader.
- Added CLI and web adapter entry points.
- Added initial server, requirements, and environment example.
- Archived v0 implementation artifacts under `archive/v0-runtime`.
