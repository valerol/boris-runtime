from typing import Any, Literal

from pydantic import BaseModel, Field, constr


class RuntimeFrameRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: Literal["default", "production", "developer"] = "default"
    context: dict[str, Any] = Field(default_factory=dict)


class RuntimeSIMAFrame(BaseModel):
    risk: float = 0.0
    uncertainty: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    ambiguity_score: float = 0.0


class RuntimeProjectedCoreChunk(BaseModel):
    chunk_id: str
    section: str
    title: str
    text: str
    relevance: float = 0.0


class RuntimeProjectionMetadata(BaseModel):
    returned_chunks: int
    total_characters: int
    truncated: bool
    max_chunks: int
    max_chunk_characters: int
    max_total_characters: int


class RuntimeFrameResponse(BaseModel):
    packet_version: Literal["boris-context/2.0"]
    frame_id: str
    session_id: str
    input: str
    runtime_mode: Literal["context_provider"]
    llm_called: Literal[False]
    bois_frame: dict[str, Any] = Field(default_factory=dict)
    sima: RuntimeSIMAFrame
    boris_context: dict[str, Any] = Field(default_factory=dict)
    projected_core: list[RuntimeProjectedCoreChunk] = Field(default_factory=list)
    projection_metadata: RuntimeProjectionMetadata
    developer_trace: dict[str, Any] | None = None
    answer_instructions: list[str] = Field(default_factory=list)
    runtime_generated_prompt: str


ValidationMode = Literal["deterministic", "semantic", "hybrid"]
ValidationVerdict = Literal["PASS", "REVISE", "FAIL", "INDETERMINATE"]


class RuntimeValidationRequest(BaseModel):
    answer: constr(strip_whitespace=True, min_length=1)
    context_packet: dict[str, Any]
    validation_mode: ValidationMode = "deterministic"


class RuntimeValidationIssue(BaseModel):
    code: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    path: str | None = None
    source: Literal["preflight", "deterministic", "semantic"]
    semantic_required: bool


class RuntimeDeterministicCheck(BaseModel):
    code: str
    status: ValidationVerdict
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    path: str | None = None
    semantic_required: bool


class RuntimePreflightReport(BaseModel):
    status: Literal["completed", "failed"]
    issues: list[RuntimeValidationIssue] = Field(default_factory=list)


class RuntimeDeterministicReport(BaseModel):
    status: Literal["completed", "not_run"]
    verdict: ValidationVerdict
    checks: list[RuntimeDeterministicCheck] = Field(default_factory=list)
    issues: list[RuntimeValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RuntimeSemanticReport(BaseModel):
    status: Literal["completed", "not_run", "unavailable", "invalid_output"]
    verdict: ValidationVerdict
    issues: list[RuntimeValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RuntimeValidationResponse(BaseModel):
    validation_version: Literal["boris-validation/1.0"]
    frame_id: str | None = None
    validation_mode: ValidationMode
    verdict: ValidationVerdict
    llm_called: bool
    preflight: RuntimePreflightReport
    deterministic: RuntimeDeterministicReport
    semantic: RuntimeSemanticReport
    issues: list[RuntimeValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RuntimeErrorResponse(BaseModel):
    error: str
    detail: str
    session_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    api: str
