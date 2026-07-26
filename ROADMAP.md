# Roadmap

The active roadmap is maintained in [docs/roadmap.md](docs/roadmap.md).

Current implemented boundary:

- Core Surface package trust;
- Runtime compatibility and attestation;
- isolated, non-executing Semantic Executor;
- Semantic Input compilation and the `boris-execution/1.0` candidate envelope;
- sole public MCP entry `boris.execute`;
- signed stateless HOLD handoff and resume through the same tool;
- developer-only visual MCP surface with model-hidden safe trace;
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

- Policy Kernel;
- admitted State Events and Cycle Guard;
- domain physiology and memory;
- authorized external actions.
