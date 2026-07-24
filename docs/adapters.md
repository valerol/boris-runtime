# Adapters

Transport adapters are explicit top-level packages rather than a generic
`adapters/` container:

- `api/` — private FastAPI transport for frame and validation;
- `mcp_server/` — public read-only `boris.frame` tool;
- `cli/` — local frame generation;
- `llm/` — canonical inference port used by semantic calculation and optional
  semantic answer validation.

## Dependency direction

```text
CLI -> application
API -> application
MCP -> HTTP -> API
Semantic Executor -> LLM port
```

The MCP server must not import `application`, `core_surface`,
`runtime_compatibility`, `semantic_executor`, or `llm`. It receives only the
wire-level context packet from the private API.

There is no compatibility `adapters.llm` module. Callers must use
`llm.llm_adapter` directly.
