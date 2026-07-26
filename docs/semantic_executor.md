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

The view reads, from the same verified package:

- `assurance/NORM_CATALOG.tsv`;
- `assurance/NORM_PHASE_APPLICABILITY.tsv`;
- `machine/CORE_CANON.json#predicate_dsl`;
- `machine/CORE_CANON.json#deontic_semantics`;
- `machine/CORE_CANON.json#gate_decision_semantics`.

Candidate selection is mechanical:

1. native layer;
2. current phase, `ALL_PHASES`, or an explicit extra scope;
3. wildcard, matching input trigger, or an explicit targeted evaluation;
4. lifecycle availability for evaluation.

The current phase and trigger select candidates only. Semantic applicability
remains an LLM calculation.

The candidate set is limited to 64 norms. Oversized sets and calculation prompts
are rejected rather than silently truncated.

## Predicate DSL

Runtime recomputes the package's formal `when` expression. It supports the
legacy three-valued contract and the current four-valued contract:

```text
TRUE | FALSE | UNKNOWN | ERROR
```

The current evaluator implements the Core v2.23 release operator vocabulary:
logical composition, literals, existence and non-empty checks, typed equality
and enum membership, array bounds and uniqueness, identifier checks, scope
relations, subject/cycle relations, and package reference resolution. Legacy
`gte` and `scope_match` remain supported for older compatible sources.

A missing path remains `UNKNOWN`. Material unknowns constrain the final
candidate to `HOLD`; a formal `ERROR` is a predicate or type defect and
constrains the gate to `REPAIR`.

## LLM Contract

`LLMSemanticCalculator` quotes the phenomenon, evidence, facts, and all norm
text as untrusted semantic data. The model must return one strict JSON object
containing:

- the exact Core Surface package ID, version, source kind, content-set SHA-256,
  and manifest SHA-256, plus archive SHA-256 when the source is a ZIP;
- the exact phase;
- exactly one result for every selected norm;
- semantic applicability, reasoning, and material unknowns;
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
semantic `TRUE`. A `PASS` is constrained to `HOLD` while material unknowns,
unresolved conflicts, unsupported source types, or evaluation-only candidate
norms remain. Formal `ERROR` cannot be weakened below `REPAIR`.

The final gate follows the package's declared precedence:

```text
REPAIR > STOP > HOLD > PASS
```

Consequently, a material unknown can constrain `PASS` to `HOLD`, but it cannot
weaken an existing `STOP` or `REPAIR`.

Provider failures, empty structured output, and malformed calculations become
controlled `SemanticCalculationError` rejections.

An empty calculator `candidate_result` is not a public candidate. At the
application boundary it is accepted only when deterministic constraints leave
the final gate at `HOLD`; the wire envelope then uses
`candidate_result: null` and a mandatory `candidate_unavailable_reason`.
`PASS`, `STOP`, and `REPAIR` require a non-empty candidate result.

Semantic Executor remains stateless. The application-level HOLD handoff signs
the exact `SemanticInput` and later reconstructs it for resume; this does not
change the isolated executor contract, write memory, or admit a state
transition.

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
