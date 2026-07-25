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

There is no compatibility `adapters.llm` module. Callers use
`llm.llm_adapter` directly.
