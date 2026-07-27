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
- signed `CHATGPT_HOST_ONLY` compilation and calculation work orders through
  the same `boris.execute`, with no public provider selector, zero API calls on
  that route, and the autonomous API provider retained only behind private
  HTTP;
- phase-bound `candidate_result` validation from the canonical primary object,
  followed by one signed diagnostic correction under `HOLD`, with `HOLD`
  preserved if the corrected submission remains invalid; canonical `REPAIR`
  remains deferred until new-revision/new-cycle transitions exist;
- developer-only visual MCP surface v2.1 with model-hidden safe trace and a
  host wake-up bridge for signed operator continuation;
- internal stateless CoreSurface-based `/runtime/frame`;
- compact production projection and safe developer projection trace;
- stateless answer validation;
- consolidated architecture with earlier middleware generations removed.

Immediate validation target:

- production exercise of
  `HOLD → OperatorDecision → signed CALCULATION → host follow-up → same-phase
  gate recheck` for a real system predicate and of terminal compliance-HOLD
  resolution.

Following stages:

- Independent Reviewer;
- durable multi-worker work-order registry;
- Policy Kernel;
- admitted State Events and Cycle Guard;
- domain physiology and memory;
- typed `facts`, `evidence`, and domain `authority`, backed by that physiology
  and memory rather than unverified LLM promotion;
- delegated `OPERATOR_MACHINE` resolution after a signed authority registry
  exists;
- authorized external actions.
