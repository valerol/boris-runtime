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

Available MCP tools:

- `boris.ask`: calls private `/runtime/ask`; Runtime generates the final answer
  through its configured LLM adapter.
- `boris.frame`: calls private `/runtime/frame`; Runtime returns only a bounded
  BOIS/SIMA/BORIS context packet in `structuredContent`, does not call an LLM,
  and ChatGPT generates the final answer itself.

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

Do not expose `/runtime/ask` or `/runtime/frame` directly to the public
internet. The public boundary is `/mcp`; the internal execution boundaries are
`http://127.0.0.1:8000/runtime/ask` and
`http://127.0.0.1:8000/runtime/frame`.

`/runtime/frame` returns packets with `packet_version:
"boris-context/1.0"`, `runtime_mode: "context_provider"`, `llm_called: false`,
and retrieval bounded to 6 chunks, 3000 characters per chunk, and 12000 total
retrieved-core characters. The operation is non-mutating with respect to
protocol conversation state.

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
BORIS Runtime
```

Suggested connector description:

```text
Connects ChatGPT to BORIS Runtime. Use boris.ask for Runtime-generated answers and boris.frame for LLM-free BOIS/SIMA/BORIS context packets that ChatGPT answers from.
```

After updating tool metadata, refresh connector metadata in ChatGPT.

Local smoke tests:

```bash
curl -s -X POST http://127.0.0.1:8000/runtime/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id":"ask-test","input":"Explain BOIS Runtime","mode":"default","context":{"source":"curl"}}'

curl -s -X POST http://127.0.0.1:8000/runtime/frame \
  -H "Content-Type: application/json" \
  -d '{"session_id":"frame-test","input":"Explain BOIS Runtime as a context provider","mode":"default","context":{"source":"curl"}}'
```
