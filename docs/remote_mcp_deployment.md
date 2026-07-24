# Remote MCP Deployment

Phase 4C exposes the MCP server as the public adapter boundary while keeping the
BORIS Runtime HTTP API private. Phase 4D adds `boris.frame`, a context-provider
tool that still reaches Runtime only through the private HTTP API.

```text
ChatGPT / Remote MCP client
  -> HTTPS
/mcp
  ->
private MCP server
  ->
Runtime API 127.0.0.1:8000
```

The MCP server is an adapter. It does not contain BOIS/SIMA/BORIS logic, does
not call OpenAI directly, and does not store memory.

The private Runtime process must be configured with a package source:

```bash
BORIS_CORE_PACKAGE=/opt/boris-core
```

The path must identify a package directory or ZIP accepted by Core Surface.

Available public MCP tools:

- `boris.frame`: calls private `/runtime/frame`; Runtime returns only a bounded
  BOIS/SIMA/BORIS context packet in `structuredContent`, includes the full safe
  `runtime_generated_prompt` in text `content`, does not call an LLM, and
  ChatGPT shows the prompt before generating the final answer itself.

Answer validation remains available through the private Runtime API. It is not
registered as a public MCP tool.

## Mode A - Local Development

Terminal 1, private Runtime API:

```bash
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Terminal 2, remote MCP transport:

```bash
BORIS_MCP_TRANSPORT=streamable-http \
BORIS_MCP_HOST=127.0.0.1 \
BORIS_MCP_PORT=9000 \
BORIS_MCP_PATH=/mcp \
BORIS_RUNTIME_API_URL=http://127.0.0.1:8000 \
python -m mcp_server.server
```

Health check:

```bash
curl -s http://127.0.0.1:9000/health
```

## Mode B - Public HTTPS Through Nginx

Keep the Runtime API private:

```text
127.0.0.1:8000
```

Run the MCP server privately:

```text
127.0.0.1:9000
```

Expose only the MCP endpoint publicly:

```text
https://<domain>/mcp
```

Example nginx location:

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:9000/mcp;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    proxy_buffering off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}
```

Do not expose `/runtime/frame` or `/runtime/validate` directly to the public
internet. The public boundary is `/mcp`; the internal boundaries are
`http://127.0.0.1:8000/runtime/frame` and
`http://127.0.0.1:8000/runtime/validate`.

`/runtime/frame` returns packets with `packet_version:
"boris-context/2.0"`, `runtime_mode: "context_provider"`, `llm_called: false`,
and Core Surface projection bounded to 6 chunks, 3000 characters per chunk,
and 12000 total projected-core characters. The operation has no server-side
conversation state.

`/runtime/validate` accepts `answer`, the full `context_packet`, and optional
`validation_mode` (`deterministic`, `semantic`, or `hybrid`; default
`deterministic`). Validation is stateless: Runtime does not persist packets,
look up `frame_id`, enforce TTL, verify HMAC signatures, or claim packet
authenticity. The report uses `validation_version: "boris-validation/1.0"` and
verdicts `PASS`, `REVISE`, `FAIL`, and `INDETERMINATE`. Semantic and hybrid
modes may call the Runtime-configured validator LLM. If needed, set
`BORIS_VALIDATOR_LLM` and `BORIS_VALIDATOR_MODEL`; otherwise validator
configuration falls back to the main LLM settings.

## Mode C - OpenAI Secure MCP Tunnel / Temporary Tunnel

When the MCP server must remain private, use an outbound tunnel rather than
opening inbound ports. This repository does not implement the tunnel client.

```text
ChatGPT / OpenAI
  ->
Secure tunnel endpoint
  ->
outbound tunnel-client
  ->
private MCP server /mcp
  ->
Runtime API 127.0.0.1:8000
```

## ChatGPT Developer Mode Connector Setup

1. Start the Runtime API.
2. Start the MCP server in `streamable-http` mode.
3. Ensure the MCP endpoint is reachable over HTTPS.
4. Use this connector URL:

```text
https://<domain>/mcp
```

Suggested connector name:

```text
BORIS
```

Suggested connector description:

```text
Connects ChatGPT to BORIS. Use boris.frame for LLM-free BOIS/SIMA/BORIS context packets and the full Runtime-generated prompt that ChatGPT shows before answering.
```

After updating tool metadata, refresh connector metadata in ChatGPT.

Use `"mode":"developer"` in a frame request to return `developer_trace`.
Through MCP, developer mode also instructs ChatGPT to display the complete
formatted trace before the Runtime-generated prompt and its own answer. The
trace contains projection scores and decisions, not model chain-of-thought or
server secrets.

Local smoke tests:

```bash
curl -s -X POST http://127.0.0.1:8000/runtime/frame \
  -H "Content-Type: application/json" \
  -d '{"session_id":"frame-test","input":"Explain BOIS Runtime as a context provider","mode":"default","context":{"source":"curl"}}'

curl -s -X POST http://127.0.0.1:8000/runtime/validate \
  -H "Content-Type: application/json" \
  -d '{
    "answer": "The ChatGPT-generated answer",
    "context_packet": {
      "packet_version": "boris-context/2.0",
      "frame_id": "00000000-0000-4000-8000-000000000000",
      "session_id": "validate-test",
      "input": "Explain BOIS Runtime",
      "runtime_mode": "context_provider",
      "llm_called": false,
      "bois_frame": {},
      "sima": {
        "risk": 0.2,
        "uncertainty": 0.2,
        "missing_fields": [],
        "ambiguity_score": 0.1
      },
      "boris_context": {},
      "projected_core": [],
      "projection_metadata": {
        "returned_chunks": 0,
        "total_characters": 0,
        "truncated": false,
        "max_chunks": 6,
        "max_chunk_characters": 3000,
        "max_total_characters": 12000
      },
      "answer_instructions": [],
      "runtime_generated_prompt": "## User input\nExplain BOIS Runtime"
    },
    "validation_mode": "deterministic"
  }'
```
