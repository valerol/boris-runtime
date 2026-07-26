import os
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.models import (
    HealthResponse,
    RuntimeErrorResponse,
    RuntimeExecutionRequest,
    RuntimeExecutionResponse,
    RuntimeFrameRequest,
    RuntimeFrameResponse,
    RuntimeValidationRequest,
    RuntimeValidationResponse,
)
from application.context_provider import ContextProvider, CoreSurfaceUnavailable
from application.continuation import (
    ContinuationStateMismatch,
    ContinuationUnavailable,
    InvalidContinuationToken,
)
from application.execution import (
    ExecutionService,
    OperatorAcceptanceUnavailable,
    SemanticInputCompilationError,
)
from application.semantic_validation import SemanticValidationOutputError
from application.validation import ValidationEngine
from llm.config import build_lazy_validator_llm_adapter, load_env_file
from llm.errors import LLMConfigurationError
from runtime_compatibility import RuntimeCompatibilityError
from semantic_executor import SemanticExecutorError


load_env_file()

app = FastAPI(title="BORIS Runtime API")
context_provider = ContextProvider()
execution_service = ExecutionService()
validation_engine = ValidationEngine(
    validator_adapter_factory=build_lazy_validator_llm_adapter
)


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
    "/runtime/frame",
    response_model=RuntimeFrameResponse,
    response_model_exclude_none=True,
    responses={
        500: {"model": RuntimeErrorResponse},
        503: {"model": RuntimeErrorResponse},
    },
)
def frame_runtime(request: RuntimeFrameRequest):
    session_id = request.session_id or str(uuid4())
    try:
        return context_provider.frame(
            request.input,
            session_id=session_id,
        )
    except CoreSurfaceUnavailable as exc:
        return _error_response(
            503,
            "core_surface_unavailable",
            exc,
            session_id=session_id,
        )
    except Exception as exc:
        return _error_response(500, "runtime_error", exc, session_id=session_id)


@app.post(
    "/runtime/execute",
    response_model=RuntimeExecutionResponse,
    responses={
        400: {"model": RuntimeErrorResponse},
        409: {"model": RuntimeErrorResponse},
        500: {"model": RuntimeErrorResponse},
        502: {"model": RuntimeErrorResponse},
        503: {"model": RuntimeErrorResponse},
    },
)
def execute_runtime(request: RuntimeExecutionRequest):
    session_id = request.session_id
    if session_id is None and request.resume is None:
        session_id = str(uuid4())
    try:
        execution_arguments = {
            "session_id": session_id,
            "context": request.context,
        }
        if request.resume is not None:
            execution_arguments["resume"] = (
                request.resume.model_dump()
            )
        return execution_service.execute(
            request.input,
            **execution_arguments,
        )
    except InvalidContinuationToken as exc:
        return _error_response(
            400,
            "invalid_continuation",
            exc,
            session_id=session_id,
        )
    except ContinuationStateMismatch as exc:
        return _error_response(
            409,
            "continuation_state_mismatch",
            exc,
            session_id=session_id,
        )
    except ContinuationUnavailable as exc:
        return _error_response(
            503,
            "continuation_unavailable",
            exc,
            session_id=session_id,
        )
    except CoreSurfaceUnavailable as exc:
        return _error_response(
            503,
            "core_surface_unavailable",
            exc,
            session_id=session_id,
        )
    except OperatorAcceptanceUnavailable as exc:
        return _error_response(
            503,
            "operator_acceptance_unavailable",
            exc,
            session_id=session_id,
        )
    except RuntimeCompatibilityError as exc:
        return _error_response(
            409,
            "runtime_compatibility_rejected",
            exc,
            session_id=session_id,
        )
    except SemanticInputCompilationError as exc:
        return _error_response(
            502,
            "semantic_input_error",
            exc,
            session_id=session_id,
        )
    except (SemanticExecutorError, LLMConfigurationError) as exc:
        return _error_response(
            502,
            "semantic_execution_error",
            exc,
            session_id=session_id,
        )
    except Exception:
        return _error_response(
            500,
            "runtime_error",
            "Unexpected Runtime execution failure.",
            session_id=session_id,
        )


@app.post(
    "/runtime/validate",
    response_model=RuntimeValidationResponse,
    responses={
        500: {"model": RuntimeErrorResponse},
        502: {"model": RuntimeErrorResponse},
        503: {"model": RuntimeErrorResponse},
    },
)
def validate_runtime(request: RuntimeValidationRequest):
    session_id = request.context_packet.get("session_id")
    if not isinstance(session_id, str):
        session_id = None
    try:
        return validation_engine.validate(
            answer=request.answer,
            context_packet=request.context_packet,
            validation_mode=request.validation_mode,
        )
    except LLMConfigurationError as exc:
        return _error_response(503, "llm_unavailable", exc, session_id=session_id)
    except SemanticValidationOutputError as exc:
        return _error_response(502, "semantic_validation_error", exc, session_id=session_id)
    except Exception as exc:
        return _error_response(500, "runtime_error", exc, session_id=session_id)
