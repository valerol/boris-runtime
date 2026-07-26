# BORIS Runtime Roadmap

## Completed foundations

### Core Surface

- immutable package loading;
- legacy, release-envelope, and public Core v2 manifests;
- versioned package-contract adapters behind the stable `CoreSurface`;
- separate release and normative identities;
- archive, content-set, manifest, component, checksum, DAG, and validation
  envelope checks;
- native norm catalog projection;
- fail-closed lifecycle handling.

### Runtime compatibility

- explicit receiving-substrate profile;
- package-declared required-check registry;
- canonical `SubstrateDeclaration`;
- `OperatorAcceptance`;
- archive- or repository-content-bound `RuntimeAttestation`;
- fail-closed capability and schema checks.

### Minimal Semantic Executor

- immutable `SemanticInput` and `SemanticView`;
- formal predicate evaluation within the supported DSL;
- structured LLM calculation boundary;
- strict semantic-calculation validation;
- deterministic deontic and gate constraints;
- non-executing `ExecutionCandidate`;
- trace binding to RuntimeAttestation.

### Semantic Execution Entry

- strict application-level `SemanticInputCompiler`;
- scoped acceptance of the server-configured `boris-core` checkout;
- `ExecutionService` route through Runtime Compatibility and Semantic Executor;
- private `POST /runtime/execute`;
- sole public MCP tool `boris.execute`;
- `boris-execution/1.0` envelope marked `status=semantic_candidate`;
- safe developer trace combining lexical projection, compiled input,
  RuntimeAttestation, semantic results, stage ledger, and timings;
- Core v2.31 phase-complete selection, typed applicability/violation
  predicates, capsule context, model-capacity checks, and four-valued
  Predicate DSL compatibility;
- internal `/runtime/frame` retained without a public `boris.frame` alias.

### Closed HOLD handoff and Developer Surface

- typed uncertainty ownership and resolution classes;
- schema-driven internal-object ownership projection from Core phase
  capsules;
- structured operator handoff only when a `HOLD` contains an explicit
  operator-owned target;
- non-operator `HOLD` disclosure without a continuation token;
- non-empty conditional candidate or explicit null-candidate reason;
- HMAC-SHA256 stateless continuation bound to exact `SemanticInput`, Core
  identity, session, HOLD targets, expiry, and resume count;
- resume through the same `boris.execute` without a second public tool;
- exact semantic-input reconstruction without repeated input compilation;
- path-aware semantic unknowns kept separate from signed formal-predicate
  input paths;
- explicit completeness check before semantic recalculation;
- guaranteed non-empty candidate material after a completed non-`HOLD`
  resume, with a trace-marked deterministic projection of the validated
  calculation when the provider returns an empty object;
- no automatic suggestion of the predicate-matching value as an operator
  decision;
- developer-only MCP Apps resource
  `ui://boris/developer-surface-v2.html`;
- complete safe trace delivered to the component through model-hidden `_meta`;
- production MCP tool without a linked Developer Surface.

### Experimental ChatGPT host-only executor

- optional `CHATGPT_HOST_ONLY` provider through the sole `boris.execute` tool;
- signed `COMPILATION` and `CALCULATION` work orders, each consumed by
  `operation=submit` exactly once;
- HMAC binding to the session, Core reference, RuntimeAttestation,
  source material, compiler catalog, `SemanticInput`, Semantic View, prompts,
  response schemas, phase, and selected scope;
- exact JSON Schema supplied to the ChatGPT host, with the existing
  `SemanticInputCompiler` and
  `SemanticCalculationValidator` remaining authoritative;
- zero Runtime LLM/API calls on the host-only route;
- signed HOLD resume skips compilation and starts at `CALCULATION`;
- deterministic gate constraints and ordinary HOLD handoff after submission;
- bounded TTL and size controls;
- existing `OPENAI_API` route retained unchanged;
- in-memory single-process registry only for the PoC.

### Stateless context, validation, and projection observability

- CoreSurface-based internal `/runtime/frame`;
- bounded passive norm projection;
- safe `boris-context/2.0` packet;
- compact responses unless server `BORIS_RUNTIME_MODE=dev` is active;
- safe server-controlled developer projection trace with Core identity, attestation, selected
  and excluded candidates, projection limits, stage timings, and explicit
  capability boundaries;
- deterministic, semantic, and hybrid answer validation;
- private FastAPI and public MCP transport separation.

### Architecture consolidation

- removed Phase 2 local `core/`;
- removed direct machine-JSON `core_retriever/`;
- removed Phase 3 `runtime/`, `protocol/`, and `prompt/`;
- removed compatibility `adapters/` and embedded v0 `archive/`;
- removed stateful `boris.ask`, Runtime sessions, clarification loop, legacy
  `/run`, and compatibility facades;
- made Core Surface the only canonical Core source.

## Current execution limit

The public route now reaches Runtime Compatibility and Semantic Executor, but
every result remains:

- not independently reviewed;
- not admitted by Policy Kernel;
- non-mutating;
- unable to execute external actions.

`HOLD`, `STOP`, and `REPAIR` are normal Runtime results rather than transport
errors. `PASS` is still only a semantic candidate, not final authorization.
Lexical projection remains observability and never determines semantic
applicability.

`HOLD` can request operator input and resume the same semantic calculation
from a signed stateless token only when an unresolved target is explicitly
classified as `OPERATOR_INPUT`. Runtime-owned derivations, future
contingencies, model uncertainty, downstream preconditions, and unresolvable
limitations remain visible without being reassigned to the operator. This
closes the clarification handoff only; it
does not implement Independent Review, Policy Kernel admission, durable cycle
state, memory, or action authorization. Tokens are replayable until expiry and
are globally invalidated by continuation-secret rotation.

## Next architectural stages

### Independent Reviewer

- define `IndependentReview` contract;
- require a genuinely independent evaluation path;
- bind review to the exact `SemanticCalculation`, Core reference, and
  attestation;
- produce no state mutation.

### Policy Kernel

- define deterministic `KernelDecision`;
- enforce authority and operator decisions;
- resolve `HOLD`, `STOP`, and `REPAIR` consequences;
- reject any semantic result that has not passed independent review;
- keep meaning creation outside the kernel.

### State event boundary

- define append-only `StateEvent`;
- admit only Policy Kernel-approved transitions;
- add Cycle Guard and recovery behavior;
- preserve traceability from phenomenon to applied change.

### Domain physiology and memory

- attach operator-approved domain physiology as a distinct layer;
- define ownership, provenance, confidence, and revision rules;
- add long-term memory only after Policy Kernel admission exists;
- keep the Base Core immutable.

### External actions

- define tool and adapter capability contracts;
- authorize action only from a valid `KernelDecision`;
- record evidence and execution result;
- never allow Semantic Executor output to call a tool directly.

## Deferred security work

- packet authenticity and signatures;
- frame registry and TTL;
- persistent continuation registry, single-use enforcement, and targeted
  revocation;
- persistent host work-order registry and multi-worker routing;
- targeted host work-order revocation and audit records;
- measurement of MCP payload and effective ChatGPT context limits on Core
  v2.31;
- revocation and rotation of operator decisions;
- persistent audit storage;
- multi-tenant isolation and authorization.
