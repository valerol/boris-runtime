from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from application.continuation import (
    ContinuationCodec,
    ContinuationStateMismatch,
    build_hold_handoff,
    build_system_issue_handoff,
    continuation_count,
    continuation_source_input,
    continuation_text,
    require_continuation_core,
    resume_hold,
    resume_token,
    trace_handoff,
)
from application.context_packet import sanitize_public_value
from application.context_provider import (
    ContextProvider,
    CoreSurfaceProvider,
)
from application.host_executor import (
    CALCULATION_WORK_ORDER,
    COMPILATION_WORK_ORDER,
    HOST_EXECUTOR_LIMITATIONS,
    HOST_SEMANTIC_PROVIDER,
    MAX_HOST_SEMANTIC_INPUT_CHARACTERS,
    MAX_HOST_SEMANTIC_RESULT_CHARACTERS,
    HostWorkOrderCodec,
    HostWorkOrderStateMismatch,
    InMemoryHostWorkOrderRegistry,
    InvalidHostWorkOrder,
    SubmittedSemanticCalculator,
    build_host_compilation_work_order,
    build_host_work_order,
    consume_host_work_order,
    require_current_compilation_scope,
    require_current_host_scope,
    validate_host_submission_payload,
)
from application.phase_output import (
    PhaseOutputContract,
    PhaseOutputValidationError,
)
from application.runtime_mode import developer_mode_enabled
from llm.config import build_lazy_llm_adapter
from runtime_compatibility import (
    OperatorAcceptance,
    RuntimeCompatibilityVerifier,
)
from runtime_compatibility.errors import RuntimeAttestationError
from semantic_executor import (
    CoreReference,
    LLMSemanticCalculator,
    SemanticCalculationError,
    SemanticExecutor,
    SemanticInput,
    SemanticViewBuilder,
)


EXECUTION_VERSION = "boris-execution/1.0"
OPERATOR_ACCEPTANCE_ENV = "BORIS_OPERATOR_ACCEPTANCE_FILE"
MAX_COMPILER_PROMPT_CHARACTERS = 200000
MAX_COMPILER_LIST_ITEMS = 128
MAX_COMPILER_TEXT_CHARACTERS = 2000
SEMANTIC_INPUT_FIELDS = {
    "phenomenon",
    "phase",
    "facts",
    "unknowns",
    "evidence",
    "authority",
    "active_layers",
    "triggers",
    "applicability_scopes",
    "requested_norm_refs",
    "evaluate_inactive",
}
PUBLIC_LIMITATIONS = (
    "not_independently_reviewed",
    "not_policy_admitted",
    "no_state_mutation",
    "no_external_action",
)
PHASE_CROSSWALK_PATH = "assurance/CYCLE_CROSSWALK.json"


class OperatorAcceptanceUnavailable(RuntimeError):
    """Raised when server-owned acceptance cannot be loaded safely."""


class SemanticInputCompilationError(RuntimeError):
    """Raised when raw input cannot be compiled into a strict SemanticInput."""


class OperatorAcceptanceProvider:
    """Resolve acceptance from trusted server configuration, never request data."""

    def __init__(
        self,
        source: str | None = None,
        acceptance: OperatorAcceptance | Mapping | None = None,
    ):
        self._source = source
        self._acceptance = acceptance

    def get(self, surface) -> OperatorAcceptance:
        value = self._acceptance
        if value is None:
            source = self._source or os.getenv(OPERATOR_ACCEPTANCE_ENV)
            if not source:
                if surface.source_kind == "directory":
                    return self._accept_configured_repository(surface)
                raise OperatorAcceptanceUnavailable(
                    "Server OperatorAcceptance is not configured for the "
                    "archive Core source."
                )
            try:
                payload = Path(source).read_text(encoding="utf-8")
                value = json.loads(payload)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OperatorAcceptanceUnavailable(
                    "Server OperatorAcceptance is unavailable or invalid."
                ) from exc

        try:
            acceptance = (
                value
                if isinstance(value, OperatorAcceptance)
                else OperatorAcceptance.from_dict(value)
            )
        except (RuntimeAttestationError, TypeError) as exc:
            raise OperatorAcceptanceUnavailable(
                "Server OperatorAcceptance is unavailable or invalid."
            ) from exc

        expected = (
            surface.package_id,
            surface.artifact_version,
            surface.archive_sha256 or "",
            surface.manifest_sha256,
        )
        actual = (
            acceptance.package_id,
            acceptance.artifact_version,
            acceptance.archive_sha256,
            acceptance.manifest_sha256,
        )
        if actual != expected:
            raise OperatorAcceptanceUnavailable(
                "Server OperatorAcceptance does not match the loaded Core source."
            )
        return acceptance

    @staticmethod
    def _accept_configured_repository(surface) -> OperatorAcceptance:
        return OperatorAcceptance(
            package_id=surface.package_id,
            artifact_version=surface.artifact_version,
            archive_sha256="",
            manifest_sha256=surface.manifest_sha256,
            operator_role="RUNTIME_CONFIGURED_CORE_REPOSITORY",
            decision="ACCEPT",
            accepted_scope=("semantic_evaluation",),
            decision_time=datetime.now(timezone.utc).isoformat(),
            revocation_route=(
                "Change BORIS_CORE_PACKAGE or stop the Runtime service."
            ),
        )


class SemanticInputCompiler:
    """Compile untrusted request material against the verified selector vocabulary."""

    def __init__(self, llm_adapter, view_builder=None):
        self.llm_adapter = llm_adapter
        self.view_builder = view_builder or SemanticViewBuilder()
        self.last_catalog = None

    def compile(
        self,
        surface,
        user_input: str,
        context: Mapping | None = None,
    ) -> SemanticInput:
        source, catalog, prompt = self.prepare(
            surface,
            user_input,
            context=context,
        )
        if not hasattr(self.llm_adapter, "call_structured"):
            raise SemanticInputCompilationError(
                "The configured LLM port does not support structured calls."
            )
        try:
            raw_output = self.llm_adapter.call_structured(
                prompt,
                (
                    "Return only the strict SemanticInput JSON contract. "
                    "Do not return analysis or hidden reasoning."
                ),
            )
        except SemanticInputCompilationError:
            raise
        except Exception as exc:
            raise SemanticInputCompilationError(
                "Structured SemanticInput compilation failed."
            ) from exc
        return self.validate_submission(raw_output, source, catalog)

    def prepare(
        self,
        surface,
        user_input: str,
        context: Mapping | None = None,
    ) -> tuple[dict, Mapping, str]:
        text = str(user_input or "").strip()
        if not text:
            raise SemanticInputCompilationError(
                "Semantic input phenomenon must not be empty."
            )
        source = _source_semantic_material(text, context)
        catalog = self.view_builder.applicability_catalog(surface)
        if not catalog["phases"]:
            raise SemanticInputCompilationError(
                "Core Surface does not expose an allowed semantic phase."
            )
        self.last_catalog = catalog
        prompt = build_semantic_input_prompt(
            surface,
            source,
            catalog,
        )
        if len(prompt) > MAX_COMPILER_PROMPT_CHARACTERS:
            raise SemanticInputCompilationError(
                "Semantic input compiler prompt exceeds the application limit."
            )
        return source, catalog, prompt

    @staticmethod
    def validate_submission(
        raw_output,
        source,
        catalog,
    ) -> SemanticInput:
        payload = _decode_compiler_output(raw_output)
        _require_exact_fields(payload, SEMANTIC_INPUT_FIELDS, "SemanticInput")

        if payload["phenomenon"] != source["phenomenon"]:
            raise SemanticInputCompilationError(
                "Compiled phenomenon does not exactly preserve the request."
            )
        facts = _object(payload["facts"], "facts")
        authority = _object(payload["authority"], "authority")
        evidence = _object_array(payload["evidence"], "evidence")
        if facts != source["facts"]:
            raise SemanticInputCompilationError(
                "Compiler must not add, remove, or change supplied facts."
            )
        if evidence != source["evidence"]:
            raise SemanticInputCompilationError(
                "Compiler must not add, remove, or change supplied evidence."
            )
        if authority != source["authority"]:
            raise SemanticInputCompilationError(
                "Compiler must not add, remove, or change supplied authority."
            )

        phase = _text(payload["phase"], "phase")
        _require_allowed(phase, catalog["phases"], "phase")
        unknowns = _string_array(payload["unknowns"], "unknowns")
        if not set(source["unknowns"]).issubset(unknowns):
            raise SemanticInputCompilationError(
                "Compiler must preserve every supplied unknown."
            )
        active_layers = _validated_array(
            payload["active_layers"],
            "active_layers",
            catalog["layers"],
        )
        triggers = _validated_array(
            payload["triggers"],
            "triggers",
            catalog["triggers"],
        )
        applicability_scopes = _validated_array(
            payload["applicability_scopes"],
            "applicability_scopes",
            catalog["applicability_scopes"],
        )
        requested_norm_refs = _validated_array(
            payload["requested_norm_refs"],
            "requested_norm_refs",
            catalog["norm_refs"],
        )
        if not set(source["requested_norm_refs"]).issubset(
            requested_norm_refs
        ):
            raise SemanticInputCompilationError(
                "Compiler must preserve every supplied requested norm reference."
            )
        for norm_ref in requested_norm_refs:
            if (
                norm_ref not in source["requested_norm_refs"]
                and not _contains_literal(source["input"], norm_ref)
            ):
                raise SemanticInputCompilationError(
                    "Compiler may request a norm only when the request names it "
                    "explicitly."
                )
        if payload["evaluate_inactive"] is not False:
            raise SemanticInputCompilationError(
                "Application SemanticInput cannot enable inactive norm evaluation."
            )

        return SemanticInput(
            phenomenon=source["phenomenon"],
            phase=phase,
            facts=facts,
            unknowns=unknowns,
            evidence=evidence,
            authority=authority,
            active_layers=active_layers,
            triggers=triggers,
            applicability_scopes=applicability_scopes,
            requested_norm_refs=requested_norm_refs,
            evaluate_inactive=False,
        )


class ExecutionService:
    """Application orchestrator for one immutable semantic-candidate route."""

    def __init__(
        self,
        surface_provider=None,
        acceptance_provider=None,
        compatibility_verifier=None,
        llm_adapter_factory=None,
        compiler_factory=None,
        calculator_factory=None,
        context_provider=None,
        continuation_codec_factory=None,
        host_work_order_codec_factory=None,
        host_work_order_registry=None,
    ):
        self.surface_provider = surface_provider or CoreSurfaceProvider()
        self.acceptance_provider = (
            acceptance_provider or OperatorAcceptanceProvider()
        )
        self.compatibility_verifier = (
            compatibility_verifier or RuntimeCompatibilityVerifier()
        )
        self.llm_adapter_factory = (
            llm_adapter_factory or build_lazy_llm_adapter
        )
        self.compiler_factory = (
            compiler_factory
            or (lambda adapter: SemanticInputCompiler(adapter))
        )
        self.calculator_factory = (
            calculator_factory
            or (lambda adapter: LLMSemanticCalculator(adapter))
        )
        self.context_provider = (
            context_provider or ContextProvider(self.surface_provider)
        )
        self.continuation_codec_factory = (
            continuation_codec_factory or ContinuationCodec.from_environment
        )
        self.host_work_order_codec_factory = (
            host_work_order_codec_factory
            or HostWorkOrderCodec.from_environment
        )
        self.host_work_order_registry = (
            host_work_order_registry
            or InMemoryHostWorkOrderRegistry()
        )

    def prepare_host(
        self,
        user_input: str | None = None,
        session_id: str | None = None,
        context: Mapping | None = None,
        resume: Mapping | None = None,
    ) -> dict:
        codec = self.host_work_order_codec_factory()
        if resume is None:
            text = str(user_input or "").strip()
            if not text:
                raise ValueError("Execution input must not be empty.")
            if context is not None and not isinstance(context, Mapping):
                raise ValueError("Execution context must be an object.")
            resolved_session_id = session_id or str(uuid4())
            continuation_state = None
            continuation_resume = None
            resume_count = 0
        else:
            if user_input is not None or context:
                raise ValueError(
                    "A continuation request cannot replace token-bound input or context."
                )
            continuation_codec = self.continuation_codec_factory()
            continuation_state = continuation_codec.verify(
                resume_token(resume)
            )
            token_session_id = continuation_text(
                continuation_state,
                "session_id",
            )
            if session_id is not None and session_id != token_session_id:
                raise ContinuationStateMismatch(
                    "Continuation session_id does not match the signed state."
                )
            resolved_session_id = token_session_id
            resume_count = continuation_count(continuation_state) + 1
            text = continuation_source_input(continuation_state)

        surface = self.surface_provider.get()
        acceptance = self.acceptance_provider.get(surface)
        compatibility = self.compatibility_verifier.verify(
            surface,
            operator_acceptance=acceptance,
        )
        compatibility.require_semantic_evaluation(surface)

        if continuation_state is None:
            compiler = self.compiler_factory(None)
            source, catalog, semantic_prompt = compiler.prepare(
                surface,
                text,
                context=context,
            )
            response_schema = semantic_input_response_schema(
                source,
                catalog,
            )
            return build_host_compilation_work_order(
                codec=codec,
                registry=self.host_work_order_registry,
                source_material=source,
                compiler_catalog=catalog,
                semantic_prompt=semantic_prompt,
                response_schema=response_schema,
                session_id=resolved_session_id,
                source_text=text,
                core_ref=CoreReference.from_surface(surface).to_dict(),
                resume_count=resume_count,
                attestation_sha256=compatibility.attestation_sha256,
            )

        require_continuation_core(continuation_state, surface)
        continuation_resume = resume_hold(
            continuation_state,
            resume,
        )
        if continuation_resume.terminated:
            return _operator_termination_envelope(
                session_id=resolved_session_id,
                resume_count=resume_count,
                continuation_resume=continuation_resume,
            )
        semantic_input = continuation_resume.semantic_input
        _validate_operator_scope_change(
            surface,
            semantic_input,
            continuation_resume.operator_decision,
        )
        view = SemanticViewBuilder().build(
            surface,
            semantic_input,
            operator_decision=continuation_resume.operator_decision,
        )
        return build_host_work_order(
            codec=codec,
            registry=self.host_work_order_registry,
            semantic_input=semantic_input,
            view=view,
            session_id=resolved_session_id,
            source_text=text,
            resume_count=resume_count,
            resumed=continuation_state is not None,
            attestation_sha256=compatibility.attestation_sha256,
            continuation_cycle_id=continuation_resume.cycle_id,
            continuation_resolution=dict(
                continuation_resume.precondition_resolution
            ),
            operator_decision=dict(
                continuation_resume.operator_decision
            ),
        )

    def submit_host(
        self,
        *,
        work_order_id: str,
        work_order_token: str,
        semantic_input: Mapping | None = None,
        semantic_result: Mapping | None = None,
        session_id: str | None = None,
    ) -> dict:
        codec = self.host_work_order_codec_factory()
        state = consume_host_work_order(
            codec=codec,
            registry=self.host_work_order_registry,
            work_order_id=work_order_id,
            work_order_token=work_order_token,
            session_id=session_id,
        )
        timings = {}
        started = perf_counter()

        stage_started = perf_counter()
        surface = self.surface_provider.get()
        timings["core_surface_load"] = _elapsed_ms(stage_started)

        stage_started = perf_counter()
        acceptance = self.acceptance_provider.get(surface)
        timings["operator_acceptance_load"] = _elapsed_ms(stage_started)

        stage_started = perf_counter()
        compatibility = self.compatibility_verifier.verify(
            surface,
            operator_acceptance=acceptance,
        )
        compatibility.require_semantic_evaluation(surface)
        timings["runtime_compatibility"] = _elapsed_ms(stage_started)

        if state.work_order_type == COMPILATION_WORK_ORDER:
            if semantic_result is not None or semantic_input is None:
                raise InvalidHostWorkOrder(
                    "Compilation work order requires semantic_input only."
                )
            submitted_input = validate_host_submission_payload(
                semantic_input,
                field_name="semantic_input",
                maximum_characters=MAX_HOST_SEMANTIC_INPUT_CHARACTERS,
            )
            if (
                state.source_material is None
                or state.compiler_catalog is None
            ):
                raise HostWorkOrderStateMismatch(
                    "Compilation work-order state is incomplete."
                )
            current_catalog = SemanticViewBuilder().applicability_catalog(
                surface
            )
            current_prompt = build_semantic_input_prompt(
                surface,
                state.source_material,
                current_catalog,
            )
            current_schema = semantic_input_response_schema(
                state.source_material,
                current_catalog,
            )
            require_current_compilation_scope(
                state,
                core_ref=CoreReference.from_surface(surface).to_dict(),
                attestation_sha256=compatibility.attestation_sha256,
                source_material=state.source_material,
                compiler_catalog=current_catalog,
                semantic_prompt=current_prompt,
                response_schema=current_schema,
            )
            compiled_input = SemanticInputCompiler.validate_submission(
                submitted_input,
                state.source_material,
                current_catalog,
            )
            view = SemanticViewBuilder().build(surface, compiled_input)
            return build_host_work_order(
                codec=codec,
                registry=self.host_work_order_registry,
                semantic_input=compiled_input,
                view=view,
                session_id=state.session_id,
                source_text=state.source_text,
                resume_count=state.resume_count,
                resumed=state.resumed,
                attestation_sha256=compatibility.attestation_sha256,
            )

        if state.work_order_type != CALCULATION_WORK_ORDER:
            raise HostWorkOrderStateMismatch(
                "Host work order has an unsupported type."
            )
        if semantic_input is not None or semantic_result is None:
            raise InvalidHostWorkOrder(
                "Calculation work order requires semantic_result only."
            )
        submitted_result = validate_host_submission_payload(
            semantic_result,
            field_name="semantic_result",
            maximum_characters=MAX_HOST_SEMANTIC_RESULT_CHARACTERS,
        )
        calculator = SubmittedSemanticCalculator(submitted_result)
        if state.semantic_input is None:
            raise HostWorkOrderStateMismatch(
                "Calculation work-order state is incomplete."
            )
        view = SemanticViewBuilder().build(
            surface,
            state.semantic_input,
            operator_decision=state.operator_decision,
        )
        require_current_host_scope(
            state,
            view=view,
            attestation_sha256=compatibility.attestation_sha256,
        )
        stage_started = perf_counter()
        try:
            PhaseOutputContract.from_view(view).validate(
                submitted_result.get("candidate_result")
            )
            executor = SemanticExecutor(
                surface,
                calculator,
                compatibility,
            )
            candidate = executor.execute(
                state.semantic_input,
                operator_decision=state.operator_decision,
            )
        except (
            PhaseOutputValidationError,
            SemanticCalculationError,
        ) as exc:
            timings["semantic_executor"] = _elapsed_ms(stage_started)
            issues = _host_submission_issues(
                exc,
                submitted_result,
            )
            if state.correction_count == 0:
                return build_host_work_order(
                    codec=codec,
                    registry=self.host_work_order_registry,
                    semantic_input=state.semantic_input,
                    view=view,
                    session_id=state.session_id,
                    source_text=state.source_text,
                    resume_count=state.resume_count,
                    resumed=state.resumed,
                    attestation_sha256=(
                        compatibility.attestation_sha256
                    ),
                    correction_count=1,
                    parent_work_order_id=state.work_order_id,
                    correction_issues=tuple(issues),
                    continuation_cycle_id=(
                        state.continuation_cycle_id
                    ),
                    continuation_resolution=(
                        state.continuation_resolution
                    ),
                    operator_decision=state.operator_decision,
                )
            return self._host_compliance_hold(
                state=state,
                semantic_input=state.semantic_input,
                issues=issues,
                timings=timings,
                started=started,
            )
        timings["semantic_executor"] = _elapsed_ms(stage_started)
        return self._candidate_envelope(
            candidate=candidate,
            semantic_input=state.semantic_input,
            session_id=state.session_id,
            source_text=state.source_text,
            compatibility=compatibility,
            timings=timings,
            resume_count=state.resume_count,
            resumed=state.resumed,
            semantic_provider=HOST_SEMANTIC_PROVIDER,
            host_work_order_id=state.work_order_id,
            continuation_cycle_id=state.continuation_cycle_id,
            continuation_resolution=state.continuation_resolution,
            operator_decision=state.operator_decision,
            started=started,
        )

    def _host_compliance_hold(
        self,
        *,
        state,
        semantic_input,
        issues,
        timings,
        started,
    ) -> dict:
        reason = (
            "The single correction submission remained invalid for the "
            f"canonical {semantic_input.phase} output contract. Runtime "
            "preserved HOLD and ended automatic submission."
        )
        result = {
            "execution_version": EXECUTION_VERSION,
            "session_id": state.session_id,
            "status": "semantic_candidate",
            "semantic_provider": HOST_SEMANTIC_PROVIDER,
            "host_work_order_id": state.work_order_id,
            "phase": semantic_input.phase,
            "gate": "HOLD",
            "candidate_result": None,
            "candidate_unavailable_reason": reason,
            "norm_results": [],
            "unknowns": list(semantic_input.unknowns),
            "uncertainties": [],
            "conflicts": [],
            "alternatives": [],
            "limitations": [
                *HOST_EXECUTOR_LIMITATIONS,
                *PUBLIC_LIMITATIONS,
            ],
            "hold": build_system_issue_handoff(
                codec=self.continuation_codec_factory(),
                semantic_input=semantic_input,
                core_ref=state.core_ref,
                session_id=state.session_id,
                resume_count=state.resume_count,
                reason=reason,
                issues=issues,
                cycle_id=state.continuation_cycle_id,
                operator_decision=state.operator_decision,
            ),
        }
        if developer_mode_enabled():
            result["developer_trace"] = {
                "semantic_submission": {
                    "status": "HOLD",
                    "correction_count": state.correction_count,
                    "previous_work_order_id": (
                        state.parent_work_order_id
                    ),
                    "issues": [dict(issue) for issue in issues],
                },
                "stages": {
                    "semantic_input_compiler": (
                        "not_invoked_repair_submission"
                    ),
                    "semantic_executor": (
                        "rejected_before_candidate"
                    ),
                    "independent_reviewer": "not_implemented",
                    "policy_kernel": "not_implemented",
                    "state_event": "not_implemented",
                },
                "stage_timings_ms": {
                    **dict(timings),
                    "total": _elapsed_ms(started),
                },
            }
        return sanitize_public_value(result)

    def execute(
        self,
        user_input: str | None = None,
        session_id: str | None = None,
        context: Mapping | None = None,
        resume: Mapping | None = None,
    ) -> dict:
        if resume is None:
            text = str(user_input or "").strip()
            if not text:
                raise ValueError("Execution input must not be empty.")
            if context is not None and not isinstance(context, Mapping):
                raise ValueError("Execution context must be an object.")
            resolved_session_id = session_id or str(uuid4())
            continuation_state = None
            continuation_resume = None
            resume_count = 0
        else:
            if user_input is not None or context:
                raise ValueError(
                    "A continuation request cannot replace token-bound input or context."
                )
            codec = self.continuation_codec_factory()
            continuation_state = codec.verify(
                resume_token(resume)
            )
            token_session_id = continuation_text(
                continuation_state,
                "session_id",
            )
            if session_id is not None and session_id != token_session_id:
                raise ContinuationStateMismatch(
                    "Continuation session_id does not match the signed state."
                )
            resolved_session_id = token_session_id
            resume_count = continuation_count(continuation_state) + 1
            text = continuation_source_input(continuation_state)
        timings = {}
        started = perf_counter()

        stage_started = perf_counter()
        surface = self.surface_provider.get()
        timings["core_surface_load"] = _elapsed_ms(stage_started)

        stage_started = perf_counter()
        acceptance = self.acceptance_provider.get(surface)
        timings["operator_acceptance_load"] = _elapsed_ms(stage_started)

        stage_started = perf_counter()
        compatibility = self.compatibility_verifier.verify(
            surface,
            operator_acceptance=acceptance,
        )
        compatibility.require_semantic_evaluation(surface)
        timings["runtime_compatibility"] = _elapsed_ms(stage_started)

        adapter = self.llm_adapter_factory()
        if continuation_state is None:
            compiler = self.compiler_factory(adapter)
            stage_started = perf_counter()
            semantic_input = compiler.compile(surface, text, context=context)
            timings["semantic_input_compile"] = _elapsed_ms(stage_started)
        else:
            require_continuation_core(continuation_state, surface)
            stage_started = perf_counter()
            continuation_resume = resume_hold(
                continuation_state,
                resume,
            )
            if continuation_resume.terminated:
                return _operator_termination_envelope(
                    session_id=resolved_session_id,
                    resume_count=resume_count,
                    continuation_resume=continuation_resume,
                )
            semantic_input = continuation_resume.semantic_input
            _validate_operator_scope_change(
                surface,
                semantic_input,
                continuation_resume.operator_decision,
            )
            timings["continuation_resume"] = _elapsed_ms(stage_started)

        calculator = self.calculator_factory(adapter)
        executor = SemanticExecutor(
            surface,
            calculator,
            compatibility,
        )
        stage_started = perf_counter()
        candidate = executor.execute(
            semantic_input,
            operator_decision=(
                continuation_resume.operator_decision
                if continuation_resume is not None
                else None
            ),
        )
        timings["semantic_executor"] = _elapsed_ms(stage_started)
        return self._candidate_envelope(
            candidate=candidate,
            semantic_input=semantic_input,
            session_id=resolved_session_id,
            source_text=text,
            compatibility=compatibility,
            timings=timings,
            resume_count=resume_count,
            resumed=continuation_state is not None,
            semantic_provider="OPENAI_API",
            continuation_cycle_id=(
                continuation_resume.cycle_id
                if continuation_resume is not None
                else None
            ),
            continuation_resolution=(
                continuation_resume.precondition_resolution
                if continuation_resume is not None
                else None
            ),
            operator_decision=(
                continuation_resume.operator_decision
                if continuation_resume is not None
                else None
            ),
            started=started,
        )

    def _candidate_envelope(
        self,
        *,
        candidate,
        semantic_input,
        session_id,
        source_text,
        compatibility,
        timings,
        resume_count,
        resumed,
        semantic_provider,
        started,
        host_work_order_id=None,
        continuation_cycle_id=None,
        continuation_resolution=None,
        operator_decision=None,
    ):
        candidate_result = candidate.to_dict()["candidate_result"]
        candidate_unavailable_reason = None
        if not candidate_result:
            if candidate.gate != "HOLD":
                raise SemanticCalculationError(
                    "A non-HOLD ExecutionCandidate must contain a non-empty "
                    "candidate_result."
                )
            candidate_result = None
            candidate_unavailable_reason = (
                "The semantic calculation did not produce a conditional "
                "candidate while material HOLD conditions remain unresolved."
            )

        envelope = {
            "execution_version": EXECUTION_VERSION,
            "session_id": session_id,
            "status": "semantic_candidate",
            "phase": candidate.phase,
            "gate": candidate.gate,
            "candidate_result": candidate_result,
            "norm_results": [
                result.to_dict()
                for result in candidate.norm_results
            ],
            "unknowns": list(candidate.unknowns),
            "uncertainties": [
                uncertainty.to_dict()
                for uncertainty in candidate.uncertainties
            ],
            "conflicts": [
                conflict.to_dict()
                for conflict in candidate.conflicts
            ],
            "alternatives": candidate.to_dict()["alternatives"],
            "limitations": list(PUBLIC_LIMITATIONS),
        }
        if semantic_provider == HOST_SEMANTIC_PROVIDER:
            envelope["semantic_provider"] = semantic_provider
            envelope["host_work_order_id"] = host_work_order_id
            envelope["limitations"] = list(dict.fromkeys((
                *envelope["limitations"],
                *HOST_EXECUTOR_LIMITATIONS,
            )))
        if candidate_unavailable_reason is not None:
            envelope["candidate_unavailable_reason"] = (
                candidate_unavailable_reason
            )
        if candidate.gate == "HOLD":
            codec = self.continuation_codec_factory()
            envelope["hold"] = build_hold_handoff(
                codec,
                semantic_input,
                candidate,
                session_id,
                resume_count,
                cycle_id=continuation_cycle_id,
                operator_decision=operator_decision,
            )
        if developer_mode_enabled():
            stage_started = perf_counter()
            frame = self.context_provider.frame(
                source_text,
                session_id=session_id,
            )
            timings["context_projection"] = _elapsed_ms(stage_started)
            timings["total"] = _elapsed_ms(started)
            envelope["developer_trace"] = _build_execution_trace(
                frame,
                semantic_input,
                candidate,
                compatibility,
                timings,
                continuation={
                    "resumed": resumed,
                    "resume_count": resume_count,
                    "cycle_id": (
                        envelope.get("hold", {})
                        .get("hold_record", {})
                        .get("cycle_id")
                        or continuation_cycle_id
                    ),
                    "precondition_resolution": (
                        dict(continuation_resolution)
                        if continuation_resolution is not None
                        else None
                    ),
                    "handoff": trace_handoff(envelope.get("hold")),
                },
                semantic_provider=semantic_provider,
                host_work_order_id=host_work_order_id,
            )
        return envelope


def _operator_termination_envelope(
    *,
    session_id,
    resume_count,
    continuation_resume,
):
    decision = dict(continuation_resume.operator_decision)
    hold_record = dict(continuation_resume.hold_record)
    precondition_id = continuation_resume.precondition_resolution[
        "precondition_id"
    ]
    reason = (
        "The operator terminated this HOLD cycle without PASS or another "
        "semantic calculation."
    )
    result = {
        "execution_version": EXECUTION_VERSION,
        "session_id": session_id,
        "status": "semantic_candidate",
        "phase": hold_record["return_state"],
        "gate": "HOLD",
        "candidate_result": {
            "status": "OPERATOR_TERMINATED",
            "operator_decision": decision,
        },
        "norm_results": [],
        "unknowns": list(
            continuation_resume.semantic_input.unknowns
        ),
        "uncertainties": [],
        "conflicts": [],
        "alternatives": [],
        "limitations": list(PUBLIC_LIMITATIONS),
        "hold": {
            "handoff_version": "boris-hold-handoff/1.4",
            "status": "operator_terminated",
            "resolution_owner": "OPERATOR",
            "reason": reason,
            "hold_record": hold_record,
            "blocking_precondition": {
                "precondition_id": precondition_id,
                "condition": (
                    "RECOVERABLE_PRECONDITION_UNRESOLVED"
                ),
                "status": "RESOLVED",
                "owner": "OPERATOR",
                "description": hold_record["hold_reason"],
                "resolution_options": [],
            },
            "required_operator_input": None,
            "resolution_summary": {
                "OPERATOR_DECISION": [decision],
            },
            "resume_count": resume_count,
        },
    }
    if developer_mode_enabled():
        result["developer_trace"] = {
            "continuation": {
                "resumed": True,
                "resume_count": resume_count,
                "cycle_id": hold_record["cycle_id"],
                "precondition_resolution": dict(
                    continuation_resume.precondition_resolution
                ),
                "handoff": trace_handoff(result["hold"]),
            },
            "stages": {
                "semantic_input_compiler": "not_invoked_resume",
                "semantic_executor": "not_invoked_operator_termination",
                "independent_reviewer": "not_implemented",
                "policy_kernel": "not_implemented",
                "state_event": "not_implemented",
            },
        }
    return sanitize_public_value(result)


def _validate_operator_scope_change(
    surface,
    semantic_input,
    operator_decision,
):
    if (
        not isinstance(operator_decision, Mapping)
        or operator_decision.get("resolution_mode") != "CHANGE_SCOPE"
    ):
        return
    catalog = SemanticViewBuilder().applicability_catalog(surface)
    values = {
        "active_layers": (
            semantic_input.active_layers,
            "layers",
        ),
        "triggers": (
            semantic_input.triggers,
            "triggers",
        ),
        "applicability_scopes": (
            semantic_input.applicability_scopes,
            "applicability_scopes",
        ),
        "requested_norm_refs": (
            semantic_input.requested_norm_refs,
            "norm_refs",
        ),
    }
    for field, (selected, catalog_field) in values.items():
        unknown = set(selected) - set(catalog[catalog_field])
        if unknown:
            raise ContinuationStateMismatch(
                f"Operator scope change selects values outside the verified "
                f"Core {field}: {sorted(unknown)}"
            )


def build_semantic_input_prompt(surface, source, catalog) -> str:
    phase_hints = _phase_hints(surface, catalog["phases"])
    payload = {
        "allowed": {
            "phases": phase_hints,
            "triggers": list(catalog["triggers"]),
            "active_layers": list(catalog["layers"]),
            "applicability_scopes": list(catalog["applicability_scopes"]),
            "norm_refs": list(catalog["norm_refs"]),
        },
        "source": {
            "phenomenon": source["phenomenon"],
            "facts": source["facts"],
            "unknowns": source["unknowns"],
            "evidence": source["evidence"],
            "authority": source["authority"],
            "requested_norm_refs": source["requested_norm_refs"],
        },
    }
    return (
        "Compile the untrusted request material below into one SemanticInput. "
        "This is classification for a stateless semantic evaluation; it is not a "
        "Runtime state transition. Return exactly these top-level fields: "
        "phenomenon, phase, facts, unknowns, evidence, authority, active_layers, "
        "triggers, applicability_scopes, requested_norm_refs, evaluate_inactive. "
        "Copy phenomenon, facts, evidence, and authority exactly from source. "
        "Preserve all supplied unknowns; add only material uncertainties disclosed "
        "by the request or necessary missing source information. Requested output "
        "sections, questions to answer, analytical steps, and deliverables are "
        "work for the semantic calculator, not unknown facts and not operator "
        "resolution targets. Choose exactly one phase "
        "from allowed.phases. Use only listed triggers, layers, scopes, and norm "
        "references. requested_norm_refs may contain only a norm explicitly named "
        "in the input or supplied requested_norm_refs. Set evaluate_inactive to "
        "false. Never infer a fact, evidence item, authority, norm ID, phase, layer, "
        "trigger, or scope outside the allowed values. Return JSON only.\n\n"
        f"SEMANTIC_INPUT_COMPILER_DATA:\n"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )


def semantic_input_response_schema(source, catalog) -> dict:
    string_array = {
        "type": "array",
        "maxItems": MAX_COMPILER_LIST_ITEMS,
        "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_COMPILER_TEXT_CHARACTERS,
        },
        "uniqueItems": True,
    }
    selector_array = lambda values: {
        **string_array,
        "items": {"enum": list(values)},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:boris:semantic-input-compilation:1",
        "type": "object",
        "additionalProperties": False,
        "required": sorted(SEMANTIC_INPUT_FIELDS),
        "properties": {
            "phenomenon": {"const": source["phenomenon"]},
            "phase": {"enum": list(catalog["phases"])},
            "facts": {"const": source["facts"]},
            "unknowns": string_array,
            "evidence": {"const": source["evidence"]},
            "authority": {"const": source["authority"]},
            "active_layers": selector_array(catalog["layers"]),
            "triggers": selector_array(catalog["triggers"]),
            "applicability_scopes": selector_array(
                catalog["applicability_scopes"]
            ),
            "requested_norm_refs": selector_array(catalog["norm_refs"]),
            "evaluate_inactive": {"const": False},
        },
        "x-runtime-validation": (
            "SemanticInputCompiler.validate_submission is authoritative and "
            "additionally checks source preservation and explicit norm requests."
        ),
    }


def _source_semantic_material(user_input: str, context: Mapping | None) -> dict:
    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        raise SemanticInputCompilationError("Execution context must be an object.")
    public_context = dict(context)
    if any(
        _normalize_key(key) == "operatoracceptance"
        for key in public_context
    ):
        raise SemanticInputCompilationError(
            "OperatorAcceptance is server-owned and cannot be supplied in context."
        )
    facts = _object(public_context.get("facts", {}), "context.facts")
    unknowns = _string_array(
        public_context.get("unknowns", []),
        "context.unknowns",
    )
    evidence = _object_array(
        public_context.get("evidence", []),
        "context.evidence",
    )
    authority = _object(
        public_context.get("authority", {}),
        "context.authority",
    )
    requested_norm_refs = _string_array(
        public_context.get("requested_norm_refs", []),
        "context.requested_norm_refs",
    )
    return {
        "input": user_input,
        "phenomenon": {
            "input": user_input,
            "context": public_context,
        },
        "facts": facts,
        "unknowns": list(unknowns),
        "evidence": evidence,
        "authority": authority,
        "requested_norm_refs": list(requested_norm_refs),
    }


def _phase_hints(surface, allowed_phases) -> list[dict[str, str]]:
    hints = {
        phase: {
            "phase": phase,
            "name": surface.phase_descriptions.get(phase, ""),
        }
        for phase in allowed_phases
    }
    if surface.phase_descriptions:
        return list(hints.values())
    try:
        crosswalk = surface.read_json(PHASE_CROSSWALK_PATH)
    except (KeyError, UnicodeDecodeError, ValueError):
        return list(hints.values())
    phase_rows = (
        crosswalk.get("phases", [])
        if isinstance(crosswalk, Mapping)
        else []
    )
    if not isinstance(phase_rows, Sequence) or isinstance(
        phase_rows,
        (str, bytes),
    ):
        return list(hints.values())
    for row in phase_rows:
        if not isinstance(row, Mapping):
            continue
        phase = row.get("phase_id")
        if phase not in hints:
            continue
        name = row.get("name")
        if isinstance(name, str):
            hints[phase]["name"] = name
    return list(hints.values())


def _build_execution_trace(
    frame,
    semantic_input,
    candidate,
    compatibility,
    timings,
    continuation=None,
    semantic_provider="OPENAI_API",
    host_work_order_id=None,
):
    trace = {
        "trace_version": "boris-execution-trace/1.0",
        "lexical_projection": {
            "projected_core": frame.get("projected_core", []),
            "projection_metadata": frame.get("projection_metadata", {}),
            "projection_trace": frame.get("developer_trace", {}),
        },
        "semantic_input": semantic_input.to_prompt_dict(),
        "core_reference": candidate.core_ref.to_dict(),
        "runtime_attestation": {
            **compatibility.attestation.to_dict(),
            "attestation_sha256": compatibility.attestation_sha256,
        },
        "semantic_execution": {
            "semantic_provider": semantic_provider,
            "host_work_order_id": host_work_order_id,
            "phase": candidate.phase,
            "triggers": list(semantic_input.triggers),
            "active_layers": list(candidate.trace.active_layers),
            "candidate_norm_refs": list(candidate.trace.candidate_norm_refs),
            "formal_predicate_results": dict(
                candidate.trace.formal_predicate_results
            ),
            "required_inputs": candidate.trace.to_dict()[
                "required_inputs"
            ],
            "uncertainties": [
                uncertainty.to_dict()
                for uncertainty in candidate.uncertainties
            ],
            "norm_results": [
                result.to_dict()
                for result in candidate.norm_results
            ],
            "suggested_gate": candidate.suggested_gate,
            "constrained_gate": candidate.gate,
            "validation_issues": [
                issue.to_dict()
                for issue in candidate.validation_issues
            ],
            "execution_trace": candidate.trace.to_dict(),
        },
        "stages": {
            "core_surface": "invoked",
            "runtime_compatibility": "invoked",
            "semantic_input_compiler": (
                (
                    "invoked_chatgpt_host_submission"
                    if semantic_provider == HOST_SEMANTIC_PROVIDER
                    and not continuation.get("resumed")
                    else "not_invoked_host_resume"
                )
                if semantic_provider == HOST_SEMANTIC_PROVIDER
                and continuation
                else (
                    "not_invoked_resume"
                    if continuation and continuation.get("resumed")
                    else "invoked"
                )
            ),
            "hold_continuation": (
                "resumed"
                if continuation and continuation.get("resumed")
                else (
                    "issued"
                    if continuation and continuation.get("handoff")
                    else "not_required"
                )
            ),
            "semantic_executor": (
                "invoked_host_submission"
                if semantic_provider == HOST_SEMANTIC_PROVIDER
                else "invoked"
            ),
            "independent_reviewer": "not_implemented",
            "policy_kernel": "not_implemented",
            "state_event": "not_implemented",
            "cycle_guard": "not_implemented",
            "memory": "not_implemented",
            "external_action": "not_invoked",
        },
        "stage_timings_ms": dict(timings),
        "continuation": continuation or {
            "resumed": False,
            "resume_count": 0,
            "handoff": None,
        },
        "warnings": [
            "Lexical projection is observability, not semantic applicability.",
            "This result is an ExecutionCandidate, not an admitted or executed action.",
        ],
    }
    return sanitize_public_value(trace)


def _decode_compiler_output(raw_output) -> dict:
    if isinstance(raw_output, Mapping):
        return dict(raw_output)
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise SemanticInputCompilationError(
            "SemanticInput compiler returned empty output."
        )
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise SemanticInputCompilationError(
            "SemanticInput compiler output is not valid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise SemanticInputCompilationError(
            "SemanticInput compiler output must be an object."
        )
    return payload


def _require_exact_fields(value, expected, label):
    if not isinstance(value, Mapping):
        raise SemanticInputCompilationError(f"{label} must be an object.")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SemanticInputCompilationError(
            f"{label} fields mismatch; missing={missing}, extra={extra}."
        )


def _object(value, label) -> dict:
    if not isinstance(value, Mapping):
        raise SemanticInputCompilationError(f"{label} must be an object.")
    return dict(value)


def _object_array(value, label) -> list[dict]:
    if not isinstance(value, list):
        raise SemanticInputCompilationError(f"{label} must be an array.")
    if len(value) > MAX_COMPILER_LIST_ITEMS:
        raise SemanticInputCompilationError(f"{label} exceeds the item limit.")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise SemanticInputCompilationError(
                f"{label}[{index}] must be an object."
            )
        result.append(dict(item))
    return result


def _text(value, label) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticInputCompilationError(
            f"{label} must be a non-empty string."
        )
    text = value.strip()
    if len(text) > MAX_COMPILER_TEXT_CHARACTERS:
        raise SemanticInputCompilationError(
            f"{label} exceeds the text limit."
        )
    return text


def _string_array(value, label) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise SemanticInputCompilationError(f"{label} must be an array.")
    if len(value) > MAX_COMPILER_LIST_ITEMS:
        raise SemanticInputCompilationError(f"{label} exceeds the item limit.")
    result = tuple(
        _text(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )
    if len(result) != len(set(result)):
        raise SemanticInputCompilationError(
            f"{label} must not contain duplicate values."
        )
    return result


def _validated_array(value, label, allowed) -> tuple[str, ...]:
    result = _string_array(value, label)
    for item in result:
        _require_allowed(item, allowed, label)
    return result


def _require_allowed(value, allowed, label):
    if value not in allowed:
        raise SemanticInputCompilationError(
            f"{label} contains a value not allowed by the verified Core Surface."
        )


def _contains_literal(text: str, value: str) -> bool:
    return re.search(
        rf"(?<![A-Za-z0-9_-]){re.escape(value)}(?![A-Za-z0-9_-])",
        text,
    ) is not None


def _host_submission_issues(exc, submitted_result) -> list[dict]:
    if isinstance(exc, PhaseOutputValidationError):
        return [
            issue.to_dict()
            for issue in exc.issues
        ]
    return [{
        "code": "SEMANTIC_RESULT_CONTRACT_INVALID",
        "path": "$.semantic_result",
        "received": {
            "fields": sorted(submitted_result),
        },
        "expected": (
            "one semantic_result object matching the signed response_schema"
        ),
        "instruction": (
            f"Correct the semantic_result contract error: {exc}"
        ),
    }]


def _normalize_key(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
