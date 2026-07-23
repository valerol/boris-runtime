# BOIS / SIMA / BORIS Middleware SDK - Full Execution Roadmap v1

BOIS Middleware SDK - protocol execution layer + deterministic reasoning loop +
adapter abstraction layer.

## Global Architecture

```text
User/UI -> Middleware -> LLM -> Tools -> Memory
```

## Global Principles

- BOIS declarative
- SIMA analytical
- BORIS contextual specialization
- Middleware = execution engine only
- Platform = external

## Current Execution Status

- PHASE 0: completed
- PHASE 1: completed
- PHASE 2: completed
- PHASE 3: completed
- PHASE 4: in progress / partially implemented
- PHASE 5: pending
- PHASE 6: pending
- PHASE 7: pending
- PHASE 8: pending
- PHASE 9: pending
- PHASE 10: pending

---

# PHASE 0 - ARCHITECTURE RESET

Status: completed/current foundation.

- define SDK boundaries
- create root-level SDK structure
- lock BOIS as declarative core
- create documentation set:
  - `docs/vision.md`
  - `docs/architecture.md`
  - `docs/protocol.md`
  - `docs/sdk_api.md`
  - `docs/adapters.md`

---

# PHASE 1 - CLI MVP (RUNTIME CORE v0.1)

Status: completed.

Evidence:
- `1fd0c23 Implement phase 1 strict CLI runtime`

- runtime loop
- protocol parser
- prompt builder
- LLM adapter stub
- CLI execution only
- detect GAP + clarify loop

---

# PHASE 2 - CORE LOADER SYSTEM

Status: completed.

Evidence:
- `0918633 Implement phase 2 core loader system`
- `bbc431e Document runtime session lifecycle`

- load BOIS from .md/.json/.yaml
- folder-based core support
- GitHub release support
- immutable core per session

---

# PHASE 3 - PROTOCOL ENGINE

Status: completed.

Evidence:
- `55d5409 Implement phase 3 protocol engine`
- `7df755a Remove pre-LLM semantic decisions`
- `9464e20 Fix Phase 3 LLM invocation tracing`

- full execution cycle:
  INPUT -> SIMA -> BOIS -> BORIS -> LLM -> PARSER -> LOOP
- gap detection engine
- question memory
- validation layer

---

# PHASE 4 - RUNTIME API AND CHATGPT INTEGRATION

Status: in progress / partially implemented.

Phase 4 is split into:

- Phase 4A Runtime HTTP API / FastAPI: implemented
- Phase 4A.1 API Stabilization: implemented
- Phase 4B MCP Server adapter: implemented
- Phase 4C Remote MCP / ChatGPT Apps readiness: implemented
- Phase 4D Runtime as Context Provider: implemented
- Phase 4D.1 Stateless `boris.validate`: implemented
- Phase 4E Core Surface Foundation: implemented
- Phase 4R Architecture Consolidation: implemented before merge
- Phase 4F Minimal Semantic Executor: implementation and pre-merge hardening complete

Phase 4A provides a thin FastAPI transport layer over `BOISRuntime.run(...)`.
The HTTP API owns request validation and in-memory runtime session plumbing only.
It must not implement BOIS, SIMA, BORIS, protocol logic, memory logic, prompt
building, LLM orchestration, semantic decisions, or MCP logic.

Phase 4A.1 stabilizes the HTTP contract with controlled runtime error responses,
per-session execution locking, session inspection, and single-session reset.
`context` remains transport metadata and is not injected into prompt construction.

Phase 4B introduces an MCP adapter with one tool, `boris.ask`. The adapter calls
the stabilized Runtime HTTP API and does not import or implement Runtime
internals.

Phase 4C adds remote MCP transport suitable for ChatGPT developer-mode connector
testing. It exposes `/mcp` as the public adapter boundary while keeping
`/runtime/ask` private.

Phase 4E introduces a stable, version-independent trust boundary for loading,
checking, and exposing a canonical core package. Runtime does not select
applicable rules or calculate philosophical meaning inside this boundary.

Future Phase 4 hardening remains pending:

- OAuth/auth hardening
- public deployment hardening
- ChatGPT Apps UI/widget layer
- app submission package

---

# PHASE 4D - RUNTIME AS CONTEXT PROVIDER

Status: implemented.

Goal:
Allow Runtime to return a bounded BOIS/SIMA/BORIS context packet while the
client model generates the final answer.

Delivered:
- private `/runtime/frame`;
- MCP `boris.frame`;
- LLM-independent context generation;
- bounded and sanitized public packet;
- non-mutating session behavior.

Acceptance summary:
- `boris.ask` remains backward compatible;
- Runtime API remains private;
- MCP remains the public adapter;
- context packet is explicit, bounded, and leakage-protected.

## PHASE 4D.1 - STATELESS ANSWER VALIDATION

Status: implemented.

Goal:
Validate a client-generated answer against the complete context packet without
storing packets or mutating Runtime state.

Delivered:
- private `/runtime/validate`;
- MCP `boris.validate`;
- deterministic, semantic, and hybrid modes;
- mandatory preflight;
- layered validation report;
- stateless and non-mutating execution.

Boundaries:
- no answer rewriting;
- no packet persistence;
- no `frame_id` lookup;
- no authenticity guarantee;
- no HMAC signing.

Acceptance summary:
- request schema errors remain HTTP 422;
- readable but invalid packets return a validation report;
- deterministic validation remains LLM-free;
- semantic validation is lazy and strictly parsed;
- hybrid validation preserves deterministic structural and security findings;
- `boris.ask` and `boris.frame` remain backward compatible.

### Future improvement - Multilingual Deterministic Validation

Status: non-blocking / pending.

Current deterministic heuristics use English-oriented lexical markers for
relevance, risk, uncertainty, ambiguity, and clarification detection.

For non-English answers, the validator may conservatively return
`INDETERMINATE` more often.

Future scope:
- language-aware heuristic profiles;
- Unicode-aware lexical overlap;
- multilingual disclosure markers;
- language-neutral structural checks;
- regression tests for supported languages.

### Future item - Stateful Frame Registry and Packet Authenticity

Status: pending.

Not part of Phase 4D.1. Future scope may include packet persistence,
`frame_id` lookup, packet TTL, cleanup, session ownership, restart persistence,
HMAC packet signing, signature verification, and tamper detection.

---

# PHASE 4E - CORE SURFACE FOUNDATION

Status: implemented.

Goal:
Prepare Runtime for a final Base Core through a stable, version-independent
boundary while the canon continues to evolve.

Target dependency flow:

```text
Versioned Core Package
    |
    v
Core Surface Adapter
    |
    v
Immutable Core Surface
    |
    v
Semantic Executor
    |
    v
Independent Reviewer
    |
    v
Policy Kernel
```

Only the first three nodes belong to Phase 4E. Semantic Executor, Independent
Reviewer, and Policy Kernel are subsequent consumers and must not be simulated
inside Core Surface.

## Layer Boundaries

Core Surface exposes Base Core without merging it with other physiology:

```text
Base Core      -> universal canonical surface
Personal      -> versioned physiology for one machine
Domain        -> versioned subject-area physiology
Memory        -> mutable experience and evidence
```

Personal and domain layers may reference Base Core IDs. They do not amend Base
Core, and memory records do not become norms automatically.

## Delivered Foundation

- safe loading from a package directory or ZIP archive;
- exact package identity, version, status, inventory, size, and SHA-256 checks;
- separate source kind, archive, content-set, and manifest identity;
- complete checksum reproduction;
- dependency coverage and topological order validation;
- immutable package and norm records;
- separation by the package's native `layer` field;
- evaluation-only loading for candidate packages;
- command-line validation independent of Runtime, LLM, retriever, and adapters;
- synthetic positive and negative tests.

The current v2.18 package is an evaluation fixture. Loading it does not activate
it, publish it, authorize action, or claim semantic compatibility.

## Open Debt - Statement Type Projection

The human-readable canon distinguishes:

- definition;
- invariant;
- mandatory rule;
- conditional rule;
- permission;
- recommendation;
- ground;
- example;
- note.

The current machine catalog exposes three `norm_type` values and carries
modality and operation in separate fields. Their complete canonical mapping is
not fixed in Runtime.

This debt is intentionally non-blocking for the foundation. Core Surface:

- preserves `norm_type`, modality, operation, and all other supplied fields;
- does not reduce them to a Runtime enum;
- accepts unknown future source values as opaque data;
- does not execute an unknown value as a rule.

The debt is revisited only when semantic execution encounters a material
ambiguity that changes the result or when the canon publishes an authoritative
projection.

## Boundaries

Phase 4E does not:

- repair or supplement canonical ontology;
- use the discarded Claim runtime ontology;
- select applicable norms, protocols, constraints, HOLD, or STOP;
- infer conflict priority;
- call an LLM;
- activate a candidate package;
- merge personal or domain physiology into Base Core;
- replace retrieval before an actual Semantic Executor exists.

`RuntimeSession` integration remains deferred. Phase 4F consumes the surface
through a separate compatibility and attestation boundary; attaching it to the
current session would still be premature.

## Acceptance

- the v2.18 archive loads for evaluation with its exact archive SHA-256;
- Base and non-Base norms remain separately addressable;
- unknown source classifications survive unchanged;
- a changed byte, missing component, unsafe path, duplicate norm ID, invalid
  dependency order, or candidate activation attempt is rejected;
- existing Runtime tests and boot paths remain unchanged.

---

# PHASE 4R - ARCHITECTURE CONSOLIDATION

Status: implemented before Phase 4E/4F merge.

Goal:
Remove parallel active execution architectures and establish the exact boundary
between passive package loading and semantic calculation.

Canonical active flow:

```text
api.app
  -> RuntimeRegistry
  -> BOISRuntime
  -> ProtocolEngine
  -> canonical LLM port
```

Delivered:

- converted `MiddlewareEngine` into a compatibility facade over `BOISRuntime`;
- converted `api.fastapi_server.app` into an alias of `api.app.app`;
- preserved deprecated `/run` through that facade for legacy HTTP callers;
- backed `adapters.llm` compatibility names with the canonical LLM port;
- removed the unused earlier prompt builder, response parser, and ProtocolLoop;
- added plain and structured calls to one LLM port, including lazy forwarding
  and controlled provider failures;
- separated Core Surface identity into source kind, exact archive SHA-256,
  content-set SHA-256, manifest SHA-256, and component hashes;
- added `RuntimeCompatibilityVerifier`, `SubstrateDeclaration`,
  `OperatorAcceptance`, and schema-validated `RuntimeAttestation`;
- made accepted exact-archive attestation a prerequisite for Phase 4F;
- kept `ProtocolEngine`, RuntimeSession, API, MCP, memory, and external response
  semantics outside Semantic Executor integration.

`boris.validate` remains Phase 4D stateless answer validation. It is not the
future Independent Reviewer.

---

# PHASE 4F - MINIMAL SEMANTIC EXECUTOR

Status: implementation and pre-merge hardening complete; experimental and
isolated from the canonical Runtime session flow.

Goal:
Prove that Runtime can calculate a grounded, reviewable semantic candidate from
an immutable Core Surface while leaving the statement-type projection debt open.

```text
SemanticInput + Core Surface + RuntimeAttestation
    |
    v
phase/layer/trigger candidate selection
    |
    v
LLM semantic calculation
    |
    v
deterministic source and predicate validation
    |
    v
ExecutionCandidate: PASS / HOLD / STOP / REPAIR
```

Delivered:

- immutable `SemanticInput`, `SemanticView`, and exact Core reference;
- package-owned runtime contract validation and exact-archive attestation;
- fail-closed execution of every declared `VALIDATION_SPEC.required_checks`
  entry through an explicit Runtime registry;
- native phase, trigger, and explicit-layer candidate selection;
- v2.18 three-valued Predicate DSL evaluation;
- structured calculator-specific LLM call;
- strict calculation schema and complete norm-reference validation;
- formal predicate recomputation;
- canonical `REPAIR > STOP > HOLD > PASS` gate precedence;
- deterministic deontic gate constraints, including applicable
  `PROHIBIT -> STOP`;
- conservative `HOLD` guards for material unknowns, unresolved conflicts,
  evaluation-only norms, and unsupported source types;
- immutable trace with selected norms, formal results, source identity,
  RuntimeAttestation hash, and gate constraint;
- experimental CLI and offline precomputed-calculation validation;
- synthetic negative tests and optional real-package v2.18 integration tests.

Boundaries:

- no attachment to `RuntimeSession` or `ProtocolEngine`;
- no Independent Reviewer or C10 independence claim;
- no Policy Kernel or state admission;
- no external action, tool call, or memory write;
- no package or layer activation;
- no mapping from nine human-readable statement types to three machine types;
- no full C00-C11 cycle execution.

Operational acceptance remains separate from implementation. A real run must
provide an explicit OperatorAcceptance for the exact archive and perform a live
structured LLM calculation. Test acceptance records authorize test evaluation
only and do not activate v2.18.

The implementation is described in
[`semantic_executor.md`](semantic_executor.md).

Acceptance summary:

- exact package ID, version, source kind, archive hash, content-set hash,
  manifest hash, component hashes, and attestation hash survive the full
  calculation;
- selected norm references, layers, operations, and formal predicates cannot be
  changed by the calculator;
- v2.18 `N-GEN-027` remains `MANDATORY_RULE + MAY + PERMIT`;
- missing evidence yields a reviewable `HOLD` candidate;
- inactive `T-N-043` cannot produce `PASS`;
- unknown future `norm_type` remains visible and cannot execute automatically;
- a future artifact version is judged by its runtime contract and capabilities,
  not a hard-coded version allowlist;
- an unknown or unimplemented future required check yields `HOLD`;
- an applicable prohibition cannot be converted to `PASS` by the calculator;
- `STOP` and `REPAIR` cannot be weakened to `HOLD` by a material unknown;
- the existing Runtime execution flow remains unchanged.

---

# PHASE 5 - PLATFORM ADAPTERS

Status: pending.

- Telegram adapter
- Web adapter
- Open WebUI adapter
- Dify adapter
- LangGraph adapter

---

# PHASE 6 - MEMORY ABSTRACTION LAYER

Status: pending.

- interface: load/save/search
- backend agnostic
- SQLite/Postgres/Redis/Chroma/Supabase support

---

# PHASE 7 - TOOL ABSTRACTION LAYER

Status: pending.

- search / call_api / run_code / read_file
- tool execution externalized
- middleware does not own tools

---

# PHASE 8 - PACKAGING (SDK)

Status: pending.

- pip install bois-runtime
- stable package entrypoints matching implemented SDK APIs

---

# PHASE 9 - REFERENCE INTEGRATIONS

Status: pending.

- CLI
- Telegram
- Web API
- Open WebUI
- Dify
- LangGraph
- validate single middleware across all

---

# PHASE 10 - STABLE v1.0

Status: pending.

- stable API contract
- documentation freeze
- versioned BOIS/SIMA/BORIS specs
- migration guide

---

# NON-GOALS

- no UI
- no database engine
- no agent autonomy system
- no platform lock-in
