# Roadmap

The active roadmap is maintained in [docs/roadmap.md](docs/roadmap.md).

Current implemented boundary:

- Core Surface package trust;
- versioned public Core v2.31 contract adaptation into the stable Runtime
  surface;
- Runtime compatibility and attestation;
- isolated, non-executing Semantic Executor;
- Semantic Input compilation and the `boris-execution/1.0` candidate envelope;
- sole public MCP entry `boris.execute`;
- ownership-aware uncertainty resolution derived from Core phase capsules;
- Core-compatible `HoldRecord` projection for every `HOLD`, with the blocking
  precondition separated from unknowns and open debts;
- signed operator resolution for every recoverable system `HOLD`, including
  formal predicate and final semantic-submission compliance targets;
- current-cycle `OperatorDecision` with information, assumption, conditional,
  scope-change, and termination modes, without writing semantic memory;
- deterministic non-empty candidate projection for any non-`HOLD` route,
  including resume;
- canonical `SemanticProvider` port and `ServerLLMProvider`, with strict
  compilation and semantic calculation completed inside Runtime by one public
  `boris.execute` call;
- `boris-independent-review/1.0` with a separate O027-owned adversarial method,
  honest Core v2.31 `IND2`, strict review decisions, and exact SHA-256 bindings
  to Semantic Input, calculation, candidate, Core, and RuntimeAttestation;
- public MCP schema limited to `input`, correlation/context, and signed HOLD
  resume; no provider selector or host work-order submission fields;
- non-canonical `ChatGPTHostProvider` with signed `CHATGPT_HOST_ONLY`
  compilation and calculation work orders retained only behind private HTTP
  for compatibility research;
- phase-bound `candidate_result` validation from the canonical primary object,
  followed by one signed diagnostic correction under `HOLD`, with `HOLD`
  preserved if the corrected submission remains invalid; canonical `REPAIR`
  remains deferred until new-revision/new-cycle transitions exist;
- developer-only visual MCP surface v2.5 with separate review, model-hidden safe
  trace, and direct server-side signed operator continuation; no host wake-up
  or ChatGPT-internal orchestration;
- internal stateless CoreSurface-based `/runtime/frame`;
- compact production projection and safe developer projection trace;
- stateless answer validation;
- consolidated architecture with earlier middleware generations removed.

Accepted validation boundary:

- production E2E of one public `boris.execute` call returning
  `semantic_provider: SERVER_LLM` and a substantive semantic candidate was
  observed; full developer trace was unavailable after host model limits were
  exhausted, so the route is accepted with an observability gap rather than
  reopening ChatGPT-host orchestration.

Immediate validation target:

- production E2E returns both the unchanged semantic gate and
  `independent_review.review_version: boris-independent-review/1.0`;
- Review `PASS` on a semantic `HOLD` leaves the semantic gate at `HOLD`;
- no Policy Kernel admission, state mutation, or external action is claimed.

Following stages:

- typed Semantic Input with provenance-bearing facts, evidence, and authority;
- Policy Kernel;
- admitted State Events and Cycle Guard;
- domain physiology and memory;
- delegated `OPERATOR_MACHINE` resolution after a signed authority registry
  exists;
- authorized external actions.
