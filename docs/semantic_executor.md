# Minimal Semantic Executor

`semantic_executor` is the isolated Phase 4F proof of concept that consumes an
immutable `CoreSurface` and returns a non-executing `ExecutionCandidate`.

It performs a grounded semantic calculation over a real versioned package. The
application `ExecutionService` now invokes this component, but the component
still cannot change state, activate a package, or authorize an external action.

## Boundary

```text
SemanticInput + immutable CoreSurface
    |
    v
accepted RuntimeAttestation
    |
    v
Semantic View
    |
    v
LLM semantic calculation
    |
    v
Deterministic validation and guards
    |
    v
ExecutionCandidate for operator review
```

Independent Review, Policy Kernel admission, state transitions, tools, memory
writes, and external action are outside this phase.

## Runtime Compatibility Boundary

`SemanticExecutor` requires a `RuntimeCompatibilityResult` before it builds the
Semantic View or calls the calculator. The result must prove:

- the package runtime schema was validated;
- the declaration, scoped decision, and attestation refer to the same Core
  source, manifest, content set, and substrate;
- loaded component hashes still match the immutable surface;
- substrate-defined checks produced `PASS`;
- activation status is `ACCEPTED_IN_SCOPE`;
- the operator accepted `semantic_evaluation`.

Without this result execution is rejected before the LLM call. The trace records
the substrate, specification status, activation status, and attestation
SHA-256. See
[`runtime_compatibility.md`](runtime_compatibility.md).

## Input

`SemanticInput` carries:

- a phenomenon;
- the current phase;
- formal predicate facts;
- known unknowns;
- evidence and authority material;
- explicitly enabled personal or domain layers;
- semantic triggers and extra applicability scopes;
- optional targeted norm references for evaluation.

Base Core is always a separate selected layer. Other layers are included only
when named in `active_layers`. Merely including a layer does not activate its
candidate norms.

## Semantic View

The view reads only the stable immutable `CoreSurface`. Package paths and
release dialects are resolved earlier by `core_surface.contracts`.

For legacy packages, that adapter projects the norm and applicability TSV
catalogs. For public Core v2, it projects the canonical JSON norm records,
phase-complete selector, operational semantics, gate contracts, accepted
layers, boot/phase capsules, and per-phase context budget.

Candidate selection is mechanical:

1. native layer;
2. current phase, `ALL_PHASES`, or an explicit extra scope;
3. package selector completeness, or for legacy contracts a wildcard,
   matching input trigger, or an explicit targeted evaluation;
4. lifecycle availability for evaluation.

Public Core v2 declares task-specific narrowing disabled. Runtime therefore
selects the complete accepted Base set for the phase; request triggers cannot
remove norms. Semantic applicability for `KERNEL_INTERPRETED` norms remains an
LLM calculation.

Legacy candidate sets retain the 64-norm safety limit. Public Core v2 supplies
its maximum accepted phase count through the normalized compatibility
contract, with an independent Runtime safety ceiling of 1,024 norms. Oversized
sets and calculation prompts are rejected rather than silently truncated.

## Predicate DSL

Runtime recomputes the package's formal `when` expression. It supports the
legacy three-valued contract and the current four-valued contract:

```text
TRUE | FALSE | UNKNOWN | ERROR
```

The current evaluator implements the Core v2.31 release operator vocabulary:
logical composition, literals, existence and non-empty checks, typed equality
and enum membership, array bounds and uniqueness, identifier checks, scope
relations, subject/cycle relations, package reference resolution, typed pair
membership, ordered ranks, array-wide facts, HTTPS collections, and local
schema validation. Legacy `gte` and `scope_match` remain supported for older
compatible sources.

A missing path remains `UNKNOWN`. A formal `ERROR` is a predicate or type
defect and constrains the gate to `REPAIR`. An unresolved item constrains the
candidate according to its typed owner and resolution route rather than by
the mere presence of an `unknowns` string.

Public Core v2 separates predicate ownership:

- `KERNEL_COMPUTED_TYPED_PREDICATE` records expose independent
  `applicability_predicate` and `violation_predicate`; Runtime computes both
  deterministically;
- `KERNEL_INTERPRETED` records expose canonical semantic content for the
  calculator; their applicability and violation result are semantic outputs;
- internal `violation.*` selectors are never converted into operator-owned
  inputs.

The prompt includes the normalized phase execution context (boot capsule,
phase capsule, and budget declaration). Runtime requires the configured model
capacity to meet the Core phase minimum. It never drops norms to fit a smaller
model context.

## LLM Contract

`LLMSemanticCalculator` quotes the phenomenon, evidence, facts, and all norm
text as untrusted semantic data. The model must return one strict JSON object
containing:

- the exact Core Surface package ID, version, source kind, content-set SHA-256,
  and manifest SHA-256, plus archive SHA-256 when the source is a ZIP;
- the exact phase;
- exactly one result for every selected norm;
- semantic applicability, reasoning, and material unknowns;
- a typed uncertainty record for every disclosed unknown;
- conflicts and their `HOLD` or `STOP` disposition;
- materially distinct considered alternatives;
- a suggested `PASS`, `HOLD`, `STOP`, or `REPAIR`;
- a candidate result that does not claim execution.

The Runtime validator rejects:

- changed Core references or phase;
- omitted, duplicate, fabricated, or unselected norm references;
- changed layer or deontic operation;
- a changed formal predicate result;
- incomplete or extra schema fields;
- conflicts referencing unselected norms;
- any candidate result that claims a state transition, execution, or tool call.

An LLM cannot upgrade a formal `FALSE`, `UNKNOWN`, or `ERROR` predicate to
semantic `TRUE`. An operator-owned or unresolved Runtime-owned uncertainty
constrains `PASS` to `HOLD`. A future contingency, model uncertainty,
downstream precondition, or unresolvable limitation is retained as a
condition, confidence bound, deferred prerequisite, or disclosed limitation;
its presence alone does not force `HOLD`. Unresolved conflicts, unsupported
source types, and evaluation-only candidate norms still constrain the gate.
Formal `ERROR` cannot be weakened below `REPAIR`.

The final gate follows the package's declared precedence:

```text
REPAIR > STOP > HOLD > PASS
```

Consequently, a blocking uncertainty can constrain `PASS` to `HOLD`, but it
cannot weaken an existing `STOP` or `REPAIR`.

Provider failures, empty structured output, and malformed calculations become
controlled `SemanticCalculationError` rejections.

## Calculator providers

`SemanticExecutor` remains calculator-port driven. The ordinary application
route supplies `LLMSemanticCalculator`, which invokes the configured
`OPENAI_API` adapter. The public `CHATGPT_HOST_ONLY` route supplies
`SubmittedSemanticCalculator` only after a signed work order has been prepared
and consumed.

The public MCP input first returns a signed `COMPILATION` work order containing
the ordinary compiler prompt and a strict JSON Schema. Runtime validates the
submitted `semantic_input`, mechanically builds the same `SemanticView` and
`build_semantic_calculation_prompt()` used by `LLMSemanticCalculator`, and
returns a signed `CALCULATION` work order. HMAC tokens and the in-memory
registry bind the exact source, compiler catalog, compiled input, view, prompts,
schemas, Core identity, attestation, session, phase, scope, and expiry.

Every calculation work order includes
`boris-phase-output-contract/1.0`. Runtime resolves the current capsule's
canonical primary output object against its full `required_object_schemas`
entry and installs that schema at
`response_schema.properties.candidate_result`. The future gate context remains
a separate Runtime-owned contract.

Public MCP submission never calls an LLM. Runtime consumes each work order
once, rebuilds its scope against the current Core, verifies all hashes, and
gives the calculation submission to the ordinary
`SemanticCalculationValidator`. All existing ownership checks, formal-result
checks, candidate-result guards, and deterministic gate constraints therefore
remain provider-independent. Direct private HTTP clients use explicit
`operation=prepare` and `operation=submit` values for the same protocol.

A phase-output or semantic-result contract violation on the first submission
returns one new signed calculation work order with `gate=HOLD`, unchanged
semantic bindings, and structured diagnostics for every violated path. The
correction order is also single-use. If it remains invalid, Runtime preserves
`HOLD`, exposes no candidate, and ends automatic submission. No third attempt,
automatic `STOP`, or additional Runtime state is introduced.

This correction is a return under the existing phase `HOLD`, not canonical
`REPAIR`. Core reserves `REPAIR` for creating a new revision, invalidating
affected descendants, retesting dependencies, and beginning a new cycle.

This proof of concept moves both semantic compilation and phase-complete
calculation into the current ChatGPT host, so the host-only route never
constructs the Runtime API adapter. It is not a clean-context model sandbox and
does not yet provide durable or multi-worker work-order state. The calculation
work order discloses the Core minimum context requirement, while the resulting
candidate retains explicit limitations because Runtime cannot attest the host
model identity or its effective context capacity.

An empty calculator `candidate_result` is not a public candidate. At the
application boundary it is accepted only when deterministic constraints leave
the final gate at `HOLD`; the wire envelope then uses
`candidate_result: null` and a mandatory `candidate_unavailable_reason`.
`PASS`, `STOP`, and `REPAIR` require a non-empty candidate result.

The calculator prompt requires non-empty candidate material for every
non-`HOLD` suggested gate. As a deterministic contract guard, if the validated
calculation still contains an empty object and the constrained gate is
`PASS`, `STOP`, or `REPAIR`, Semantic Executor creates a
`boris-candidate-projection/1.0`. It contains only the constrained gate and the
already validated norm results, unknowns, conflicts, and alternatives. The
trace records `CANDIDATE_RESULT_PROJECTED`; the projection does not infer a
new semantic conclusion or claim execution.

Semantic Executor remains stateless. The application-level HOLD handoff signs
the exact `SemanticInput` and later reconstructs it for resume; this does not
change the isolated executor contract, write memory, or admit a state
transition.

`boris-hold-handoff/1.3` exposes operator resolution only when the typed
calculation contains an `OPERATOR_INPUT`. Every `HOLD` projects the Core
`HoldRecord` fields and keeps the blocking precondition separate from unknowns
and open debts. It preserves two separate operator surfaces:

- `semantic_unknowns` contain the unresolved semantic statements, an
  `unknown_id`, and a `target_path` only when exactly one valid path is stated;
- `predicate_inputs` contain the Core-declared machine paths from formal
  predicates whose result is `UNKNOWN`.

Validation-issue summaries are not presented as operator unknowns. Predicate
constraints describe the Core expression but do not suggest its matching value
as the operator answer. `PROVIDE_INFORMATION` requires explicit closure of every
signed semantic unknown and predicate input. A separate
`ALLOW_CONDITIONAL_PROCEEDING` mode may resolve only the operator scope decision
when every signed semantic unknown has no target path, norm reference, or Core
reference and no predicate input remains. That mode preserves all unknowns,
establishes no fact or authority, and triggers a same-phase gate recheck without
forcing `PASS`.

The Semantic View derives an uncertainty-resolution catalog from the current
phase capsule:

- `canonical_object_projection.output_objects` become
  `RUNTIME_DERIVABLE`;
- `required_object_schemas` supply object owners and required fields;
- assessment inputs, `GateEvidence`, `CycleObjectStore`, and other
  `required_evidence_contract` entries become current-cycle or downstream
  contracts according to their declared source class.

The calculator must cite exact catalog references for Runtime and downstream
classes. Runtime rejects attempts to cite a `CURRENT_RUNTIME` entry as
`OPERATOR_INPUT`. `FUTURE_CONTINGENT`, `MODEL_UNCERTAINTY`,
`DOWNSTREAM_PRECONDITION`, and `UNRESOLVABLE_LIMITATION` remain in the
candidate as explicit bounds. A `HOLD` containing no operator-owned target
returns `status=resolution_not_operator_owned`, keeps any conditional
candidate, and issues no continuation token.

## Statement-Type Debt

Phase 4F does not map the nine human-readable statement types onto the three
current machine `norm_type` values.

The adapter currently reports interpretation coverage for the source values
preserved by the current release:

- `INVARIANT`;
- `MANDATORY_RULE`;
- `CONDITIONAL_RULE`.

This coverage set is not a new canonical ontology. `norm_type`, `modality`,
`operation`, `when`, `predicate`, and formulation remain separate source
fields. A future unknown `norm_type` remains visible in the view but forces
`HOLD` instead of being automatically interpreted.

The current-Core `N-GEN-027` integration check deliberately preserves:

```text
norm_type = MANDATORY_RULE
modality = MAY
operation = PERMIT
```

No missing human-readable classification is inferred.

## Programmatic Use

```python
from application.execution import OperatorAcceptanceProvider
from core_surface import load_core_surface
from llm.llm_adapter import OpenAIAdapter
from runtime_compatibility import RuntimeCompatibilityVerifier
from semantic_executor import (
    LLMSemanticCalculator,
    SemanticExecutor,
    SemanticInput,
)

surface = load_core_surface("/opt/boris-core", purpose="evaluation")
acceptance = OperatorAcceptanceProvider().get(surface)
compatibility = RuntimeCompatibilityVerifier().verify(
    surface,
    operator_acceptance=acceptance,
)
calculator = LLMSemanticCalculator(OpenAIAdapter())
executor = SemanticExecutor(surface, calculator, compatibility)

candidate = executor.execute(SemanticInput(
    phenomenon={"claim": "material"},
    phase="C03",
    facts={"evidence": []},
    triggers=("claim:factual",),
))

print(candidate.to_dict())
```

## Experimental CLI

With the configured OpenAI adapter:

```bash
BOIS_LLM=openai python -m semantic_executor \
  /path/to/core.zip \
  /path/to/semantic-input.json \
  --operator-acceptance /path/to/operator-acceptance.json
```

To validate a precomputed calculation without an LLM call:

```bash
python -m semantic_executor \
  /path/to/core.zip \
  /path/to/semantic-input.json \
  --operator-acceptance /path/to/operator-acceptance.json \
  --calculation /path/to/calculation.json
```

The CLI loads packages for `evaluation` only and prints either a validated
`ExecutionCandidate` or a controlled rejection. Without an acceptance record,
the compatibility decision remains `HOLD` and the calculator is not called.
This explicit-file CLI workflow is separate from server deployment;
`ExecutionService` accepts the configured repository directory without a
sidecar file.

## Current Core Integration Tests

The Core repository remains separate from Runtime. By project convention, the
highest available Core release is current; older releases are used only for an
explicit compatibility check. Run the current real-source checks directly
against its checkout:

```bash
BORIS_CURRENT_CORE_PATH=/path/to/boris-core pytest -q \
  tests/test_current_core_integration.py
```

They verify:

- the package's canonical and operational Predicate DSL test vectors;
- all positive and negative assurance gate predicates;
- `N-GEN-027` machine-field separation;
- current-source RuntimeAttestation and content binding;
- `HOLD` for a material claim without evidence;
- `HOLD` for an external action without authority;
- evaluation-only handling of inactive `T-N-043`;
- the application `ExecutionService` route through the real current Core.

Synthetic tests cover layer separation, trigger selection, strict references,
prompt-injection containment, unknown future `norm_type`, equal-priority
conflicts, and prohibition of claimed execution.
They also cover future contract versions without a number allowlist,
exact-source acceptance, stronger-gate preservation, structured lazy LLM
forwarding, and controlled provider failure.
