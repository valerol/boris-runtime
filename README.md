# BORIS Runtime

BORIS Runtime is an experimental BOIS/SIMA/BORIS orchestration substrate. The
repository currently implements a verified passive Core Surface, compatibility
attestation, a strict Semantic Input compiler, an application-level execution
service, a non-mutating Semantic Executor, an internal diagnostic context
provider, and transport adapters.

It does not yet implement Independent Review, Policy Kernel state admission,
external actions, domain physiology, or long-term memory.

## Active architecture

```text
Core release package
  -> core_surface
  -> runtime_compatibility
  -> application.execution.SemanticInputCompiler
  -> semantic_executor
  -> ExecutionCandidate
  -> private HTTP /runtime/execute
  -> public MCP boris.execute

Core release package
  -> core_surface
  -> application.context_provider
  -> private HTTP /runtime/frame
  -> internal diagnostics
```

Both paths share the same verified `CoreSurface`. The public execution path
returns `status: "semantic_candidate"`; it does not claim Independent Review,
Policy Kernel admission, state mutation, or external action. The frame path
remains read-only lexical observability and does not determine semantic
applicability.

## Repository layout

```text
application/            execution service, compiler, projection, validation
api/                    private FastAPI adapter
cli/                    local context-frame adapter
core_surface/           package loading, integrity, immutable canonical data
llm/                    canonical LLM port and configuration
mcp_server/             public boris.execute adapter
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

At the current deployment stage, `BORIS_CORE_PACKAGE` identifies the checked-out
`boris-core` repository. Runtime verifies the directory through its manifest,
content-set hash, and component hashes. Selecting that server-owned directory
authorizes only `semantic_evaluation`; no exact Core ZIP or separate
`operator-acceptance.json` is required. Acceptance is never read from an MCP
request. Archive sources remain supported for isolated compatibility work and
still require an explicit server-owned acceptance record. A legacy machine JSON
file is not a valid source.

When several Core releases are available, configure the highest version as the
current package. Older releases are used only for an explicit compatibility
test.

LLM settings are used by the Semantic Input compiler, Semantic Executor
calculator, and optional semantic answer validation:

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
- `POST /runtime/execute`
- `POST /runtime/frame`
- `POST /runtime/validate`

Create a semantic candidate:

```bash
curl -s -X POST http://127.0.0.1:8000/runtime/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "execution-test",
    "input": "Explain the applicable BOIS constraints",
    "mode": "production",
    "context": {}
  }'
```

The response uses `execution_version: "boris-execution/1.0"` and
`status: "semantic_candidate"`. It includes the constrained gate, candidate
result, norm results, unknowns, conflicts, alternatives, and explicit
limitations. `HOLD`, `STOP`, and `REPAIR` are normal HTTP 200 Runtime results.
Invalid Core source binding, invalid compiled input, and provider failures
return controlled fail-closed errors. An archive source with missing or
mismatched server acceptance also fails closed.

Set `mode` to `developer` to add the safe combined lexical and semantic trace:
compiled `SemanticInput`, Core reference, RuntimeAttestation, selected norms,
formal predicates, suggested and constrained gates, validation issues, stage
ledger, and timings. `default` and `production` follow the same execution route
without this trace.

`/runtime/frame` is stateless. `session_id` is correlation data, not a stored
conversation. The response uses `packet_version: "boris-context/2.0"` and
contains a bounded Core Surface projection plus a safe
`runtime_generated_prompt`. It remains available for internal diagnostics and
is not a public MCP tool.

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

The MCP server exposes one public read-only tool: `boris.execute`. It communicates
with the private API over HTTP and does not import Runtime internals, load Core
packages, call LLMs, or store memory.

For an observable response, call `boris.execute` with `mode: "developer"`.
ChatGPT must present the complete safe trace first and then the Runtime
candidate. It must not replace the candidate with an independently generated
answer or weaken its gate. No public `boris.frame` alias is registered.

## Core Surface and Semantic Executor

Validate a package:

```bash
python -m core_surface /opt/boris-core
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
BORIS_CURRENT_CORE_PATH=/path/to/boris-core \
  python -m pytest -q tests/test_current_core_integration.py
python -m compileall -q \
  application api cli core_surface llm mcp_server \
  runtime_compatibility semantic_executor
git diff --check
```

See [architecture.md](docs/architecture.md),
[core_surface.md](docs/core_surface.md),
[runtime_compatibility.md](docs/runtime_compatibility.md), and
[semantic_executor.md](docs/semantic_executor.md).
