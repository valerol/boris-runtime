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

### Stateless context, validation, and projection observability

- CoreSurface-based `boris.frame`;
- bounded passive norm projection;
- safe `boris-context/2.0` packet;
- compact `default` and `production` responses;
- safe `developer` projection trace with Core identity, attestation, selected
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

The current release package may still produce `HOLD` when its Predicate DSL,
deontic operations, schema vocabulary, or gate semantics exceed the receiving
Runtime profile. A successfully loaded package and
`status=INTERNAL_STATIC_PASS` do not imply semantic compatibility or
activation.

The Semantic Executor is currently available only as an isolated internal
component. The public `boris.frame` route performs bounded lexical projection
and does not compile a `SemanticInput` or invoke `SemanticExecutor.execute()`.
Its selected objects are retrieval candidates, not semantically applicable or
policy-admitted norms.

## Immediate next milestone: Semantic Execution Entry

### Goal

Connect the existing Semantic Executor to the application, private API, and
public MCP path without introducing a second public route or renaming unrelated
internal components.

The target path is:

```text
MCP boris.execute
  -> private POST /runtime/execute
  -> ExecutionService
  -> Runtime Compatibility and RuntimeAttestation
  -> validated SemanticInput
  -> SemanticExecutor
  -> non-executing ExecutionCandidate
```

### Scope

- add a minimal application-level `SemanticInputCompiler` for raw user input;
- treat user input as an untrusted phenomenon and do not invent facts,
  evidence, authority, norm references, phases, layers, or triggers;
- validate all compiled identifiers against the verified Core Surface and fail
  closed on invalid compiler output;
- load server-side `OperatorAcceptance` and check Runtime Compatibility before
  any semantic LLM call;
- add an application-level `ExecutionService` that invokes the existing
  Semantic Executor;
- add private `POST /runtime/execute` while retaining `/runtime/frame` as an
  internal read-only diagnostic route;
- atomically replace the sole public MCP tool `boris.frame` with the sole
  public tool `boris.execute`;
- do not retain a public `boris.frame` alias;
- preserve `default`, `production`, and `developer` modes on the single
  execution route;
- return an execution envelope marked `status=semantic_candidate`, including
  gate, unknowns, conflicts, alternatives, and explicit limitations;
- extend developer mode with the safe projection, compiled `SemanticInput`,
  attestation, semantic trace, validation issues, invoked and absent stages,
  and timings.

The lexical Context Projector remains an observability source. It must not
decide semantic applicability or automatically populate requested norm
references.

### Explicit limitations

Every result from this milestone remains:

- not independently reviewed;
- not admitted by Policy Kernel;
- non-mutating;
- unable to execute external actions.

`HOLD`, `STOP`, and `REPAIR` are normal Runtime results rather than transport
errors. The execution envelope must not imply that any unavailable downstream
stage ran.

### Out of scope

- Independent Reviewer;
- Policy Kernel;
- automatic phase transitions;
- State Events and Cycle Guard;
- memory and domain physiology;
- external tool calls and action execution;
- new architecture directories for future-only components.

### Completion criteria

- the MCP tool list is exactly `{"boris.execute"}`;
- `boris.frame` is absent from the public MCP contract;
- `/runtime/frame` remains available internally;
- ordinary MCP input reaches Runtime Compatibility and the Semantic Executor;
- invalid or mismatched `OperatorAcceptance` fails closed before semantic LLM
  execution;
- invalid phases, triggers, layers, and norm references are rejected;
- constrained gates cannot be weakened by later presentation logic;
- production omits developer trace;
- developer mode contains projection, SemanticInput, attestation, and execution
  trace;
- the public result is explicitly a `semantic_candidate`;
- existing and Core v2.18 integration tests pass.

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
