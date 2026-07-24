# Runtime Compatibility and Attestation

`runtime_compatibility` is the Phase 4R boundary between an immutable
`CoreSurface` and the experimental Semantic Executor.

It implements the package bootstrap contract:

```text
original Core ZIP
  -> immutable CoreSurface
  -> package runtime schemas/templates/specification
  -> SubstrateDeclaration
  -> declared required-check registry
  -> OperatorAcceptance
  -> RuntimeAttestation
  -> semantic_evaluation eligibility
```

Loading a package is not compatibility, and compatibility is not activation.
The calculator is called only when all three records refer to the same exact
archive and the operator has accepted the `semantic_evaluation` scope.

## Package contracts

The verifier reads these paths from the loaded package:

- `schema/RUNTIME_SCHEMAS.json`;
- `runtime/RUNTIME_TEMPLATES.json`;
- `assurance/VALIDATION_SPEC.json`;
- `machine/CORE_CANON.json#predicate_dsl`;
- `machine/CORE_CANON.json#deontic_semantics`;
- `machine/CORE_CANON.json#gate_decision_semantics`.

Package ID and artifact version must agree with the immutable surface. There is
no hard-coded version allowlist. A future package can pass only when its own
contract uses the supported schema vocabulary and its declared capabilities
match the receiving Runtime profile. Unsupported contract features fail closed.

The verifier recognizes both runtime-contract dialects:

- legacy `VALIDATION_SPEC.required_checks` IDs are executed through the
  explicit Runtime registry;
- release-envelope `mandatory_checks` are matched exactly against the
  cryptographically bound `VALIDATION_RECEIPT.json`, while receiving-Runtime
  capability checks are still performed independently.

An unknown, duplicate, malformed, missing, or non-passing check prevents
`spec_check_status=PASS`. The v2.18 registry covers all 21 declared legacy
checks. A release receipt is evidence of package static validation, not proof
that the receiving Runtime supports a new Predicate DSL, deontic operation, or
GateDecision contract.

The local JSON Schema evaluator implements the vocabulary used by the current
runtime records, including local `$ref`, `oneOf`, `allOf`, conditional
`if`/`then`, collection bounds and uniqueness, date-time format, object, array,
scalar and null types, required fields, properties, additional properties,
items, const, enum, regex pattern, and minimum string length. A package using
an unimplemented schema keyword is rejected rather than partially validated.

## Identity

All runtime records bind:

- `package_id`;
- `artifact_version`;
- exact `archive_sha256`;
- `manifest_sha256`;
- receiving `substrate_id`.

The declaration and attestation additionally retain `source_kind` and
`content_set_sha256`. RuntimeAttestation records every verified manifest
component hash. The final attestation is itself hashed as canonical JSON, and
that hash is written into each Semantic Executor trace.

For a release-envelope package, `package_id` and `artifact_version` in the
package's canonical runtime records remain the normative identity required by
its schema. `RuntimeCompatibilityResult.package_identity` separately binds the
original `release_package_id`, `release_version`, `normative_package_id`, and
`normative_content_version`; its hash is rechecked before semantic evaluation.
The exact archive and manifest hashes cryptographically connect both records to
one release without changing the package's canonical schema.

A directory source can still be checked by `core_surface`, but it cannot produce
an archive-bound RuntimeAttestation.

## Receiving Runtime profile

The Phase 4R profile declares capabilities for:

- archive, manifest, component, and content-set binding;
- immutable passive Core Surface handling;
- the three-valued Predicate DSL;
- deontic operation checks;
- GateDecision semantics;
- structured semantic calculation;
- no direct Runtime state mutation.

Its limitations are explicit:

- semantic evaluation only;
- no Independent Reviewer;
- no Policy Kernel transition;
- no external action;
- no RuntimeSession integration.

These limitations do not disappear when the specification checks pass.

## Operator decision

`OperatorAcceptance` supports `ACCEPT`, `HOLD`, and `REJECT`.

For Phase 4F execution, `ACCEPT` must include:

```json
{
  "accepted_scope": ["semantic_evaluation"]
}
```

`ACCEPTED_IN_SCOPE` does not activate the Core package, authorize an external
action, or permit state mutation. It authorizes only the isolated semantic
evaluation described in Phase 4F.

If no decision is supplied, the verifier creates a schema-valid `HOLD` record.
The specification checks can still pass and an attestation can still be
produced, but the LLM calculator is not called.

## Programmatic use

```python
from core_surface import load_core_surface
from runtime_compatibility import (
    OperatorAcceptance,
    RuntimeCompatibilityVerifier,
)

surface = load_core_surface("/path/to/core.zip", purpose="evaluation")
acceptance = OperatorAcceptance(
    package_id=surface.package_id,
    artifact_version=surface.artifact_version,
    archive_sha256=surface.archive_sha256,
    manifest_sha256=surface.manifest_sha256,
    operator_role="OPERATOR",
    decision="ACCEPT",
    accepted_scope=("semantic_evaluation",),
    decision_time="2026-07-23T00:00:00Z",
    revocation_route="Replace this OperatorAcceptance record.",
)

compatibility = RuntimeCompatibilityVerifier().verify(
    surface,
    operator_acceptance=acceptance,
)
compatibility.require_semantic_evaluation(surface)
```

The decision time and role above are examples; a real record must contain the
actual operator decision.
