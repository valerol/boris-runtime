# BOIS / SIMA / BORIS Middleware SDK — FULL EXECUTION ROADMAP v1

## 0. Цель системы
BOIS Middleware SDK — protocol execution layer + deterministic reasoning loop + adapter abstraction layer.

## GLOBAL ARCHITECTURE
User/UI → Middleware → LLM → Tools → Memory

## GLOBAL PRINCIPLES
- BOIS declarative
- SIMA analytical
- BORIS contextual specialization
- Middleware = execution engine only
- Platform = external

---

# PHASE 0 — ARCHITECTURE RESET
- define SDK boundaries
- create repo structure
- lock BOIS as declarative core
- create ARCHITECTURE.md, SDK_SPEC.md

---

# PHASE 1 — CLI MVP (RUNTIME CORE v0.1)
- runtime loop
- protocol parser
- prompt builder
- LLM adapter stub
- CLI execution only
- detect GAP + clarify loop

---

# PHASE 2 — CORE LOADER SYSTEM
- load BOIS from .md/.json/.yaml
- folder-based core support
- GitHub release support
- immutable core per session

---

# PHASE 3 — PROTOCOL ENGINE
- full execution cycle:
  INPUT → SIMA → BOIS → BORIS → LLM → PARSER → LOOP
- gap detection engine
- question memory
- validation layer

---

# PHASE 4 — API LAYER (FASTAPI)
- /chat
- /session
- /reset
- stateless API wrapper over middleware

---

# PHASE 5 — PLATFORM ADAPTERS
- Telegram adapter
- Web adapter
- Open WebUI adapter
- Dify adapter
- LangGraph adapter

---

# PHASE 6 — MEMORY ABSTRACTION LAYER
- interface: load/save/search
- backend agnostic
- SQLite/Postgres/Redis/Chroma/Supabase support

---

# PHASE 7 — TOOL ABSTRACTION LAYER
- search / call_api / run_code / read_file
- tool execution externalized
- middleware does not own tools

---

# PHASE 8 — PACKAGING (SDK)
- pip install bois-runtime
- BORIS(core).chat()

---

# PHASE 9 — REFERENCE INTEGRATIONS
- CLI
- Telegram
- Web API
- Open WebUI
- Dify
- LangGraph
- validate single middleware across all

---

# PHASE 10 — STABLE v1.0
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
