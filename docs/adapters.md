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

The public tool has no `operation` discriminator. Initial input or a signed
HOLD resume is always forwarded to the private API as `prepare`. A request
containing one exact work-order ID, token, and stage-specific `semantic_input`
or `semantic_result` is always forwarded as `submit`. The MCP adapter cannot
select the private legacy `execute` operation or the configured API
calculator.

A Runtime-issued correction remains a `CALCULATION` work order with
`gate=HOLD`, the phase output contract, and structured issues. The adapter
forwards its one corrected submission exactly like the initial calculation.
It does not create retries; an ensuing `HOLD` ends the automatic route. This
transport correction is not canonical `REPAIR`.

In developer mode the tool descriptor links one versioned MCP Apps resource.
The adapter moves Runtime `developer_trace` from the HTTP payload into
tool-result `_meta`, while keeping the candidate and handoff in
`structuredContent`. Production mode registers neither the link nor the
resource.

The MCP adapter does not calculate or validate the work order itself. It keeps
the large semantic prompt in `structuredContent` and returns only a concise
model instruction in text, avoiding a second full prompt copy.

There is no compatibility `adapters.llm` module. Callers use
`llm.llm_adapter` directly.
