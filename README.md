# BOIS / SIMA / BORIS Middleware SDK

## Documentation

- Vision -> [docs/vision.md](docs/vision.md)
- Architecture -> [docs/architecture.md](docs/architecture.md)
- Protocol -> [docs/protocol.md](docs/protocol.md)
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
adapters/      LLM, memory, tool, and platform boundaries
cli/           validation CLI
api/           optional API boundary
examples/      usage examples
docs/          current documentation set
archive/       v0 runtime artifacts
```

## Run CLI

```bash
python cli/run.py
```

## Server Smoke Test

```bash
git pull
source .venv/bin/activate
python -m pip install -r requirements.txt
python cli/run.py
```

The CLI loads `.env` from the repository root automatically. Use
`BOIS_LLM=openai` and `OPENAI_API_KEY=...` in `.env` to use the OpenAI adapter;
otherwise it falls back to the deterministic mock adapter. It has no UI,
database, vector store, Telegram, or Open WebUI dependency.

## Architecture

Read [docs/architecture.md](docs/architecture.md) for the current SDK
architecture.
