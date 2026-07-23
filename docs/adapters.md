# Adapters

Adapters define boundaries to external capabilities. They are not full platform
implementations.

## LLMAdapter

Location: `llm/llm_adapter.py`

Base interface for the canonical Runtime LLM port. Implementations provide:

```python
call(prompt: str) -> str
call_structured(prompt: str, system_message: str) -> str
```

Structured calls must preserve the separate system contract and request JSON
output. They do not silently fall back to a plain call.

## MockLLMAdapter

Location: `llm/llm_adapter.py`

Deterministic local adapter for CLI validation and smoke tests. It does not call
an external model.

## OpenAIAdapter

Location: `llm/llm_adapter.py`

Optional adapter for OpenAI chat completions. It is loaded only when used and
depends on `OPENAI_API_KEY` and optional `OPENAI_MODEL`.

## Legacy Adapter Boundary Examples

`adapters/llm.py` retains compatibility names backed by the canonical
`llm/llm_adapter.py` implementation. It is not a second LLM architecture.
The remaining `adapters/` modules are lightweight boundary examples for memory,
tool, and platform integration, not platform implementations.

## MemoryAdapter

Location: `adapters/memory.py`

Boundary for external memory. The SDK does not provide built-in persistence.
Implementations provide:

```python
read(context)
write(event)
```

## ToolAdapter

Location: `adapters/tools.py`

Boundary for external tool execution. Tool execution belongs to the host
platform, not the middleware runtime.

## EchoToolAdapter

Location: `adapters/tools.py`

Minimal local example adapter for the `echo` tool.

## PlatformAdapter

Location: `adapters/platform.py`

Boundary for host platform transport and formatting. UI, auth, storage, tools,
and memory remain external responsibilities.

## Future Integrations

Open WebUI, Telegram, Dify, and LangGraph are future integration targets. They
should not become core dependencies of `core/`, `runtime/`, or the active SDK
execution path.
