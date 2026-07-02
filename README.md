# BORIS Runtime v0

BORIS Runtime v0 is a minimal Python MVP for a schema-driven reasoning runtime. It keeps the kernel UI-agnostic, uses adapters only for input/output normalization, and isolates the OpenAI integration inside `kernel/llm.py`.

## Architecture

```text
kernel/      BOIS, SIMA, memory, gap detection, LLM, and kernel wiring
runtime/     Schema-driven execution engine
core/        Runtime schema and loader
adapters/    CLI, web, and Telegram input/output adapters
server.py    FastAPI entry point
main_cli.py  Interactive CLI entry point
```

The runtime flow is defined in `core/schema.json` and executed by `runtime/engine.py`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env` if you want live OpenAI responses:

```bash
OPENAI_API_KEY=your_key_here
```

If `OPENAI_API_KEY` is missing, BORIS returns a deterministic local stub response and keeps running.

## Run CLI

```bash
python main_cli.py
```

Use `exit` or `quit` to stop.

Expected shape:

```text
QUESTION: Explain BOIS Runtime v0
ANSWER: LOCAL_STUB_RESPONSE: OpenAI API key is not configured. Received input: Explain BOIS Runtime v0
```

## Run Server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Event example:

```bash
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","input":"Explain BOIS Runtime v0","meta":{"source":"web"}}'
```

Expected response shape:

```json
{
  "type": "ANSWER",
  "content": "LOCAL_STUB_RESPONSE: OpenAI API key is not configured. Received input: Explain BOIS Runtime v0",
  "state": "RETURN",
  "trace_id": "generated-uuid",
  "meta": {
    "requires_user_input": false
  }
}
```

## Tests

```bash
python -m compileall .
pytest
```

## Current MVP Limitations

- Tool routing and action execution are stubs.
- Telegram support is only an adapter stub and has no bot dependency.
- Memory uses a local SQLite database file by default.
- Live OpenAI behavior depends on a valid `OPENAI_API_KEY`; without it, the local stub is expected.
