import json
from dataclasses import replace

import pytest

from core_surface import NormRecord
from application.continuation import (
    ContinuationStateMismatch,
    IncompleteOperatorResolution,
    InvalidContinuationToken,
)
from application.execution import (
    ExecutionService,
    OperatorAcceptanceProvider,
    OperatorAcceptanceUnavailable,
    SemanticInputCompilationError,
    SemanticInputCompiler,
)
from tests.test_semantic_executor import (
    AutoCalculator,
    build_accepted_compatibility,
    build_surface,
    uncertainty,
)


class StaticSurfaceProvider:
    def __init__(self, surface, events=None):
        self.surface = surface
        self.events = events if events is not None else []

    def get(self):
        self.events.append("core_surface")
        return self.surface


class StaticAcceptanceProvider:
    def __init__(self, acceptance, events=None, error=None):
        self.acceptance = acceptance
        self.events = events if events is not None else []
        self.error = error

    def get(self, surface):
        self.events.append("operator_acceptance")
        if self.error:
            raise self.error
        return self.acceptance


class StaticCompatibilityVerifier:
    def __init__(self, compatibility, events=None):
        self.compatibility = compatibility
        self.events = events if events is not None else []

    def verify(self, surface, operator_acceptance=None):
        self.events.append("runtime_compatibility")
        assert operator_acceptance == self.compatibility.operator_acceptance
        return self.compatibility


class CompilerAdapter:
    def __init__(self, output, events=None):
        self.output = output
        self.events = events if events is not None else []
        self.calls = []

    def call_structured(self, prompt, system_message):
        self.events.append("semantic_input_compiler")
        self.calls.append((prompt, system_message))
        return json.dumps(self.output)


class RecordingCalculator(AutoCalculator):
    def __init__(self, events=None, **kwargs):
        super().__init__(**kwargs)
        self.events = events if events is not None else []

    def calculate(self, view, semantic_input):
        self.events.append("semantic_executor")
        return super().calculate(view, semantic_input)


def test_execution_service_runs_one_semantic_candidate_route(monkeypatch):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    service, adapter, calculator, events = build_service(
        compiler_payload("Explain the runtime."),
    )

    result = service.execute(
        "Explain the runtime.",
        session_id="execution-test",
    )

    assert result == {
        "execution_version": "boris-execution/1.0",
        "session_id": "execution-test",
        "status": "semantic_candidate",
        "phase": "C03",
        "gate": "PASS",
        "candidate_result": {"status": "CANDIDATE_ONLY"},
        "norm_results": [
            {
                "norm_ref": "N-STAR",
                "layer": "BASE",
                "operation": "REQUIRE",
                "predicate_result": "TRUE",
                "applicability": "TRUE",
                "reason": "Calculated N-STAR.",
                "unknowns": [],
            }
        ],
        "unknowns": [],
        "uncertainties": [],
        "conflicts": [],
        "alternatives": [],
        "limitations": [
            "not_independently_reviewed",
            "not_policy_admitted",
            "no_state_mutation",
            "no_external_action",
        ],
    }
    assert events == [
        "core_surface",
        "operator_acceptance",
        "runtime_compatibility",
        "semantic_input_compiler",
        "semantic_executor",
    ]
    assert len(adapter.calls) == 1
    assert calculator.calls == 1


def test_hold_returns_signed_operator_handoff_and_no_empty_candidate(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "h" * 32)
    text = "Evaluate an action."
    service, _adapter, calculator, _events = build_service(
        compiler_payload(text, triggers=["action"]),
    )
    calculator.mutate = lambda payload, _view: payload.update(
        candidate_result={}
    )

    result = service.execute(text, session_id="hold-handoff")

    assert result["gate"] == "HOLD"
    assert result["candidate_result"] is None
    assert result["candidate_unavailable_reason"]
    assert result["hold"]["handoff_version"] == (
        "boris-hold-handoff/1.3"
    )
    assert result["hold"]["status"] == "operator_input_required"
    assert result["hold"]["continuation_token"].startswith("v1.")
    assert result["hold"]["expires_at"]
    assert set(result["hold"]["hold_record"]) == {
        "cycle_id",
        "return_state",
        "return_gate",
        "hold_reason",
        "scope",
        "source_refs",
        "unknowns",
        "evidence_refs",
        "open_debts",
        "state_hash",
    }
    assert result["hold"]["hold_record"]["return_state"] == "C03"
    assert result["hold"]["hold_record"]["return_gate"] == "C03"
    assert result["hold"]["blocking_precondition"][
        "resolution_options"
    ] == ["PROVIDE_INFORMATION"]
    required = result["hold"]["required_operator_input"]
    assert required["semantic_unknowns"] == []
    assert required["predicate_inputs"] == [
        {
            "input_id": "authorization.granted",
            "target_path": "authorization.granted",
            "resolution_kind": "operator_observation",
            "expected_type": "boolean",
            "norm_refs": ["N-ACTION"],
            "constraints": [
                {
                    "operator": "fact",
                    "path_role": "path",
                    "expected": True,
                }
            ],
            "uncertainty_ids": ["authorization.granted"],
            "uncertainty_descriptions": [
                "authorization.granted remains unknown."
            ],
            "question": (
                "Provide the observed value for Core selector "
                "authorization.granted. The value that makes a predicate "
                "true is not assumed."
            ),
        }
    ]
    assert "authorization.granted = true" not in required["question"]


def test_hold_maps_semantic_unknown_path_without_conflating_predicate_input(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "u" * 32)
    text = "Evaluate an action."
    surface = build_surface()
    action = surface.get_norm("N-ACTION")
    action_fields = dict(action.fields)
    action_fields["predicate"] = "authorization.status"
    action_fields["when"] = json.dumps({
        "op": "fact",
        "path": "violation.N-GEN-001",
        "equals": True,
    }, separators=(",", ":"))
    updated_action = NormRecord(
        norm_id=action.norm_id,
        layer=action.layer,
        norm_type=action.norm_type,
        fields=action_fields,
    )
    updated_base = tuple(
        updated_action if item.norm_id == action.norm_id else item
        for item in surface.norms_for_layer("BASE")
    )
    surface = replace(
        surface,
        norms_by_layer={
            **dict(surface.norms_by_layer),
            "BASE": updated_base,
        },
        _norm_index={
            **dict(surface._norm_index),
            action.norm_id: updated_action,
        },
    )
    service, _adapter, calculator, _events = build_service(
        compiler_payload(text, triggers=["action"]),
        surface=surface,
    )
    calculator.result_unknowns = {
        "N-ACTION": ["authorization.status remains unknown."],
    }
    calculator.uncertainties = [
        uncertainty(
            "authorization.status remains unknown.",
            resolution_class="OPERATOR_INPUT",
            target_path="authorization.status",
            norm_refs=("N-ACTION",),
            operator_question=(
                "Provide the operator-confirmed value for "
                "authorization.status."
            ),
            uncertainty_id="authorization.status",
        )
    ]

    result = service.execute(text, session_id="path-aware-handoff")

    required = result["hold"]["required_operator_input"]
    assert required["semantic_unknowns"] == [
        {
            "unknown_id": "authorization.status",
            "description": "authorization.status remains unknown.",
            "target_path": "authorization.status",
            "resolution_kind": "operator_value",
            "expected_type": "json",
            "norm_refs": ["N-ACTION"],
            "core_refs": [],
            "question": (
                "Provide the operator-confirmed value for "
                "authorization.status."
            ),
        }
    ]
    assert required["predicate_inputs"] == []
    assert all(
        "UNKNOWN formal predicate" not in item["description"]
        for item in required["semantic_unknowns"]
    )


def test_non_operator_hold_keeps_conditional_candidate_without_continuation(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    monkeypatch.delenv("BORIS_CONTINUATION_SECRET", raising=False)
    description = "The result depends on a future event."
    service, _adapter, calculator, _events = build_service(
        compiler_payload("Evaluate a conditional route."),
    )
    calculator.suggested_gate = "HOLD"
    calculator.unknowns = [description]
    calculator.uncertainties = [
        uncertainty(
            description,
            resolution_class="FUTURE_CONTINGENT",
            uncertainty_id="future-event",
        )
    ]

    result = service.execute(
        "Evaluate a conditional route.",
        session_id="bounded-hold",
    )

    assert result["gate"] == "HOLD"
    assert result["candidate_result"] == {
        "status": "CANDIDATE_ONLY"
    }
    assert result["hold"]["status"] == (
        "resolution_not_operator_owned"
    )
    assert result["hold"]["required_operator_input"] is None
    assert "continuation_token" not in result["hold"]
    assert result["hold"]["resolution_summary"][
        "FUTURE_CONTINGENT"
    ][0]["uncertainty_id"] == "future-event"


def test_resume_reuses_signed_semantic_input_and_closes_formal_unknown(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "dev")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "r" * 32)
    text = "Evaluate an action."
    context = {
        "unknowns": ["authorization.granted remains unknown."],
    }
    service, adapter, calculator, events = build_service(
        compiler_payload(text, context, triggers=["action"]),
    )

    first = service.execute(
        text,
        session_id="resume-route",
        context=context,
    )
    semantic_unknowns = first["hold"][
        "required_operator_input"
    ]["semantic_unknowns"]
    assert semantic_unknowns == []
    second = service.execute(
        session_id="resume-route",
        resume={
            "continuation_token": first["hold"]["continuation_token"],
            "operator_input": {
                "resolution_mode": "PROVIDE_INFORMATION",
                "statement": "I authorize this semantic evaluation.",
                "values": {"authorization.granted": True},
                "resolved_unknowns": [],
            },
        },
    )

    assert first["gate"] == "HOLD"
    assert second["gate"] == "PASS"
    assert second["candidate_result"] == {"status": "CANDIDATE_ONLY"}
    assert "hold" not in second
    assert len(adapter.calls) == 1
    assert calculator.calls == 2
    assert events.count("semantic_input_compiler") == 1
    assert calculator.last_view.get_candidate(
        "N-ACTION"
    ).formal_predicate_result == "TRUE"
    trace = second["developer_trace"]
    assert trace["continuation"]["resumed"] is True
    assert trace["continuation"]["resume_count"] == 1
    assert trace["stages"]["semantic_input_compiler"] == (
        "not_invoked_resume"
    )
    assert (
        "continuation_token"
        not in json.dumps(trace, ensure_ascii=False)
    )


def test_resume_projects_non_hold_candidate_when_calculator_returns_empty(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "dev")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "p" * 32)
    text = "Evaluate an action."
    context = {
        "unknowns": ["authorization.granted remains unknown."],
    }
    service, adapter, calculator, events = build_service(
        compiler_payload(text, context, triggers=["action"]),
    )
    calculator.mutate = lambda payload, _view: payload.update(
        candidate_result={}
    )

    first = service.execute(
        text,
        session_id="projected-resume-route",
        context=context,
    )
    second = service.execute(
        session_id="projected-resume-route",
        resume={
            "continuation_token": first["hold"]["continuation_token"],
            "operator_input": {
                "resolution_mode": "PROVIDE_INFORMATION",
                "statement": "I authorize this semantic evaluation.",
                "values": {"authorization.granted": True},
                "resolved_unknowns": [],
            },
        },
    )

    assert first["gate"] == "HOLD"
    assert first["candidate_result"] is None
    assert second["gate"] == "PASS"
    assert second["candidate_result"]["status"] == "CANDIDATE_ONLY"
    assert second["candidate_result"]["projection_version"] == (
        "boris-candidate-projection/1.0"
    )
    assert second["candidate_result"]["gate"] == "PASS"
    assert "hold" not in second
    assert len(adapter.calls) == 1
    assert calculator.calls == 2
    assert events.count("semantic_input_compiler") == 1
    assert {
        issue["code"]
        for issue in second["developer_trace"]["semantic_execution"][
            "validation_issues"
        ]
    } >= {"CANDIDATE_RESULT_PROJECTED"}


def test_resume_requires_every_signed_hold_target_before_recalculation(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "c" * 32)
    text = "Evaluate an action."
    service, _adapter, calculator, _events = build_service(
        compiler_payload(text, triggers=["action"]),
    )
    first = service.execute(text, session_id="incomplete-resolution")

    with pytest.raises(
        IncompleteOperatorResolution,
        match="does not close every signed HOLD target",
    ):
        service.execute(
            session_id="incomplete-resolution",
            resume={
                "continuation_token": first["hold"][
                    "continuation_token"
                ],
                "operator_input": {
                    "resolution_mode": "PROVIDE_INFORMATION",
                    "statement": "Continue.",
                    "values": {},
                    "resolved_unknowns": [],
                },
            },
        )

    assert calculator.calls == 1


def test_conditional_resume_preserves_unknowns_and_rechecks_same_phase(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "dev")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "b" * 32)
    text = "Evaluate a bounded policy question."
    description = "A material historical fact is not available."
    context = {"unknowns": [description]}
    service, _adapter, calculator, _events = build_service(
        compiler_payload(text, context),
    )

    def classify_uncertainty(_view, semantic_input):
        conditionally_bounded = any(
            item.get("kind") == "hold_precondition_resolution"
            for item in semantic_input.evidence
        )
        if conditionally_bounded:
            return [
                uncertainty(
                    description,
                    resolution_class="UNRESOLVABLE_LIMITATION",
                    uncertainty_id="historical-fact",
                )
            ]
        return [
            uncertainty(
                description,
                resolution_class="OPERATOR_INPUT",
                operator_question=(
                    "Provide the historical fact if it is available."
                ),
                uncertainty_id="historical-fact",
            )
        ]

    calculator.uncertainties = classify_uncertainty
    first = service.execute(
        text,
        session_id="conditional-resume",
        context=context,
    )

    assert first["gate"] == "HOLD"
    assert first["hold"]["blocking_precondition"][
        "resolution_options"
    ] == [
        "PROVIDE_INFORMATION",
        "ALLOW_CONDITIONAL_PROCEEDING",
    ]
    first_record = first["hold"]["hold_record"]

    second = service.execute(
        session_id="conditional-resume",
        resume={
            "continuation_token": first["hold"]["continuation_token"],
            "operator_input": {
                "resolution_mode": "ALLOW_CONDITIONAL_PROCEEDING",
                "statement": (
                    "Recalculate conditionally and preserve the missing fact "
                    "as a limitation."
                ),
                "values": {},
                "resolved_unknowns": [],
            },
        },
    )

    assert second["gate"] == "PASS"
    assert second["phase"] == first_record["return_state"] == "C03"
    assert second["unknowns"] == [description]
    semantic_input = second["developer_trace"]["semantic_input"]
    assert semantic_input["unknowns"] == [description]
    assert semantic_input["facts"] == {}
    assert semantic_input["authority"] == {}
    decision = semantic_input["evidence"][-1]
    assert decision["kind"] == "hold_precondition_resolution"
    assert decision["resolution_mode"] == (
        "ALLOW_CONDITIONAL_PROCEEDING"
    )
    assert decision["does_not_establish_facts"] is True
    continuation = second["developer_trace"]["continuation"]
    assert continuation["cycle_id"] == first_record["cycle_id"]
    assert continuation["precondition_resolution"][
        "gate_recheck_required"
    ] is True
    assert continuation["precondition_resolution"][
        "gate_forced"
    ] is False


def test_conditional_resume_cannot_bypass_predicate_input(monkeypatch):
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "d" * 32)
    text = "Evaluate an action."
    service, _adapter, calculator, _events = build_service(
        compiler_payload(text, triggers=["action"]),
    )
    first = service.execute(text, session_id="conditional-blocked")

    with pytest.raises(
        IncompleteOperatorResolution,
        match="is not available",
    ):
        service.execute(
            session_id="conditional-blocked",
            resume={
                "continuation_token": first["hold"][
                    "continuation_token"
                ],
                "operator_input": {
                    "resolution_mode": (
                        "ALLOW_CONDITIONAL_PROCEEDING"
                    ),
                    "statement": "Proceed without authorization.",
                    "values": {},
                    "resolved_unknowns": [],
                },
            },
        )

    assert calculator.calls == 1


def test_resume_rejects_tampered_token(monkeypatch):
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "t" * 32)
    text = "Evaluate an action."
    service, _adapter, _calculator, _events = build_service(
        compiler_payload(text, triggers=["action"]),
    )
    first = service.execute(text, session_id="tamper-route")
    token = first["hold"]["continuation_token"]
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(InvalidContinuationToken):
        service.execute(
            session_id="tamper-route",
            resume={
                "continuation_token": token[:-1] + replacement,
                "operator_input": {
                    "resolution_mode": "PROVIDE_INFORMATION",
                    "statement": "Continue.",
                    "values": {},
                    "resolved_unknowns": [],
                },
            },
        )


def test_resume_is_bound_to_signed_session(monkeypatch):
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "s" * 32)
    text = "Evaluate an action."
    service, _adapter, _calculator, _events = build_service(
        compiler_payload(text, triggers=["action"]),
    )
    first = service.execute(text, session_id="signed-session")

    with pytest.raises(
        ContinuationStateMismatch,
        match="session_id",
    ):
        service.execute(
            session_id="different-session",
            resume={
                "continuation_token": first["hold"][
                    "continuation_token"
                ],
                "operator_input": {
                    "resolution_mode": "PROVIDE_INFORMATION",
                    "statement": "Continue.",
                    "values": {},
                    "resolved_unknowns": [],
                },
            },
        )


def test_compatibility_is_required_before_any_semantic_llm_call():
    surface = build_surface()
    compatibility = build_accepted_compatibility(surface)
    events = []
    adapter = CompilerAdapter(
        compiler_payload("Must not compile."),
        events,
    )
    service = ExecutionService(
        surface_provider=StaticSurfaceProvider(surface, events),
        acceptance_provider=StaticAcceptanceProvider(
            compatibility.operator_acceptance,
            events,
            error=OperatorAcceptanceUnavailable(
                "Server OperatorAcceptance is not configured."
            ),
        ),
        compatibility_verifier=StaticCompatibilityVerifier(
            compatibility,
            events,
        ),
        llm_adapter_factory=lambda: adapter,
    )

    with pytest.raises(OperatorAcceptanceUnavailable):
        service.execute("Must not compile.")

    assert events == ["core_surface", "operator_acceptance"]
    assert adapter.calls == []


def test_operator_acceptance_provider_rejects_wrong_archive_identity():
    surface = build_surface()
    acceptance = build_accepted_compatibility(surface).operator_acceptance
    mismatched = replace(acceptance, archive_sha256="f" * 64)

    with pytest.raises(
        OperatorAcceptanceUnavailable,
        match="does not match the loaded Core source",
    ):
        OperatorAcceptanceProvider(acceptance=mismatched).get(surface)


def test_configured_core_repository_is_accepted_without_sidecar_file(
    monkeypatch,
):
    monkeypatch.delenv("BORIS_OPERATOR_ACCEPTANCE_FILE", raising=False)
    surface = replace(
        build_surface(),
        source="/opt/boris-core",
        source_kind="directory",
        archive_sha256=None,
    )

    acceptance = OperatorAcceptanceProvider().get(surface)

    assert acceptance.package_id == surface.package_id
    assert acceptance.artifact_version == surface.artifact_version
    assert acceptance.archive_sha256 == ""
    assert acceptance.manifest_sha256 == surface.manifest_sha256
    assert acceptance.operator_role == "RUNTIME_CONFIGURED_CORE_REPOSITORY"
    assert acceptance.decision == "ACCEPT"
    assert acceptance.accepted_scope == ("semantic_evaluation",)


def test_archive_source_still_requires_explicit_operator_acceptance(monkeypatch):
    monkeypatch.delenv("BORIS_OPERATOR_ACCEPTANCE_FILE", raising=False)

    with pytest.raises(
        OperatorAcceptanceUnavailable,
        match="not configured for the archive Core source",
    ):
        OperatorAcceptanceProvider().get(build_surface())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase", "C99"),
        ("triggers", ["invented-trigger"]),
        ("active_layers", ["INVENTED_LAYER"]),
        ("applicability_scopes", ["C99"]),
        ("requested_norm_refs", ["N-INVENTED"]),
    ],
)
def test_compiler_rejects_selector_values_outside_verified_core(
    field,
    value,
):
    surface = build_surface()
    payload = compiler_payload("Classify this request.")
    payload[field] = value
    compiler = SemanticInputCompiler(CompilerAdapter(payload))

    with pytest.raises(
        SemanticInputCompilationError,
        match="not allowed by the verified Core Surface",
    ):
        compiler.compile(surface, "Classify this request.")


def test_compiler_rejects_known_norm_not_explicitly_named():
    surface = build_surface()
    payload = compiler_payload("Classify this request.")
    payload["requested_norm_refs"] = ["N-ACTION"]

    with pytest.raises(
        SemanticInputCompilationError,
        match="only when the request names it explicitly",
    ):
        SemanticInputCompiler(CompilerAdapter(payload)).compile(
            surface,
            "Classify this request.",
        )


def test_compiler_cannot_invent_facts_evidence_or_authority():
    surface = build_surface()
    payload = compiler_payload("Classify this request.")
    payload["facts"] = {"invented": True}

    with pytest.raises(
        SemanticInputCompilationError,
        match="must not add, remove, or change supplied facts",
    ):
        SemanticInputCompiler(CompilerAdapter(payload)).compile(
            surface,
            "Classify this request.",
        )


def test_operator_acceptance_cannot_enter_through_request_context():
    surface = build_surface()
    adapter = CompilerAdapter(compiler_payload("Classify this request."))
    compiler = SemanticInputCompiler(adapter)

    with pytest.raises(
        SemanticInputCompilationError,
        match="server-owned",
    ):
        compiler.compile(
            surface,
            "Classify this request.",
            context={"operator_acceptance": {"decision": "ACCEPT"}},
        )

    assert adapter.calls == []


def test_lexical_projection_does_not_become_requested_norm_refs(monkeypatch):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "dev")
    text = "Inspect Formulation for N-ACTION."
    service, _adapter, calculator, _events = build_service(
        compiler_payload(text),
    )

    result = service.execute(
        text,
        session_id="projection-separation",
    )

    selected_projection_ids = {
        item["object_id"]
        for item in result["developer_trace"]["lexical_projection"][
            "projection_trace"
        ]["selected_objects"]
    }
    semantic_refs = set(
        result["developer_trace"]["semantic_execution"][
            "candidate_norm_refs"
        ]
    )
    assert "N-ACTION" in selected_projection_ids
    assert "N-ACTION" not in semantic_refs
    assert calculator.last_view.selection_trace["requested_norm_refs"] == ()


def test_developer_runtime_mode_adds_safe_combined_trace_only(monkeypatch):
    text = "Explain the runtime."
    production, _adapter, _calculator, _events = build_service(
        compiler_payload(text),
    )
    developer, _adapter, _calculator, _events = build_service(
        compiler_payload(text),
    )

    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    production_result = production.execute(
        text,
        session_id="same",
    )
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "dev")
    developer_result = developer.execute(
        text,
        session_id="same",
    )

    assert "developer_trace" not in production_result
    candidate_without_trace = {
        key: value
        for key, value in developer_result.items()
        if key != "developer_trace"
    }
    assert candidate_without_trace == production_result
    trace = developer_result["developer_trace"]
    assert trace["trace_version"] == "boris-execution-trace/1.0"
    assert trace["semantic_input"]["phase"] == "C03"
    assert trace["core_reference"]["archive_sha256"] == "a" * 64
    assert trace["runtime_attestation"]["activation_status"] == (
        "ACCEPTED_IN_SCOPE"
    )
    assert trace["semantic_execution"]["suggested_gate"] == "PASS"
    assert trace["semantic_execution"]["constrained_gate"] == "PASS"
    assert trace["stages"]["independent_reviewer"] == "not_implemented"
    assert trace["stages"]["policy_kernel"] == "not_implemented"
    assert trace["stages"]["external_action"] == "not_invoked"
    assert set(trace["stage_timings_ms"]) >= {
        "core_surface_load",
        "operator_acceptance_load",
        "runtime_compatibility",
        "semantic_input_compile",
        "semantic_executor",
        "context_projection",
        "total",
    }
    serialized = json.dumps(trace)
    assert "SEMANTIC_INPUT_COMPILER_DATA" not in serialized
    assert "Return only the Phase 4F" not in serialized


def build_service(compiler_output, surface=None):
    surface = surface or build_surface()
    compatibility = build_accepted_compatibility(surface)
    events = []
    adapter = CompilerAdapter(compiler_output, events)
    calculator = RecordingCalculator(events)
    if "action" in compiler_output.get("triggers", []):
        calculator.uncertainties = _authorization_uncertainties
    service = ExecutionService(
        surface_provider=StaticSurfaceProvider(surface, events),
        acceptance_provider=StaticAcceptanceProvider(
            compatibility.operator_acceptance,
            events,
        ),
        compatibility_verifier=StaticCompatibilityVerifier(
            compatibility,
            events,
        ),
        llm_adapter_factory=lambda: adapter,
        calculator_factory=lambda _adapter: calculator,
    )
    return service, adapter, calculator, events


def _authorization_uncertainties(view, _semantic_input):
    try:
        candidate = view.get_candidate("N-ACTION")
    except KeyError:
        return []
    if candidate.formal_predicate_result != "UNKNOWN":
        return []
    return [
        uncertainty(
            "authorization.granted remains unknown.",
            resolution_class="OPERATOR_INPUT",
            target_path="authorization.granted",
            norm_refs=("N-ACTION",),
            operator_question=(
                "Provide the observed authorization decision."
            ),
            uncertainty_id="authorization.granted",
        )
    ]


def compiler_payload(
    user_input,
    context=None,
    *,
    phase="C03",
    triggers=None,
):
    context = dict(context or {})
    return {
        "phenomenon": {
            "input": user_input,
            "context": context,
        },
        "phase": phase,
        "facts": dict(context.get("facts", {})),
        "unknowns": list(context.get("unknowns", [])),
        "evidence": list(context.get("evidence", [])),
        "authority": dict(context.get("authority", {})),
        "active_layers": [],
        "triggers": list(triggers or []),
        "applicability_scopes": [],
        "requested_norm_refs": list(
            context.get("requested_norm_refs", [])
        ),
        "evaluate_inactive": False,
    }
