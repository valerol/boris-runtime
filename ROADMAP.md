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
- signed path-aware HOLD handoff with distinct complete-information and bounded
  conditional-proceeding resolution modes through the same tool;
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

- typed Semantic Input:
  - compile established material into explicit `facts`, `evidence`, and
    `authority` objects rather than retaining it only in `phenomenon.input`;
  - preserve source identity, reliability, provenance, and claim linkage;
  - reject unsupported fact/evidence/authority promotion fail-closed;
  - add trace links from source material to semantic claims and norm results.

Following stages:

- Independent Reviewer;
- durable multi-worker work-order registry;
- Policy Kernel;
- admitted State Events and Cycle Guard;
- domain physiology and memory;
- authorized external actions.
