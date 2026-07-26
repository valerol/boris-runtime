# Core 2.31 Runtime Adaptation Report

## Outcome

The Runtime application is now separated from the Core 2.31 package layout by
a versioned contract adapter. A structurally valid Core 2.31 package can be
loaded, integrity-checked, normalized, attested, selected phase-completely, and
passed to the existing Semantic Executor without adding request- or
domain-specific logic.

The two operational incompatibilities are now resolved inside Runtime:

1. `MANIFEST.json` and `CHECKSUMS.json` declare
   `runtime/operator_acceptance.json`, while the Git tree contains
   `runtime/OPERATOR_ACCEPTANCE.json`. Runtime now maps this one-to-one
   case-only transport difference to the manifest spelling before strict
   inventory and checksum verification. `boris-core` is unchanged.
2. Core 2.31 declares a minimum context window of 524,288 tokens for phases
   C03 and C07. The Runtime deployment configuration now selects
   `gpt-5.6-terra` with explicit `medium` reasoning and declares the model's
   1,050,000-token context capacity.

Production activation now requires publishing and deploying this Runtime
revision, updating the server checkout to Core 2.31, and restarting the
Runtime process.

No case-specific test, fixture, norm, selector, or production branch was added.

## Adaptation complexity

Overall complexity is **high**. The size-limit and manifest changes were
small; the semantic contract migration was not.

| Area | Complexity | Reason |
|---|---:|---|
| Package size and inventory | Low | Raise the safety envelope, normalize only unambiguous case-only transport differences, and run the exact public-v2 manifest/checksum verifier. |
| Canonical norm loading | Medium | Replace TSV assumptions with typed `CORE_CANON.norms` while preserving legacy contracts. |
| Applicability selection | High | Core 2.31 requires phase-complete selection and disables task-specific narrowing. |
| Predicate execution | High | Add eight operators and separate applicability from violation semantics. |
| Semantic prompt materialization | High | Preserve all selected records plus boot/phase capsule context without truncation. |
| Model/runtime operations | Medium | C03/C07 require a 524,288-token context window; the selected Terra route must keep its model, reasoning, timeout, and declared capacity aligned. |
| Future Core updates | Low to medium if public-v2 remains stable | Package changes stay inside the adapter and capability profile. A new semantic contract still requires an explicit adapter revision. |

The adaptation touched the package boundary, compatibility layer, and semantic
view, but did not introduce Independent Review, Policy Kernel admission,
state mutation, memory, or external actions.

## Stable integration boundary

```text
boris-core package
  -> manifest dialect detector
  -> exact integrity verifier
  -> versioned Core contract adapter
  -> stable immutable CoreSurface
  -> Runtime Compatibility capability checks
  -> existing application and Semantic Executor
```

Only the first three components know Core filenames and release dialects.
Application code consumes stable concepts:

- `NormRecord`;
- `ApplicabilityRecord`;
- accepted layers;
- phase descriptions;
- phase execution context;
- normalized Predicate DSL, deontic, and GateDecision semantics;
- a compact compatibility contract.

This avoids scattering checks such as “if version is 2.31” or direct package
paths through request handling.

## Core 2.31 behavior now supported

- `public-core-v2` manifest detection;
- manifest-canonical path spelling with one-to-one case-only transport
  normalization;
- exact normalized manifest inventory with collision rejection;
- SHA-256 and size verification for every checksum entry;
- release/canon identity binding;
- 364 canonical norms from `machine/CORE_CANON.json`;
- Base/Personal layer separation and package acceptance boundary;
- phase-complete selection from `APPLICABILITY_SELECTOR.json`;
- all 12 boot/phase capsule contexts;
- per-phase context budget declarations;
- complete published Predicate DSL operator vocabulary;
- separate deterministic applicability and violation results for the 10
  `KERNEL_COMPUTED_TYPED_PREDICATE` norms;
- semantic calculation for the 354 `KERNEL_INTERPRETED` norms;
- no operator handoff for internal `violation.*` selectors;
- exact phase candidate equivalence with every published task-capsule example.

## Verification evidence

The repository regression suite passes:

```text
237 passed, 11 skipped
```

Using the unchanged `boris-core` 2.31 checkout directly:

- Runtime Compatibility: `PASS / ACCEPTED_IN_SCOPE` when configured with
  the selected model's 1,050,000-token context capacity;
- 20/20 published operational predicate vectors match;
- 10/10 typed critical norm contracts match positive and negative fixtures;
- 12/12 phase gate schemas return `TRUE` for the published positive context
  and `FALSE` for the published negative context;
- all C00-C11 selected norm sets exactly match the published task-capsule
  examples;
- the largest constructed semantic prompts are C03 (849,636 characters) and
  C07 (848,088 characters), below the Runtime character safety envelope but
  subject to the Core-declared token-window requirement.

These are generic contract checks over Core-published records. No user-domain
scenario is embedded in Runtime.

## Required deployment actions

1. Publish and deploy the compatible Runtime revision.
2. Keep the tracked semantic configuration:
   `OPENAI_MODEL=gpt-5.6-terra`,
   `OPENAI_REASONING_EFFORT=medium`, and
   `BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS=1050000`.
3. Keep the MCP and reverse-proxy request timeouts long enough for the
   phase-complete semantic call; the tracked MCP timeout is now 300 seconds.
4. Update `/opt/boris-core` to the current Core 2.31 checkout without renaming
   or modifying Core files.
5. Restart Runtime so its process-local `CoreSurface` cache reloads.
6. Confirm the live `core_ref.artifact_version` is `2.31` and Runtime
   Compatibility is `PASS / ACCEPTED_IN_SCOPE`.

## Reducing future rewrite cost

The current adapter is the immediate containment mechanism. Further reduction
requires a stable, explicitly versioned integration contract owned by
`boris-core`:

1. Publish a small `RUNTIME_INTERFACE.json` with a contract version, canonical
   component roles, selector semantics, required capabilities, and context
   budgets. Runtime should dispatch on that contract version, not artifact
   version.
2. Keep canonical semantic records independent of presentation and transport
   files.
3. Publish generic conformance vectors for every operator and selector rule.
   Do not publish application-domain scenarios as Runtime requirements.
4. Add a compatibility matrix to each Runtime release: supported interface
   dialects, operators, norm modes, gate contract, and capacity.
5. Pin deployment to an exact Core commit/content hash; do not follow repository
   `main` implicitly.
6. Use an atomic release directory or symlink switch, then restart and verify
   the live Core reference.

With that contract, ordinary content changes in Core require no Runtime code
changes. Only a new interface dialect or semantic capability requires a new
adapter implementation.
