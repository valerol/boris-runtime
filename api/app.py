import os
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.models import (
    HealthResponse,
    RuntimeAskRequest,
    RuntimeAskResponse,
    RuntimeErrorResponse,
    RuntimeFrameRequest,
    RuntimeFrameResponse,
    RuntimeResetRequest,
    RuntimeResetResponse,
    RuntimeSessionResponse,
)
from api.runtime_registry import RuntimeRegistry
from runtime.config import LLMConfigurationError, load_env_file


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


def _error_response(status_code, error, detail, session_id=None):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "detail": _safe_error_detail(detail),
            "session_id": session_id,
        },
    )


def _safe_error_detail(detail):
    text = str(detail)
    for env_name in ("OPENAI_API_KEY",):
        secret = os.getenv(env_name)
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


@app.post(
    "/runtime/ask",
    response_model=RuntimeAskResponse,
    responses={
        500: {"model": RuntimeErrorResponse},
        503: {"model": RuntimeErrorResponse},
    },
)
def ask_runtime(request: RuntimeAskRequest):
    session_id = request.session_id or str(uuid4())
    try:
        output = runtime_registry.run(session_id, request.input)
    except LLMConfigurationError as exc:
        return _error_response(503, "llm_unavailable", exc, session_id=session_id)
    except Exception as exc:
        return _error_response(500, "runtime_error", exc, session_id=session_id)

    metadata = dict(output.get("metadata", {}))
    metadata["transport"] = {
        "mode": request.mode,
        "context_received": bool(request.context),
    }

    return {
        "session_id": session_id,
        "type": output["type"],
        "content": output["content"],
        "metadata": metadata,
    }


@app.post(
    "/runtime/frame",
    response_model=RuntimeFrameResponse,
    responses={
        500: {"model": RuntimeErrorResponse},
        503: {"model": RuntimeErrorResponse},
    },
)
def frame_runtime(request: RuntimeFrameRequest):
    session_id = request.session_id or str(uuid4())
    try:
        return runtime_registry.frame(session_id, request.input)
    except LLMConfigurationError as exc:
        return _error_response(503, "llm_unavailable", exc, session_id=session_id)
    except Exception as exc:
        return _error_response(500, "runtime_error", exc, session_id=session_id)


@app.post("/runtime/reset", response_model=RuntimeResetResponse)
def reset_runtime(request: RuntimeResetRequest):
    return {
        "session_id": request.session_id,
        "reset": runtime_registry.reset(request.session_id),
    }


@app.get("/runtime/session/{session_id}", response_model=RuntimeSessionResponse)
def inspect_runtime_session(session_id: str):
    return {
        "session_id": session_id,
        "exists": runtime_registry.exists(session_id),
    }
