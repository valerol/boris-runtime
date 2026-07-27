from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    constr,
    model_validator,
)


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
    resolution_mode: Literal[
        "PROVIDE_INFORMATION",
        "CONFIRM_ASSUMPTION",
        "ALLOW_CONDITIONAL_PROCEEDING",
        "CHANGE_SCOPE",
        "TERMINATE_CYCLE",
    ]
    statement: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    resolved_unknowns: list[str] | None = None
    scope: "RuntimeOperatorScopeChange | None" = None


class RuntimeOperatorScopeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_layers: list[str] | None = None
    triggers: list[str] | None = None
    applicability_scopes: list[str] | None = None
    requested_norm_refs: list[str] | None = None

    @model_validator(mode="after")
    def require_selector(self):
        if all(
            value is None
            for value in (
                self.active_layers,
                self.triggers,
                self.applicability_scopes,
                self.requested_norm_refs,
            )
        ):
            raise ValueError(
                "Operator scope change requires at least one selector array."
            )
        return self


class RuntimeExecutionResume(BaseModel):
    continuation_token: constr(strip_whitespace=True, min_length=1)
    operator_input: RuntimeOperatorInput


class RuntimeExecutionRequest(BaseModel):
    operation: Literal["execute", "prepare", "submit"] = "execute"
    input: constr(strip_whitespace=True, min_length=1) | None = None
    session_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    resume: RuntimeExecutionResume | None = None
    work_order_id: constr(strip_whitespace=True, min_length=1) | None = None
    work_order_token: constr(strip_whitespace=True, min_length=1) | None = None
    semantic_input: dict[str, Any] | None = None
    semantic_result: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_route(self):
        host_fields = (
            self.work_order_id,
            self.work_order_token,
            self.semantic_input,
            self.semantic_result,
        )
        if self.operation in {"execute", "prepare"}:
            if (self.input is None) == (self.resume is None):
                raise ValueError(
                    "Provide exactly one of input or resume."
                )
            if self.resume is not None and self.context:
                raise ValueError(
                    "Continuation context is bound by continuation_token."
                )
            if any(value is not None for value in host_fields):
                raise ValueError(
                    "Host submission fields are allowed only in submit mode."
                )
        else:
            if self.input is not None or self.resume is not None or self.context:
                raise ValueError(
                    "Submit mode cannot replace work-order-bound input or context."
                )
            if self.work_order_id is None or self.work_order_token is None:
                raise ValueError(
                    "Submit mode requires work_order_id and work_order_token."
                )
            if (self.semantic_input is None) == (
                self.semantic_result is None
            ):
                raise ValueError(
                    "Submit mode requires exactly one of semantic_input or "
                    "semantic_result."
                )
        return self


class RuntimeHostWorkOrderBindings(BaseModel):
    attestation_sha256: str
    semantic_source_sha256: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    compiler_catalog_sha256: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    semantic_input_sha256: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    semantic_view_sha256: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    semantic_prompt_sha256: str
    response_schema_sha256: str


class RuntimeHostSubmissionContract(BaseModel):
    tool: Literal["boris.execute"]
    required_arguments: list[str]
    work_order_token: str


class RuntimeHostWorkOrderResponse(BaseModel):
    work_order_version: Literal["boris-semantic-work-order/0.4"]
    work_order_id: str
    work_order_type: Literal["COMPILATION", "CALCULATION"]
    session_id: str
    status: Literal["semantic_work_order"]
    semantic_provider: Literal["CHATGPT_HOST_ONLY"]
    phase: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    gate: Literal["HOLD"] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    minimum_context_window_tokens: int = Field(ge=0)
    core_ref: dict[str, str]
    issued_at: str
    expires_at: str
    semantic_prompt: str
    response_schema: dict[str, Any]
    phase_output_contract: dict[str, Any] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    correction: dict[str, Any] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    bindings: RuntimeHostWorkOrderBindings
    submission_contract: RuntimeHostSubmissionContract
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_work_order_type(self):
        bindings = self.bindings
        if self.work_order_type == "COMPILATION":
            if (
                self.phase is not None
                or self.phase_output_contract is not None
                or self.gate is not None
                or self.correction is not None
            ):
                raise ValueError(
                    "Compilation work order cannot contain phase or correction "
                    "state."
                )
            if (
                bindings.semantic_source_sha256 is None
                or bindings.compiler_catalog_sha256 is None
                or bindings.semantic_input_sha256 is not None
                or bindings.semantic_view_sha256 is not None
            ):
                raise ValueError(
                    "Compilation work-order bindings are invalid."
                )
            submission_field = "semantic_input"
        else:
            if (
                self.phase is None
                or self.phase_output_contract is None
                or bindings.semantic_input_sha256 is None
                or bindings.semantic_view_sha256 is None
                or bindings.semantic_source_sha256 is not None
                or bindings.compiler_catalog_sha256 is not None
            ):
                raise ValueError(
                    "Calculation work-order bindings are invalid."
                )
            if (self.gate is None) != (self.correction is None):
                raise ValueError(
                    "Calculation HOLD gate and correction contract must be "
                    "present "
                    "together."
                )
            submission_field = "semantic_result"
        if submission_field not in self.submission_contract.required_arguments:
            raise ValueError(
                "Submission contract does not match the work-order type."
            )
        return self


class RuntimeSemanticUnknown(BaseModel):
    unknown_id: str
    description: str
    target_path: str | None = None
    resolution_kind: str
    expected_type: str
    norm_refs: list[str] = Field(default_factory=list)
    core_refs: list[str] = Field(default_factory=list)
    source_resolution_class: str
    resolution_owner: Literal["OPERATOR"]
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
    source_resolution_class: str
    resolution_owner: Literal["OPERATOR"]
    question: str


class RuntimeSystemHoldTarget(BaseModel):
    target_id: str
    kind: str
    description: str
    target_path: str | None = None
    norm_refs: list[str] = Field(default_factory=list)
    source_resolution_class: str
    resolution_owner: Literal["OPERATOR"]


class RuntimeHoldResolutionMode(BaseModel):
    mode: Literal[
        "PROVIDE_INFORMATION",
        "CONFIRM_ASSUMPTION",
        "ALLOW_CONDITIONAL_PROCEEDING",
        "CHANGE_SCOPE",
        "TERMINATE_CYCLE",
    ]
    available: bool
    effect: str
    preserves_unknowns: bool


class RuntimeRequiredOperatorInput(BaseModel):
    question: str
    resolution_modes: list[RuntimeHoldResolutionMode] = Field(
        default_factory=list,
    )
    semantic_unknowns: list[RuntimeSemanticUnknown] = Field(
        default_factory=list,
    )
    predicate_inputs: list[RuntimePredicateInput] = Field(
        default_factory=list,
    )
    system_targets: list[RuntimeSystemHoldTarget] = Field(
        default_factory=list,
    )
    response_contract: dict[str, str] = Field(default_factory=dict)


class RuntimeHoldRecord(BaseModel):
    hold_id: str
    cycle_id: str
    return_state: str
    return_gate: str
    hold_reason: str
    scope: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    open_debts: list[str] = Field(default_factory=list)
    state_hash: str


class RuntimeBlockingPrecondition(BaseModel):
    precondition_id: str
    condition: Literal["RECOVERABLE_PRECONDITION_UNRESOLVED"]
    status: Literal["UNRESOLVED", "RESOLVED"]
    owner: Literal["OPERATOR"]
    description: str
    resolution_options: list[
        Literal[
            "PROVIDE_INFORMATION",
            "CONFIRM_ASSUMPTION",
            "ALLOW_CONDITIONAL_PROCEEDING",
            "CHANGE_SCOPE",
            "TERMINATE_CYCLE",
        ]
    ] = Field(default_factory=list)


class RuntimeHoldHandoff(BaseModel):
    handoff_version: Literal["boris-hold-handoff/1.4"]
    status: Literal[
        "operator_input_required",
        "operator_terminated",
    ]
    resolution_owner: Literal["OPERATOR"]
    reason: str
    hold_record: RuntimeHoldRecord
    blocking_precondition: RuntimeBlockingPrecondition
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
                or not self.blocking_precondition.resolution_options
            ):
                raise ValueError(
                    "An operator handoff requires input, token, expiry, and a "
                    "signed resolution mode."
                )
        else:
            if (
                self.required_operator_input is not None
                or self.continuation_token is not None
                or self.expires_at is not None
                or self.blocking_precondition.status != "RESOLVED"
            ):
                raise ValueError(
                    "A terminated HOLD must contain one resolved operator "
                    "precondition and no continuation."
                )
        return self


class RuntimeExecutionResponse(BaseModel):
    execution_version: Literal["boris-execution/1.0"]
    session_id: str
    status: Literal["semantic_candidate"]
    semantic_provider: Literal["CHATGPT_HOST_ONLY"] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    host_work_order_id: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
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
        if (self.semantic_provider is None) != (
            self.host_work_order_id is None
        ):
            raise ValueError(
                "Host provider and work-order ID must be present together."
            )
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
