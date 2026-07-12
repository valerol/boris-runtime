# BOIS / SIMA / BORIS Middleware SDK

## Documentation

- Vision -> [docs/vision.md](docs/vision.md)
- Architecture -> [docs/architecture.md](docs/architecture.md)
- Protocol -> [docs/protocol.md](docs/protocol.md)
- Protocol Engine -> [docs/PROTOCOL_ENGINE.md](docs/PROTOCOL_ENGINE.md)
- Runtime Session -> [docs/RUNTIME_SESSION.md](docs/RUNTIME_SESSION.md)
- SDK API -> [docs/sdk_api.md](docs/sdk_api.md)
- Adapters -> [docs/adapters.md](docs/adapters.md)
- Remote MCP Deployment -> [docs/remote_mcp_deployment.md](docs/remote_mcp_deployment.md)
- Roadmap -> [docs/roadmap.md](docs/roadmap.md)
- Archive -> [docs/archive.md](docs/archive.md)
- Changelog -> [CHANGELOG.md](CHANGELOG.md)

This repository has been reset from a runtime/platform MVP into a lightweight
protocol middleware SDK.

The project is not an AI platform and not a full runtime system. It enforces
BOIS / SIMA / BORIS protocol definitions on top of existing LLM platforms.

## Current Structure

```text
core/          declarative protocol definitions and loader
runtime/       minimal stateless protocol execution
protocol/      BOIS, SIMA, and BORIS protocol layers
prompt/        deterministic prompt construction
llm/           Phase 1 LLM adapter interface
adapters/      LLM, memory, tool, and platform boundaries
cli/           validation CLI
api/           optional API boundary
mcp_server/    MCP adapter over the Runtime HTTP API
examples/      usage examples
docs/          current documentation set
archive/       v0 runtime artifacts
```

## Run CLI

```bash
python cli/main.py
```

## Runtime HTTP API

Install dependencies and run the FastAPI transport adapter:

```bash
python -m pip install -r requirements.txt
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

Smoke test:

```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/runtime/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","input":"Explain BOIS Runtime v0","mode":"default","context":{"source":"curl"}}'

curl -s -X POST http://localhost:8000/runtime/frame \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "frame-test",
    "input": "Explain BOIS Runtime as a context provider",
    "mode": "default",
    "context": {
      "source": "curl"
    }
  }'

curl -s -X POST http://localhost:8000/runtime/validate \
  -H "Content-Type: application/json" \
  -d '{
    "answer": "The ChatGPT-generated answer",
    "context_packet": {
      "packet_version": "boris-context/1.0",
      "frame_id": "00000000-0000-4000-8000-000000000000",
      "session_id": "validate-test",
      "input": "Explain BOIS Runtime",
      "runtime_mode": "context_provider",
      "llm_called": false,
      "bois_frame": {},
      "sima": {
        "risk": 0.2,
        "uncertainty": 0.2,
        "missing_fields": [],
        "ambiguity_score": 0.1
      },
      "boris_context": {},
      "retrieved_core": [],
      "retrieval_metadata": {
        "returned_chunks": 0,
        "total_characters": 0,
        "truncated": false,
        "max_chunks": 6,
        "max_chunk_characters": 3000,
        "max_total_characters": 12000
      },
      "answer_instructions": []
    },
    "validation_mode": "deterministic"
  }'

curl -s http://localhost:8000/runtime/session/test

curl -s -X POST http://localhost:8000/runtime/reset \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test"}'
```

`POST /runtime/ask` returns the protocol output shape plus the resolved
`session_id`. Runtime generates the final answer through its configured LLM
adapter.

`POST /runtime/frame` returns a bounded BOIS/SIMA/BORIS context packet only.
Runtime does not generate a final answer, does not call an external LLM, and
does not advance protocol conversation state. The packet uses
`packet_version: "boris-context/1.0"`, `runtime_mode: "context_provider"`, and
`llm_called: false`. Retrieved BOIS Core chunks are limited to 6 chunks, 3000
characters per chunk, and 12000 total returned characters.

`POST /runtime/validate` validates a ChatGPT-generated answer against the full
context packet returned by `/runtime/frame`. It is stateless: Runtime does not
persist packets, look up `frame_id`, bind packets to sessions, enforce TTL,
verify signatures, or claim that the supplied packet is authentic or unchanged.
The supplied `frame_id` is report correlation only. Validation does not rewrite
the answer and does not mutate protocol conversation state.

Validation modes are `deterministic`, `semantic`, and `hybrid`; the default is
`deterministic`. Every mode runs packet preflight first and returns the unified
`boris-validation/1.0` layered report with `preflight`, `deterministic`, and
`semantic` sections. Verdicts are `PASS`, `REVISE`, `FAIL`, and
`INDETERMINATE`. Request-shape errors return HTTP 422. Readable but invalid
packets return HTTP 200 with verdict `FAIL`. In pure semantic mode, unavailable
validator configuration returns HTTP 503 `llm_unavailable`, and invalid
validator output returns HTTP 502 `semantic_validation_error`. Hybrid mode
preserves deterministic results and returns HTTP 200 `INDETERMINATE` when
semantic escalation is unavailable or invalid.

Optional validator-specific configuration:

```env
BORIS_VALIDATOR_LLM=openai
BORIS_VALIDATOR_MODEL=gpt-4o-mini
```

When these are absent, semantic validation falls back to the main
`BOIS_LLM`/`OPENAI_MODEL` settings and existing credentials such as
`OPENAI_API_KEY`.

Runtime/session failures return a controlled JSON error:

```json
{"error":"runtime_error","detail":"...","session_id":"test"}
```

`POST /runtime/reset` removes one in-memory runtime session. It returns
`reset: true` when a session existed and was removed, and `reset: false` when
the session was already absent.

`context` is accepted by `/runtime/ask` and `/runtime/frame` as transport
metadata. It is not injected into prompt construction or framing, and it cannot
bypass BOIS/SIMA/BORIS protocol logic.

The CLI and HTTP API load `.env` from the repository root automatically. Use
`BOIS_LLM=openai` and `OPENAI_API_KEY=...` in `.env` to use the OpenAI adapter;
otherwise it falls back to the deterministic mock adapter. It has no UI,
database, vector store, Telegram, or Open WebUI dependency.

For prompt visibility during development, set `BORIS_RUNTIME_MODE=dev` or
`BOIS_DEBUG_PROMPT=true` in `.env`. In dev mode, the adapter prints the final
prompt payload immediately before the LLM adapter call.

## MCP Server Adapter

The public MCP adapter is named `BORIS` and exposes one ChatGPT-visible tool:

```text
boris.frame
```

`boris.frame`: Runtime returns a bounded BOIS/SIMA/BORIS context packet without
calling an LLM. The MCP client model, such as ChatGPT, receives the complete
context packet in `structuredContent` and the full `runtime_generated_prompt`
in text `content`; ChatGPT should show that prompt to the user and then generate
the final answer itself.

The internal `boris.ask` and `boris.validate` functions, Runtime client methods,
and private HTTP endpoints remain available to the project, but they are not
registered as public MCP tools.

MCP results use native MCP `CallToolResult` objects. Complete context packets
and structured error details are carried in MCP `structuredContent`. The
`content` field for `boris.frame` contains explicit instructions plus the full
safe Runtime-generated prompt. The MCP adapter does not JSON-wrap its own result
envelope inside a text content block. Error results set `isError: true`.

Recommended ChatGPT workflow:

```text
boris.frame
-> ChatGPT shows runtime_generated_prompt
-> ChatGPT generates answer
```

Run locally with the Runtime HTTP API in one terminal:

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

Then start the MCP adapter in another terminal:

```bash
BORIS_RUNTIME_API_URL=http://127.0.0.1:8000 python -m mcp_server.server
```

Tool payload:

```json
{
  "input": "Explain BOIS Runtime",
  "session_id": "test",
  "mode": "default",
  "context": {
    "source": "mcp"
  }
}
```

Architecture:

```text
public MCP boris.frame
  -> HTTP
POST /runtime/frame
  ->
BOISRuntime.frame(...)
  ->
bounded context packet in structuredContent
  ->
runtime_generated_prompt in content
```

The MCP server is an adapter only. It does not contain BOIS/SIMA/BORIS logic,
does not call OpenAI directly, does not store memory, does not replace Runtime,
and communicates with Runtime only through the stabilized HTTP API.

## Remote MCP / ChatGPT Apps

For remote MCP clients and ChatGPT developer-mode connectors, run the Runtime API
privately and expose only the MCP endpoint over HTTPS.

```bash
# Terminal 1: private Runtime API
uvicorn api.app:app --host 127.0.0.1 --port 8000

# Terminal 2: remote MCP adapter
BORIS_MCP_TRANSPORT=streamable-http \
BORIS_MCP_HOST=127.0.0.1 \
BORIS_MCP_PORT=9000 \
BORIS_MCP_PATH=/mcp \
BORIS_RUNTIME_API_URL=http://127.0.0.1:8000 \
python -m mcp_server.server
```

For ChatGPT developer-mode connectors, expose only the MCP endpoint over HTTPS,
for example `https://<domain>/mcp`. Keep the Runtime API private.

Deployment details: [docs/remote_mcp_deployment.md](docs/remote_mcp_deployment.md)

## Local BOIS Core Retriever

`boris-runtime` does not own BOIS Core. The operator must provide the external
canonical machine-readable core file at:

```text
/opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Build the local semantic index:

```bash
cd /opt/boris-runtime
source .venv/bin/activate

python -m core_retriever.build_index \
  --core /opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json \
  --out /opt/boris-runtime/data/core_index
```

Runtime `.env` settings:

```env
BORIS_CORE_PATH=/opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json
BORIS_CORE_INDEX_DIR=/opt/boris-runtime/data/core_index
BORIS_CORE_RETRIEVER_ENABLED=true
BORIS_CORE_RETRIEVER_TOP_K=12
BORIS_CORE_RETRIEVER_MIN_SCORE=0.0
BORIS_CORE_RETRIEVER_MAX_CHARS=12000
HF_HOME=/opt/boris-runtime/.cache/huggingface
```

Optional settings:

```env
BORIS_CORE_RETRIEVER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
BORIS_CORE_RETRIEVER_AUTO_BUILD=false
```

In development mode, missing index files fail clearly. In non-dev mode, the CLI
continues without `RETRIEVED_ACTIVE_CORE` if the index is not available.
Set `BORIS_CORE_RETRIEVER_ENABLED=false` to disable retrieval explicitly.

## Architecture

Read [docs/architecture.md](docs/architecture.md) for the current SDK
architecture.
