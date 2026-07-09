from uuid import uuid4

from fastapi import FastAPI

from api.models import HealthResponse, RuntimeAskRequest, RuntimeAskResponse
from api.runtime_registry import RuntimeRegistry
from runtime.config import load_env_file


load_env_file()

app = FastAPI(title="BORIS Runtime API")
runtime_registry = RuntimeRegistry()


@app.get("/health", response_model=HealthResponse)
def health():
    return {
        "status": "ok",
        "service": "boris-runtime",
        "api": "fastapi",
    }


@app.post("/runtime/ask", response_model=RuntimeAskResponse)
def ask_runtime(request: RuntimeAskRequest):
    session_id = request.session_id or str(uuid4())
    runtime = runtime_registry.get_or_create(session_id)
    output = runtime.run(request.input)

    return {
        "session_id": session_id,
        "type": output["type"],
        "content": output["content"],
        "metadata": output.get("metadata", {}),
    }
