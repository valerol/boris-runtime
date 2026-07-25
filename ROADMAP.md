# Roadmap

The active roadmap is maintained in [docs/roadmap.md](docs/roadmap.md).

Current implemented boundary:

- Core Surface package trust;
- Runtime compatibility and attestation;
- isolated, non-executing Semantic Executor;
- stateless CoreSurface-based `boris.frame`;
- compact production projection and safe developer projection trace;
- stateless answer validation;
- consolidated architecture with earlier middleware generations removed.

Immediate next stage:

- Semantic Execution Entry:
  - compile raw input into a validated `SemanticInput`;
  - route it through Runtime Compatibility and the existing Semantic Executor;
  - return a non-executing `ExecutionCandidate` marked as
    `semantic_candidate`;
  - replace the sole public MCP tool `boris.frame` with the sole public tool
    `boris.execute`, without retaining a public alias;
  - keep frame/projection and `/runtime/frame` as internal read-only
    diagnostics.

Following stages:

- Independent Reviewer;
- Policy Kernel;
- admitted State Events and Cycle Guard;
- domain physiology and memory;
- authorized external actions.
