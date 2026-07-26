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
  -> HOLD handoff / signed stateless continuation
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

The repository tracks non-secret Runtime and MCP settings in `.env`. Secret
variables are present there only as empty placeholders. Put real secret values
in the ignored `.env.local` file:

```bash
OPENAI_API_KEY=...
BORIS_CONTINUATION_SECRET=...
```

`BORIS_CONTINUATION_SECRET` must contain at least 32 bytes. It signs stateless
HOLD continuation tokens and is used only by the private Runtime service.
`BORIS_CONTINUATION_TTL_SECONDS` defaults to 3600 and may be set from 60 through
86400 seconds.

Runtime entry points load `.env` first and `.env.local` second. Values already
present in the process environment have the highest priority; `.env.local`
overrides tracked `.env` values otherwise.

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
calculator, and optional semantic answer validation. Non-secret provider
selection and model settings belong in tracked `.env`:

```bash
BOIS_LLM=openai
OPENAI_MODEL=gpt-4o
BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS=
```

For a Core contract that declares phase context budgets, set
`BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS` to the actual context capacity of the
configured semantic model. Core v2.31 requires at least `524288`. Runtime
fails closed when the declaration is absent or insufficient; it does not
silently narrow the phase-complete norm set.

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
    "context": {}
  }'
```

The response uses `execution_version: "boris-execution/1.0"` and
`status: "semantic_candidate"`. It includes the constrained gate, candidate
result, norm results, unknowns, conflicts, alternatives, and explicit
limitations. `HOLD`, `STOP`, and `REPAIR` are normal HTTP 200 Runtime results.
Every `HOLD` includes a `boris-hold-handoff/1.1` handoff. It separates
path-aware `semantic_unknowns` from Core-declared `predicate_inputs` instead
of implying that a human-readable unknown and a formal selector are the same
field. Resume the same semantic route without resending the original input:

```bash
curl -s -X POST http://127.0.0.1:8000/runtime/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "execution-test",
    "resume": {
      "continuation_token": "v1...",
      "operator_input": {
        "statement": "I confirm the supplied authorization value.",
        "values": {"authorization.granted": true},
        "resolved_unknowns": []
      }
    }
  }'
```

The token binds the exact `SemanticInput`, Core identity, session, HOLD targets,
and expiry. Resume skips the Semantic Input compiler, applies only signed
operator-input paths, and recalculates the same non-mutating semantic route. A
plain-text `operator_input` is accepted only when it closes all targetless
semantic unknowns and no typed path remains. Runtime returns
`incomplete_operator_resolution` without recalculation when any signed target
is missing. Empty
`candidate_result: {}` is never exposed: `HOLD` uses `null` plus
`candidate_unavailable_reason`; other gates require a non-empty candidate.
If a semantic calculator nevertheless returns an empty object for a route
whose constrained gate is `PASS`, `STOP`, or `REPAIR`, Semantic Executor
materializes `boris-candidate-projection/1.0` from the already validated
calculation. The projection is marked in `validation_issues` and adds no
semantic conclusion beyond the validated norm results and constrained gate.
Invalid Core source binding, invalid compiled input, and provider failures
return controlled fail-closed errors. An archive source with missing or
mismatched server acceptance also fails closed.

Set `BORIS_RUNTIME_MODE=dev` in the server `.env` to add the safe combined
lexical and semantic trace:
compiled `SemanticInput`, Core reference, RuntimeAttestation, selected norms,
formal predicates, suggested and constrained gates, validation issues, stage
ledger, and timings. Any other or absent value returns the compact envelope.
The request cannot enable or disable server observability.

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

When `BORIS_RUNTIME_MODE=dev`, `boris.execute` is linked to
`ui://boris/developer-surface-v2.html`. The MCP Apps component displays the
phase, constrained gate, candidate, path-aware HOLD form, and complete safe
trace. The trace is delivered only through tool-result `_meta`; it is absent from
model-visible `content` and `structuredContent`. The component resumes a HOLD
by calling the same `boris.execute` tool. Production mode publishes no
Developer Surface resource. No public `boris.frame` alias is registered.

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
