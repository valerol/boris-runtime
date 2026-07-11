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
Add a second Runtime/MCP mode where Runtime does not generate the final answer.
Instead, Runtime returns a structured BOIS/SIMA/BORIS context packet that
ChatGPT can use as the controlling frame for its own answer.

Current full-answer mode:
- `boris.ask`
- Runtime performs framing/retrieval/reasoning
- Runtime calls OpenAI API through the configured LLM adapter
- Runtime returns a final protocol answer

Implemented context-provider mode:
- `boris.frame`
- Runtime performs BOIS/SIMA/BORIS framing and core retrieval
- Runtime does not call OpenAI API
- Runtime returns structured context through MCP `structuredContent`
- ChatGPT generates the final answer using the returned frame

Implemented tool:
- `boris.frame`

Deferred Phase 4D.1 tool:
- `boris.validate`

`boris.validate` should validate a ChatGPT-generated answer against a previously
returned BORIS context packet, but it is deferred to Phase 4D.1.

Context packet shape:

```json
{
  "packet_version": "boris-context/1.0",
  "frame_id": "uuid",
  "session_id": "uuid-or-existing-session-id",
  "input": "original effective user input",
  "runtime_mode": "context_provider",
  "llm_called": false,
  "bois_frame": {},
  "sima": {
    "risk": 0.0,
    "uncertainty": 0.0,
    "missing_fields": [],
    "ambiguity_score": 0.0
  },
  "boris_context": {},
  "retrieved_core": [
    {
      "chunk_id": "string",
      "section": "string",
      "title": "string",
      "text": "bounded string",
      "relevance": 0.0
    }
  ],
  "retrieval_metadata": {
    "returned_chunks": 0,
    "total_characters": 0,
    "truncated": false,
    "max_chunks": 6,
    "max_chunk_characters": 3000,
    "max_total_characters": 12000
  },
  "answer_instructions": []
}
```

Implemented acceptance criteria for Phase 4D:

1. Existing `boris.ask` remains unchanged and continues to return
   Runtime-generated answers.
2. New `boris.frame` tool is added.
3. `boris.frame` does not call OpenAI API or any external LLM.
4. `boris.frame` returns MCP `structuredContent` containing the full context
   packet.
5. `boris.frame` returns concise `content` text instructing ChatGPT to use the
   packet as the controlling frame.
6. Runtime metadata explicitly includes `llm_called: false`.
7. Retrieved BOIS Core chunks are bounded to 6 chunks, 3000 characters per
   chunk, and 12000 total returned characters.
8. Secrets, raw prompts, API keys, and internal stack traces are not exposed.
9. ChatGPT can answer using Runtime context without Runtime generating the final
   answer.
10. Tests prove that `boris.frame` does not invoke the LLM adapter.

Architectural constraints:

- Do not replace `boris.ask`.
- Do not make ChatGPT call OpenAI API through Runtime in context-provider mode.
- Do not move BOIS/SIMA/BORIS logic into MCP.
- Do not import Runtime internals into MCP.
- Do not expose `/runtime/ask` publicly.
- Runtime API remains private.
- MCP remains the public adapter boundary.
- Context packet must be explicit, bounded, and model-visible through
  `structuredContent` / `content`.
- `_meta` may be used later for UI-only data, but Phase 4D context needed by
  ChatGPT must not be hidden in `_meta`.

Remaining limitations:

1. ChatGPT may not strictly obey the returned frame unless prompt/tool
   instructions are clear.
2. `boris.validate` remains Phase 4D.1.
3. Frame packet persistence, lookup by `frame_id`, answer submission, packet
   signing, and tamper verification are not implemented.

Local smoke tests:

```bash
curl -s -X POST http://localhost:8000/runtime/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id":"ask-test","input":"Explain BOIS Runtime","mode":"default","context":{"source":"curl"}}'

curl -s -X POST http://localhost:8000/runtime/frame \
  -H "Content-Type: application/json" \
  -d '{"session_id":"frame-test","input":"Explain BOIS Runtime as a context provider","mode":"default","context":{"source":"curl"}}'
```

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
