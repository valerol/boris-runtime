# BORIS Runtime Architecture

## Current boundary

The repository has one canonical Core representation: `CoreSurface`.

```text
release package
  -> CoreSurfaceLoader
  -> immutable CoreSurface
     -> Runtime compatibility verification

immutable CoreSurface
  -> application Context Projector
  -> bounded context projection
```

The loader validates package layout, inventory, hashes, identity, dependency
order, lifecycle status, and norm catalog before any consumer sees canonical
records. No active component reads the former local definition folders or an
unverified machine JSON directly.

## Active modules

| Module | Responsibility | Explicit exclusions |
|---|---|---|
| `core_surface` | Verify and expose the passive, query-independent canonical package | Query selection, semantic calculation, state mutation, activation |
| `runtime_compatibility` | Declare substrate capabilities, execute package-required checks, create attestation | Meaning creation, activation, external action |
| `semantic_executor` | Produce a non-executing `ExecutionCandidate` | Independent review, state admission, tools, memory |
| `application` | Build stateless ChatGPT frames and validate supplied answers | Conversation state, semantic authorization, tool execution |
| `llm` | Canonical structured/unstructured inference port | Policy decisions |
| `api` | Private HTTP transport | Core or semantic logic |
| `mcp_server` | Public read-only `boris.frame` transport | Direct Core access, LLM calls, memory |
| `cli` | Local context-frame transport | Alternative engine |

## Semantic path

```text
Core ZIP
  -> CoreSurface
  -> RuntimeCompatibilityVerifier
  -> RuntimeAttestation
  -> SemanticViewBuilder
  -> semantic calculator
  -> deterministic validation and gate constraints
  -> ExecutionCandidate
```

Semantic execution requires an accepted attestation for
`semantic_evaluation`. The result is candidate material only. It cannot mutate
Runtime or Core state.

## ChatGPT context path

```text
Core package
  -> CoreSurface
  -> application Context Projector
  -> bounded lexical projection
  -> ContextProvider
  -> /runtime/frame
  -> boris.frame
  -> ChatGPT-generated answer
```

The lexical projection is not semantic routing. It exposes:

- exact release and normative identity;
- content-set and manifest hashes;
- a bounded set of immutable norm records selected by lexical overlap;
- Base norms as a deterministic fallback when no overlap exists.

The `boris-context/2.0` wire contract exposes the projection as
`projected_core` with `projection_metadata`. Version 1 field names
`retrieved_core` and `retrieval_metadata` are intentionally unsupported. The
producer consumes verified Core Surface records but belongs to `application`,
so `core_surface` remains passive and query-independent.

`boris.frame`:

- does not call an LLM;
- does not create or mutate a server-side session;
- treats `session_id` as correlation data only;
- does not create RuntimeAttestation;
- does not claim package activation or semantic applicability;
- bounds output to six chunks, 3000 characters per chunk, and 12000 total
  projected characters.

If the configured Core package is absent or invalid, the API returns
`core_surface_unavailable` with HTTP 503. It does not fall back to local
definitions.

## Answer validation path

`POST /runtime/validate` is a stateless Phase 4D service. It validates a
caller-supplied answer and complete context packet through:

1. packet preflight and leakage checks;
2. deterministic answer checks;
3. optional semantic validation;
4. deterministic/semantic merge in hybrid mode.

This service is not the future Independent Reviewer. It does not establish
packet authenticity, retain packets, rewrite answers, admit state changes, or
apply an `ExecutionCandidate`.

## Removed architecture

The following top-level packages were deleted:

- `core/` — Phase 2 local definition loader;
- `core_retriever/` — direct machine-JSON embedding path;
- `runtime/`, `protocol/`, `prompt/` — Phase 3 prompt middleware, sessions, and
  clarification loop;
- `adapters/` — unused stubs and LLM compatibility facade;
- `archive/` — embedded v0 source copy.

The private `/runtime/ask`, `/runtime/reset`, `/runtime/session/{id}`, legacy
`/run`, `MiddlewareEngine`, `BOISRuntime`, and `ProtocolEngine` contracts were
removed with those paths.

## Kernel boundary

The former proposed monolithic `bois_kernel` is not an active package. Its
semantic-calculation portion now belongs to `semantic_executor`; its passive
registry belongs to `core_surface`.

The following responsibilities remain intentionally unimplemented and must not
be absorbed by the Semantic Executor:

- `IndependentReviewer`;
- deterministic `PolicyKernel`;
- authority and operator-decision enforcement beyond compatibility acceptance;
- state-event admission;
- Cycle Guard;
- domain physiology;
- long-term memory;
- tool and external action execution.

The future cycle is:

```text
SemanticCalculation
  -> IndependentReview
  -> KernelDecision
  -> StateEvent
```

Only the first contract is implemented. The current `ExecutionCandidate`
packages its result for later review; it is not a `KernelDecision`.

## Dependency rules

- `core_surface` imports no application, API, MCP, LLM, compatibility, or
  executor code.
- `runtime_compatibility` may read immutable Core Surface data.
- `semantic_executor` may consume Core Surface and compatibility records.
- `application` may consume Core Surface and the LLM port, but not Semantic
  Executor internals.
- `api` may import `application`, never the inverse.
- `mcp_server` communicates with `api` only through HTTP.
- no active module may import a removed top-level package.
