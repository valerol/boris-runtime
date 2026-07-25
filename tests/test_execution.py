import json
from dataclasses import replace

import pytest

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


def test_execution_service_runs_one_semantic_candidate_route():
    service, adapter, calculator, events = build_service(
        compiler_payload("Explain the runtime."),
    )

    result = service.execute(
        "Explain the runtime.",
        session_id="execution-test",
        mode="production",
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
        match="does not match the loaded Core archive",
    ):
        OperatorAcceptanceProvider(acceptance=mismatched).get(surface)


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


def test_lexical_projection_does_not_become_requested_norm_refs():
    text = "Inspect Formulation for N-ACTION."
    service, _adapter, calculator, _events = build_service(
        compiler_payload(text),
    )

    result = service.execute(
        text,
        session_id="projection-separation",
        mode="developer",
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


def test_developer_mode_adds_safe_combined_trace_only():
    text = "Explain the runtime."
    production, _adapter, _calculator, _events = build_service(
        compiler_payload(text),
    )
    developer, _adapter, _calculator, _events = build_service(
        compiler_payload(text),
    )

    production_result = production.execute(
        text,
        session_id="same",
        mode="production",
    )
    developer_result = developer.execute(
        text,
        session_id="same",
        mode="developer",
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


def build_service(compiler_output):
    surface = build_surface()
    compatibility = build_accepted_compatibility(surface)
    events = []
    adapter = CompilerAdapter(compiler_output, events)
    calculator = RecordingCalculator(events)
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
