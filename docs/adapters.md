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

The standard `execute` operation accepts either initial input or a signed HOLD
resume through the same `boris.execute` tool. In developer mode the tool
descriptor links one
versioned MCP Apps resource. The adapter moves Runtime `developer_trace` from
the HTTP payload into tool-result `_meta`, while keeping the candidate and
handoff in `structuredContent`. Production mode registers neither the link nor
the resource.

The same tool also exposes an optional `operation` discriminator:

- omitted or `execute` uses the configured API calculator;
- `prepare` returns a signed `CHATGPT_HOST` SemanticWorkOrder for either an
  initial input or signed HOLD resume;
- `submit` forwards exactly one work-order ID, token, and semantic result to
  the private API.

The MCP adapter does not calculate or validate the work order itself. It keeps
the large semantic prompt in `structuredContent` and returns only a concise
model instruction in text, avoiding a second full prompt copy.

There is no compatibility `adapters.llm` module. Callers use
`llm.llm_adapter` directly.
