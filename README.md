# BORIS Runtime

BORIS Runtime is an experimental BOIS/SIMA/BORIS orchestration substrate. The
repository currently implements a verified passive Core Surface, compatibility
attestation, an isolated Semantic Executor, a stateless ChatGPT context
provider, and transport adapters.

It does not yet implement Independent Review, Policy Kernel state admission,
external actions, domain physiology, or long-term memory.

## Active architecture

```text
Core release package
  -> core_surface
  -> runtime_compatibility
  -> semantic_executor
  -> ExecutionCandidate

Core release package
  -> core_surface
  -> application.context_provider
  -> private HTTP /runtime/frame
  -> public MCP boris.frame
  -> ChatGPT
```

The two paths share the same verified `CoreSurface`. The context-provider path
projects bounded canonical records but does not perform semantic applicability
routing, call an LLM, mutate state, or claim package activation.

## Repository layout

```text
application/            context projection, stateless frame, answer validation
api/                    private FastAPI adapter
cli/                    local context-frame adapter
core_surface/           package loading, integrity, immutable canonical data
llm/                    canonical LLM port and configuration
mcp_server/             public boris.frame adapter
runtime_compatibility/  substrate checks and RuntimeAttestation
semantic_executor/      isolated semantic calculation
tests/                  active regression suite
docs/                   current architecture and contracts
```

The former `core/`, `core_retriever/`, `runtime/`, `protocol/`, `prompt/`,
`adapters/`, and `archive/` trees were removed. They represented earlier
middleware generations and are not compatibility paths.

## Configuration

Copy `.env.example` to `.env` and set:

```bash
BORIS_CORE_PACKAGE=/opt/boris-core
```

The value must identify a Core release-package directory or ZIP accepted by
`core_surface.load_core_surface`. A legacy machine JSON file is not a valid
source.

LLM settings are needed only for the Semantic Executor or semantic validation:

```bash
BOIS_LLM=openai
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

## Private Runtime API

Run:

```bash
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Available endpoints:

- `GET /health`
- `POST /runtime/frame`
- `POST /runtime/validate`

Create a context packet:

```bash
curl -s -X POST http://127.0.0.1:8000/runtime/frame \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "frame-test",
    "input": "Explain the applicable BOIS constraints",
    "mode": "default",
    "context": {}
  }'
```

`/runtime/frame` is stateless. `session_id` is correlation data, not a stored
conversation. The response uses `packet_version: "boris-context/2.0"` and
contains a bounded Core Surface projection plus a safe
`runtime_generated_prompt`.

Set `mode` to `developer` to add a safe `developer_trace` containing package
metadata, projection candidates, selected and excluded norms, lexical scores
and match terms, limits, stage timings, warnings, and the actual Runtime
capabilities invoked. `default` and `production` omit this trace.

`/runtime/validate` checks a ChatGPT-generated answer against a supplied context
packet. Deterministic, semantic, and hybrid modes remain available. Validation
does not create a Runtime session or claim packet authenticity.

## Public MCP adapter

Run:

```bash
BORIS_MCP_TRANSPORT=streamable-http \
BORIS_MCP_HOST=127.0.0.1 \
BORIS_MCP_PORT=9000 \
BORIS_MCP_PATH=/mcp \
BORIS_RUNTIME_API_URL=http://127.0.0.1:8000 \
python -m mcp_server.server
```

The MCP server exposes one public read-only tool: `boris.frame`. It communicates
with the private API over HTTP and does not import Runtime internals, load Core
packages, call LLMs, or store memory.

For an observable developer response, call `boris.frame` with
`mode: "developer"`. The MCP result instructs ChatGPT to display the complete
safe `developer_trace` before the Runtime-generated prompt and final answer.

## Core Surface and Semantic Executor

Validate a package:

```bash
python -m core_surface /path/to/core-package.zip
```

Run an isolated semantic calculation:

```bash
python -m semantic_executor \
  /path/to/core-package.zip \
  /path/to/semantic-input.json \
  --operator-acceptance /path/to/operator-acceptance.json
```

Without accepted compatibility attestation, semantic calculation remains
fail-closed.

## Tests

```bash
python -m pytest -q
python -m compileall -q \
  application api cli core_surface llm mcp_server \
  runtime_compatibility semantic_executor
git diff --check
```

See [architecture.md](docs/architecture.md),
[core_surface.md](docs/core_surface.md),
[runtime_compatibility.md](docs/runtime_compatibility.md), and
[semantic_executor.md](docs/semantic_executor.md).
