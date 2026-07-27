# Adapters

Transport adapters are explicit top-level packages rather than a generic
`adapters/` container:

- `api/` — private FastAPI transport for execution, frame diagnostics, and
  answer validation;
- `mcp_server/` — public read-only `boris.execute` tool;
- `cli/` — local frame generation;
- `llm/` — canonical inference port used by Semantic Input compilation,
  semantic calculation, and optional answer validation.

## Dependency direction

```text
CLI -> application
API -> application -> semantic_executor -> LLM port
MCP -> HTTP /runtime/execute -> API
```

The MCP server must not import `application`, `core_surface`,
`runtime_compatibility`, `semantic_executor`, or `llm`. It sends the public
request contract to the private API and receives a `boris-execution/1.0`
candidate envelope.

The MCP tool list is exactly `{"boris.execute"}`. The former public
`boris.frame` tool has no alias. The internal `/runtime/frame` endpoint remains
available for lexical projection diagnostics, and `/runtime/validate` remains a
private stateless answer-validation service.

The public tool has no `operation` or provider discriminator. It accepts only
initial input/context or a signed HOLD resume and always forwards the private
API's canonical `execute` operation. `ServerLLMProvider` performs compilation
and calculation inside Runtime. Public work-order IDs, tokens, semantic
submissions, and host-provider selection are not part of the MCP schema.

The experimental `CHATGPT_HOST_ONLY` `prepare`/`submit` protocol remains
available only through the private HTTP API. It is not an MCP compatibility
path and cannot be selected by a stale public argument.

In developer mode the tool descriptor links one versioned MCP Apps resource.
The adapter moves Runtime `developer_trace` from the HTTP payload into
tool-result `_meta`, while keeping the candidate and handoff in
`structuredContent`. Production mode registers neither the link nor the
resource.

The MCP adapter does not calculate or validate semantic content itself. It
returns the Runtime-owned candidate and concise gate-preserving presentation
instructions.

There is no compatibility `adapters.llm` module. Callers use
`llm.llm_adapter` directly.
