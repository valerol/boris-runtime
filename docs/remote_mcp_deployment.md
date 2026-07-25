# Remote MCP Deployment

The MCP server is the public adapter boundary while the BORIS Runtime HTTP API
remains private. The sole public tool is `boris.execute`; it reaches the
application execution service only through the private HTTP API.

```text
ChatGPT / Remote MCP client
  -> HTTPS
/mcp
  ->
private MCP server
  ->
Runtime API 127.0.0.1:8000
```

The MCP server is an adapter. It does not contain BOIS/SIMA/BORIS logic, import
the Semantic Executor, call OpenAI directly, or store memory.

The repository tracks non-secret deployment settings in `.env`, including the
private Runtime package source:

```bash
BORIS_CORE_PACKAGE=/opt/boris-core
BOIS_LLM=openai
OPENAI_MODEL=gpt-4o
```

Tracked `.env` also declares `OPENAI_API_KEY=` as an empty secret placeholder.
Store the real value only in ignored `.env.local`:

```bash
OPENAI_API_KEY=...
```

Runtime entry points load `.env` followed by `.env.local`. Existing process
variables remain authoritative; otherwise `.env.local` overrides tracked
settings. MCP loads only non-secret `.env` because the public adapter does not
call OpenAI and does not need access to the API key. On systemd deployments,
configure the files accordingly:

```ini
# boris-runtime.service
EnvironmentFile=-/opt/boris-runtime/.env
EnvironmentFile=-/opt/boris-runtime/.env.local

# boris-mcp.service
EnvironmentFile=-/opt/boris-runtime/.env
```

Restrict the secret file to the service account, for example with mode `0600`.

`/opt/boris-core` is the server-owned checkout used by Runtime at the current
project stage. Runtime binds this directory to its manifest, reproducible
content-set hash, and verified component hashes. The configured repository
selection authorizes only the `semantic_evaluation` scope required by this
route. Do not package the checkout into an exact ZIP and do not create a
deployment-side `operator-acceptance.json`.

Exact ZIP plus explicit `OperatorAcceptance` remains an optional archive
compatibility path; it is not the production deployment protocol.

Available public MCP tools:

- `boris.execute`: calls private `/runtime/execute`; Runtime verifies
  compatibility, compiles a strict `SemanticInput`, invokes the existing
  Semantic Executor, and returns a non-mutating `ExecutionCandidate`.

There is no public `boris.frame` alias. Frame diagnostics and answer validation
remain available through the private Runtime API and are not registered as
public MCP tools.

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

Do not expose `/runtime/execute`, `/runtime/frame`, or `/runtime/validate`
directly to the public internet. The public boundary is `/mcp`; all Runtime API
routes remain on the private interface.

`/runtime/execute` returns `boris-execution/1.0` with
`status: "semantic_candidate"`. `PASS`, `HOLD`, `STOP`, and `REPAIR` are normal
HTTP 200 Runtime results. Core-source compatibility rejection, invalid
compiler output, and LLM failures use controlled error envelopes. Archive mode
also reports missing or mismatched explicit acceptance through a controlled
error.
Production output omits diagnostic trace data.

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
Connects ChatGPT to BORIS. Use boris.execute for the Runtime semantic route. Present its ExecutionCandidate without replacing it with an independent answer or weakening HOLD, STOP, or REPAIR.
```

After updating tool metadata, refresh connector metadata in ChatGPT.

Use `"mode":"developer"` in an execution request to return
`boris-execution-trace/1.0`. Through MCP, ChatGPT presents the complete safe
trace before the candidate. The trace combines lexical projection,
`SemanticInput`, RuntimeAttestation, norm and predicate results, constrained
gate, validation issues, stage ledger, and timings. It contains no hidden
prompts, chain-of-thought, server secrets, or absolute server paths.

Local smoke tests:

```bash
curl -s -X POST http://127.0.0.1:8000/runtime/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "execute-test",
    "input": "Explain the applicable BOIS constraints",
    "mode": "developer",
    "context": {}
  }'

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
