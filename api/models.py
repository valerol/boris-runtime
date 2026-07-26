from typing import Any, Literal

from pydantic import BaseModel, Field, constr, model_validator


class RuntimeFrameRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
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


class RuntimeOperatorInput(BaseModel):
    statement: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    resolved_unknowns: list[str] | None = None


class RuntimeExecutionResume(BaseModel):
    continuation_token: constr(strip_whitespace=True, min_length=1)
    operator_input: str | RuntimeOperatorInput


class RuntimeExecutionRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1) | None = None
    session_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    resume: RuntimeExecutionResume | None = None

    @model_validator(mode="after")
    def validate_route(self):
        if (self.input is None) == (self.resume is None):
            raise ValueError(
                "Provide exactly one of input or resume."
            )
        if self.resume is not None and self.context:
            raise ValueError(
                "Continuation context is bound by continuation_token."
            )
        return self


class RuntimeSemanticUnknown(BaseModel):
    unknown_id: str
    description: str
    target_path: str | None = None
    resolution_kind: str
    expected_type: str
    norm_refs: list[str] = Field(default_factory=list)
    question: str


class RuntimePredicateInput(BaseModel):
    input_id: str
    target_path: str
    resolution_kind: str
    expected_type: str
    norm_refs: list[str] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_ids: list[str] = Field(default_factory=list)
    uncertainty_descriptions: list[str] = Field(default_factory=list)
    question: str


class RuntimeRequiredOperatorInput(BaseModel):
    question: str
    semantic_unknowns: list[RuntimeSemanticUnknown] = Field(
        default_factory=list,
    )
    predicate_inputs: list[RuntimePredicateInput] = Field(
        default_factory=list,
    )
    response_contract: dict[str, str] = Field(default_factory=dict)


class RuntimeHoldHandoff(BaseModel):
    handoff_version: Literal[
        "boris-hold-handoff/1.1",
        "boris-hold-handoff/1.2",
    ]
    status: Literal[
        "operator_input_required",
        "resolution_not_operator_owned",
    ]
    reason: str
    required_operator_input: RuntimeRequiredOperatorInput | None
    continuation_token: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    expires_at: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    resolution_summary: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict,
    )
    resume_count: int = 0

    @model_validator(mode="after")
    def validate_handoff_route(self):
        if self.status == "operator_input_required":
            if (
                self.required_operator_input is None
                or not self.continuation_token
                or not self.expires_at
            ):
                raise ValueError(
                    "An operator handoff requires input, token, and expiry."
                )
        elif (
            self.required_operator_input is not None
            or self.continuation_token is not None
            or self.expires_at is not None
        ):
            raise ValueError(
                "A non-operator HOLD cannot contain operator continuation."
            )
        return self


class RuntimeExecutionResponse(BaseModel):
    execution_version: Literal["boris-execution/1.0"]
    session_id: str
    status: Literal["semantic_candidate"]
    phase: str
    gate: Literal["PASS", "HOLD", "STOP", "REPAIR"]
    candidate_result: dict[str, Any] | None
    candidate_unavailable_reason: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    norm_results: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    uncertainties: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    hold: RuntimeHoldHandoff | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    developer_trace: dict[str, Any] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def validate_execution_envelope(self):
        if self.candidate_result == {}:
            raise ValueError("candidate_result must not be an empty object.")
        if (
            self.candidate_result is None
            and not self.candidate_unavailable_reason
        ):
            raise ValueError(
                "A null candidate_result requires candidate_unavailable_reason."
            )
        if (
            self.candidate_result is not None
            and self.candidate_unavailable_reason is not None
        ):
            raise ValueError(
                "candidate_unavailable_reason requires a null candidate_result."
            )
        if self.gate == "HOLD" and self.hold is None:
            raise ValueError("A HOLD result requires a hold handoff.")
        if self.gate != "HOLD" and self.hold is not None:
            raise ValueError("Only a HOLD result may contain a hold handoff.")
        return self


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
