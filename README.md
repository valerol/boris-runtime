# BOIS / SIMA / BORIS Middleware SDK

## Documentation

- Vision -> [docs/vision.md](docs/vision.md)
- Architecture -> [docs/architecture.md](docs/architecture.md)
- Protocol -> [docs/protocol.md](docs/protocol.md)
- Protocol Engine -> [docs/PROTOCOL_ENGINE.md](docs/PROTOCOL_ENGINE.md)
- Runtime Session -> [docs/RUNTIME_SESSION.md](docs/RUNTIME_SESSION.md)
- SDK API -> [docs/sdk_api.md](docs/sdk_api.md)
- Adapters -> [docs/adapters.md](docs/adapters.md)
- Roadmap -> [docs/roadmap.md](docs/roadmap.md)
- Archive -> [docs/archive.md](docs/archive.md)
- Changelog -> [CHANGELOG.md](CHANGELOG.md)

This repository has been reset from a runtime/platform MVP into a lightweight
protocol middleware SDK.

The project is not an AI platform and not a full runtime system. It enforces
BOIS / SIMA / BORIS protocol definitions on top of existing LLM platforms.

## Current Structure

```text
core/          declarative protocol definitions and loader
runtime/       minimal stateless protocol execution
protocol/      BOIS, SIMA, and BORIS protocol layers
prompt/        deterministic prompt construction
llm/           Phase 1 LLM adapter interface
adapters/      LLM, memory, tool, and platform boundaries
cli/           validation CLI
api/           optional API boundary
examples/      usage examples
docs/          current documentation set
archive/       v0 runtime artifacts
```

## Run CLI

```bash
python cli/main.py
```

## Server Smoke Test

```bash
git pull
source .venv/bin/activate
python -m pip install -r requirements.txt
python cli/main.py
```

The CLI loads `.env` from the repository root automatically. Use
`BOIS_LLM=openai` and `OPENAI_API_KEY=...` in `.env` to use the OpenAI adapter;
otherwise it falls back to the deterministic mock adapter. It has no UI,
database, vector store, Telegram, or Open WebUI dependency.

For CLI prompt visibility during development, set `BORIS_RUNTIME_MODE=dev` in
`.env`. In dev mode, the CLI prints the final prompt payload immediately before
the LLM adapter call.

## Local BOIS Core Retriever

`boris-runtime` does not own BOIS Core. The operator must provide the external
canonical machine-readable core file at:

```text
/opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Build the local semantic index:

```bash
cd /opt/boris-runtime
source .venv/bin/activate

python -m core_retriever.build_index \
  --core /opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json \
  --out /opt/boris-runtime/data/core_index
```

Runtime `.env` settings:

```env
BORIS_CORE_PATH=/opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json
BORIS_CORE_INDEX_DIR=/opt/boris-runtime/data/core_index
BORIS_CORE_RETRIEVER_ENABLED=true
BORIS_CORE_RETRIEVER_TOP_K=12
HF_HOME=/opt/boris-runtime/.cache/huggingface
```

Optional settings:

```env
BORIS_CORE_RETRIEVER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
BORIS_CORE_RETRIEVER_AUTO_BUILD=false
```

In development mode, missing index files fail clearly. In non-dev mode, the CLI
continues without `RETRIEVED_ACTIVE_CORE` if the index is not available.
Set `BORIS_CORE_RETRIEVER_ENABLED=false` to disable retrieval explicitly.

## Architecture

Read [docs/architecture.md](docs/architecture.md) for the current SDK
architecture.
