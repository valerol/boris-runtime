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
OPENAI_MODEL=gpt-5.6-terra
OPENAI_REASONING_EFFORT=medium
BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS=1050000
```

Tracked `.env` also declares `OPENAI_API_KEY=` and
`BORIS_CONTINUATION_SECRET=` as empty secret placeholders. Store the real
values only in ignored `.env.local`:

```bash
OPENAI_API_KEY=...
BORIS_CONTINUATION_SECRET=...
```

Generate at least 32 random bytes, for example:

```bash
openssl rand -hex 32
```

Assign the output to `BORIS_CONTINUATION_SECRET`. Runtime uses it to sign and
verify stateless HOLD continuation tokens. Keep
`BORIS_CONTINUATION_TTL_SECONDS=3600` from tracked `.env` unless a shorter
operator-response window is desired. The accepted range is 60 through 86400
seconds. Changing the secret invalidates every unexpired continuation token.

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

Public Core v2 releases declare per-phase context requirements. Configure the
Runtime service with the actual semantic model capacity:

```ini
OPENAI_MODEL=gpt-5.6-terra
OPENAI_REASONING_EFFORT=medium
BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS=1050000
```

Core v2.31 requires at least 524,288 tokens. GPT-5.6 Terra supports a
1,050,000-token context window and structured outputs, while balancing
semantic quality and cost. The capacity variable is an operator assertion,
not a request to the provider. Runtime compatibility stays at `HOLD` when the
value is missing or lower than the Core requirement. Keep all three settings
aligned when overriding the deployment defaults.

`/opt/boris-core` is the server-owned checkout used by Runtime at the current
project stage. Runtime binds this directory to its manifest, reproducible
content-set hash, and verified component hashes. The configured repository
selection authorizes only the `semantic_evaluation` scope required by this
route. Do not package the checkout into an exact ZIP and do not create a
deployment-side `operator-acceptance.json`.

For public-v2 packages, Runtime treats manifest path spelling as canonical and
normalizes only unambiguous case-only differences in the directory or archive
transport. Case collisions, missing or additional paths, size differences,
and checksum differences still fail closed.

Exact ZIP plus explicit `OperatorAcceptance` remains an optional archive
compatibility path; it is not the production deployment protocol.

Updating files below `/opt/boris-core` does not hot-reload an already cached
surface. Activate a verified Core update by restarting the Runtime service (or
by explicitly clearing `CoreSurfaceProvider` in a controlled local process),
then confirm that the live Core reference reports the intended
`artifact_version`.

Available public MCP tools:

- `boris.execute`: calls private `/runtime/execute`; Runtime verifies
  compatibility, compiles a strict `SemanticInput`, invokes the existing
  Semantic Executor, and returns a non-mutating `ExecutionCandidate`. A HOLD
  returns a signed operator handoff; resume calls the same tool and bypasses
  repeated input compilation.

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

A `HOLD` response contains `hold.required_operator_input` and a signed
`continuation_token`. The token contains the exact semantic continuation state
but no server secret. It is replayable until expiry because this stage has no
persistent token registry. Apply rate limits to `/mcp`, keep the TTL bounded,
and rotate `BORIS_CONTINUATION_SECRET` to invalidate all outstanding tokens.

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
Connects ChatGPT to BORIS. Use boris.execute for the Runtime semantic route. Present its ExecutionCandidate without replacing it with an independent answer or weakening HOLD, STOP, or REPAIR. For HOLD, request the specified operator input and resume only through the signed continuation.
```

After updating tool metadata, refresh connector metadata in ChatGPT.

Use `BORIS_RUNTIME_MODE=dev` in the Runtime server `.env` to return
`boris-execution-trace/1.0`. The execution request has no mode selector.
The MCP server reads the same non-secret mode setting and links
`boris.execute` to `ui://boris/developer-surface-v2.html`. The component
receives the complete safe trace through tool-result `_meta`, hidden from the
model, and displays it alongside the candidate and path-aware HOLD resume form.
The trace
combines lexical projection, `SemanticInput`, RuntimeAttestation, norm and
predicate results, constrained gate, validation issues, continuation status,
stage ledger, and timings. It contains no continuation token, hidden prompts,
chain-of-thought, server secrets, or absolute server paths. With any other mode,
the MCP server does not publish the Developer Surface resource.

Local smoke tests:

```bash
curl -s -X POST http://127.0.0.1:8000/runtime/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "execute-test",
    "input": "Explain the applicable BOIS constraints",
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
