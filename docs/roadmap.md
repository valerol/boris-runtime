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
