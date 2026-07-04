# Adapters

Adapters define boundaries to external capabilities. They are not full platform
implementations.

## LLMAdapter

Location: `adapters/llm.py`

Base interface for LLM completions. Implementations provide:

```python
complete(prompt, context=None)
```

## MockLLMAdapter

Location: `adapters/llm.py`

Deterministic local adapter for CLI validation and smoke tests. It does not call
an external model.

## OpenAIChatAdapter

Location: `adapters/llm.py`

Optional adapter for OpenAI chat completions. It is loaded only when used and
depends on `OPENAI_API_KEY` and optional `OPENAI_MODEL`.

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

