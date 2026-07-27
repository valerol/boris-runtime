# Runtime Compatibility and Attestation

`runtime_compatibility` is the Phase 4R boundary between an immutable
`CoreSurface` and the experimental Semantic Executor.

It implements the package bootstrap contract:

```text
server Core source
  -> immutable CoreSurface
  -> package runtime schemas/templates/specification
  -> SubstrateDeclaration
  -> declared required-check registry
  -> OperatorAcceptance
  -> RuntimeAttestation
  -> semantic_evaluation eligibility
```

Loading a package is not compatibility, and compatibility is not activation.
The calculator is called only when all records refer to the same verified Core
source and the `semantic_evaluation` scope is accepted.

## Package contracts

Legacy and release-envelope verification reads these paths from the loaded
package:

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

The verifier recognizes three runtime-contract dialects:

- legacy `VALIDATION_SPEC.required_checks` IDs are executed through the
  explicit Runtime registry;
- release-envelope `mandatory_checks` are matched exactly against the
  cryptographically bound `VALIDATION_RECEIPT.json`, while receiving-Runtime
  capability checks are still performed independently;
- public Core v2 is verified through the normalized `CoreSurface` contract:
  exact source binding, passive-data boundary, adapter projection, Predicate
  DSL, deontic and gate compatibility, norm-type coverage, selector coverage,
  accepted-layer boundary, phase-complete selection, and declared context
  capacity.

An unknown, duplicate, malformed, missing, or non-passing check prevents
`spec_check_status=PASS`. The legacy registry covers all declared legacy
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
- `manifest_sha256`;
- receiving `substrate_id`.

The declaration and attestation additionally retain `source_kind` and
`content_set_sha256`. `archive_sha256` is present only for an archive source;
it is empty for a directory and never replaced with a directory hash.
RuntimeAttestation records every verified manifest component hash. The final
attestation is itself hashed as canonical JSON, and that hash is written into
each Semantic Executor trace.

For a release-envelope package, `package_id` and `artifact_version` in the
package's canonical runtime records remain the normative identity required by
its schema. `RuntimeCompatibilityResult.package_identity` separately binds the
original `release_package_id`, `release_version`, `normative_package_id`, and
`normative_content_version`; its hash is rechecked before semantic evaluation.
For an archive source, the exact archive and manifest hashes cryptographically
connect both records to one release without changing the package's canonical
schema. For the server `boris-core` checkout, Runtime uses the manifest,
reproducible content-set hash, and component hashes instead. Archive-specific
Core final-record schemas are not misapplied to the directory source.

## Receiving Runtime profile

The Phase 4R profile declares capabilities for:

- archive or repository-directory source binding;
- manifest, component, and content-set binding;
- immutable passive Core Surface handling;
- legacy three-valued and current four-valued Predicate DSL contracts;
- current identifier, scope, reference-resolution, and collection predicate
  operations;
- deontic operation checks;
- GateDecision semantics;
- structured semantic calculation;
- separate IND2 independent review;
- no direct Runtime state mutation.

Its limitations are explicit:

- semantic evaluation only;
- no Policy Kernel transition;
- no external action;
- no stateful orchestration-cycle integration.

These limitations do not disappear when the specification checks pass.

The public Core v2.31 contract adds `all_https`, `all_items_fact`,
`allowed_pair`, `contains`, `count_equals`, `not_equals`, `rank_at_least`, and
`schema_valid`. Runtime implements the complete operator set published in its
operational semantics and preserves four-valued results. A typed predicate
`ERROR` maps to `REPAIR`; it is not treated as an ordinary unknown.

Core v2.31 also publishes a minimum context window for every phase. Runtime
requires `BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS` to be at least the largest
declared minimum before it attests the package for semantic execution. This is
an operator declaration about the configured model, not a value inferred from
the model name. Missing or insufficient capacity produces `HOLD` before the
semantic LLM call.

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

If no decision is supplied, the verifier creates a `HOLD` record. The
specification checks can still pass and an attestation can still be produced,
but the LLM calculator is not called.

At the application boundary, a server-configured directory source such as
`/opt/boris-core` receives a scoped `ACCEPT` because choosing that trusted
checkout is the current Runtime operator protocol. No ZIP or
`operator-acceptance.json` sidecar is required. This implicit decision never
comes from request context and permits only `semantic_evaluation`. Archive
sources retain the explicit acceptance-file protocol.

## Programmatic use

```python
from application.execution import OperatorAcceptanceProvider
from core_surface import load_core_surface
from runtime_compatibility import RuntimeCompatibilityVerifier

surface = load_core_surface("/opt/boris-core", purpose="evaluation")
acceptance = OperatorAcceptanceProvider().get(surface)

compatibility = RuntimeCompatibilityVerifier().verify(
    surface,
    operator_acceptance=acceptance,
)
compatibility.require_semantic_evaluation(surface)
```

`OperatorAcceptanceProvider` reads only trusted server configuration. For an
archive source it requires an explicit acceptance record; for a configured
repository directory it binds the scoped decision to the loaded source
identity.
