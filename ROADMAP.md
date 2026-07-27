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
- signed path-aware HOLD handoff only for operator-owned targets and
  complete-target resume through the same tool;
- non-operator HOLD disclosure that preserves the conditional candidate
  without issuing a continuation token;
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
- developer-only visual MCP surface v2 with model-hidden safe trace;
- internal stateless CoreSurface-based `/runtime/frame`;
- compact production projection and safe developer projection trace;
- stateless answer validation;
- consolidated architecture with earlier middleware generations removed.

Immediate next stage:

- Independent Reviewer:
  - define an immutable `IndependentReview` contract;
  - bind review to the exact candidate, Core reference, and attestation;
  - require a genuinely independent evaluation path;
  - keep review non-mutating and separate from Policy Kernel admission.

Following stages:

- durable multi-worker work-order registry;
- Policy Kernel;
- admitted State Events and Cycle Guard;
- domain physiology and memory;
- authorized external actions.
