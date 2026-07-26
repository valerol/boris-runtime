# Core 2.31 Runtime Adaptation Report

## Outcome

The Runtime application is now separated from the Core 2.31 package layout by
a versioned contract adapter. A structurally valid Core 2.31 package can be
loaded, integrity-checked, normalized, attested, selected phase-completely, and
passed to the existing Semantic Executor without adding request- or
domain-specific logic.

Production activation is not yet possible with the currently checked-out
`boris-core` repository and current server model configuration:

1. `MANIFEST.json` and `CHECKSUMS.json` declare
   `runtime/operator_acceptance.json`, but the Git tree contains
   `runtime/OPERATOR_ACCEPTANCE.json`. Exact case-sensitive inventory
   validation correctly rejects this package.
2. Core 2.31 declares a minimum context window of 524,288 tokens for phases
   C03 and C07. The previously configured `gpt-4o` route does not satisfy that
   declaration. Runtime now fails closed until the deployed model and
   `BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS` both meet the requirement.

No case-specific test, fixture, norm, selector, or production branch was added.

## Adaptation complexity

Overall complexity is **high**. The size-limit and manifest changes were
small; the semantic contract migration was not.

| Area | Complexity | Reason |
|---|---:|---|
| Package size and inventory | Low | Raise the safety envelope and add an exact public-v2 manifest/checksum verifier. |
| Canonical norm loading | Medium | Replace TSV assumptions with typed `CORE_CANON.norms` while preserving legacy contracts. |
| Applicability selection | High | Core 2.31 requires phase-complete selection and disables task-specific narrowing. |
| Predicate execution | High | Add eight operators and separate applicability from violation semantics. |
| Semantic prompt materialization | High | Preserve all selected records plus boot/phase capsule context without truncation. |
| Model/runtime operations | High | C03/C07 require a 524,288-token context window and a corresponding model change. |
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
- exact case-sensitive manifest inventory;
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

The unchanged repository regression suite passes:

```text
236 passed, 11 skipped
```

Using a temporary diagnostic copy of Core 2.31 with only the path-case defect
normalized:

- Runtime Compatibility: `PASS / ACCEPTED_IN_SCOPE` when configured with
  524,288 context tokens;
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

1. Correct the path case in `boris-core` and regenerate/revalidate the exact
   release inventory if its checksums or release receipts require it.
2. Deploy a semantic model whose real context capacity is at least 524,288
   tokens.
3. Set `BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS` to that real capacity.
4. Keep the MCP and reverse-proxy request timeouts long enough for the
   phase-complete semantic call; the tracked MCP timeout is now 300 seconds.
5. Deploy the compatible Runtime.
6. Update `/opt/boris-core` to the corrected Core 2.31 package.
7. Restart Runtime so its process-local `CoreSurface` cache reloads.
8. Confirm the live `core_ref.artifact_version` is `2.31` and Runtime
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
