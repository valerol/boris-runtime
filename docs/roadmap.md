# BORIS Runtime Roadmap

## Completed foundations

### Core Surface

- immutable package loading;
- legacy and release-envelope manifests;
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
- archive-bound `RuntimeAttestation`;
- fail-closed capability and schema checks.

### Minimal Semantic Executor

- immutable `SemanticInput` and `SemanticView`;
- formal predicate evaluation within the supported DSL;
- structured LLM calculation boundary;
- strict semantic-calculation validation;
- deterministic deontic and gate constraints;
- non-executing `ExecutionCandidate`;
- trace binding to RuntimeAttestation.

### Stateless context and validation

- CoreSurface-based `boris.frame`;
- bounded passive norm projection;
- safe `boris-context/2.0` packet;
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

## Current compatibility limit

The current release package may still produce `HOLD` when its Predicate DSL,
deontic operations, schema vocabulary, or gate semantics exceed the receiving
Runtime profile. A successfully loaded package and
`status=INTERNAL_STATIC_PASS` do not imply semantic compatibility or
activation.

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
- revocation and rotation of operator decisions;
- persistent audit storage;
- multi-tenant isolation and authorization.
