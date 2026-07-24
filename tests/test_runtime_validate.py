import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_RUNTIME_PREFIXES = ("api", "application", "core_surface", "llm")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _matches_active_runtime(module_name):
    return module_name in ACTIVE_RUNTIME_PREFIXES or module_name.startswith(
        tuple(f"{prefix}." for prefix in ACTIVE_RUNTIME_PREFIXES)
    )


def active_module(module_name):
    if str(PROJECT_ROOT) in sys.path:
        sys.path.remove(str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    for name in list(sys.modules):
        if _matches_active_runtime(name):
            sys.modules.pop(name, None)
    return importlib.import_module(module_name)


@pytest.fixture
def api_context():
    saved_path = list(sys.path)
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if _matches_active_runtime(name)
    }

    if str(PROJECT_ROOT) in sys.path:
        sys.path.remove(str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))

    for module_name in list(sys.modules):
        if _matches_active_runtime(module_name):
            sys.modules.pop(module_name, None)

    from api.app import app

    try:
        yield app, _StatelessApplication()
    finally:
        for module_name in list(sys.modules):
            if _matches_active_runtime(module_name):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))


class _StatelessApplication:
    _handles = {}

    def clear(self):
        return None

    def get(self, _session_id):
        return None


class ForbiddenAdapterFactory:
    def __call__(self):
        raise AssertionError("deterministic validation must not construct a validator LLM")


class FakeSemanticAdapter:
    adapter_name = "fake-semantic"

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def call(self, prompt):
        self.calls.append(prompt)
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload)


def test_runtime_validate_default_deterministic_is_stateless(api_context, monkeypatch):
    app, runtime_registry = api_context
    runtime_registry.clear()
    monkeypatch.delenv("BOIS_LLM", raising=False)
    monkeypatch.delenv("BORIS_VALIDATOR_LLM", raising=False)
    client = TestClient(app)

    response = client.post(
        "/runtime/validate",
        json={
            "answer": "BOIS Runtime validates a context-provider answer.",
            "context_packet": valid_packet(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validation_version"] == "boris-validation/1.0"
    assert body["validation_mode"] == "deterministic"
    assert body["verdict"] == "PASS"
    assert body["llm_called"] is False
    assert body["preflight"]["status"] == "completed"
    assert body["deterministic"]["status"] == "completed"
    assert body["semantic"]["status"] == "not_run"
    assert runtime_registry.get("validate-session") is None


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda: {"context_packet": valid_packet()},
        lambda: {"answer": "   ", "context_packet": valid_packet()},
        lambda: {"answer": 123, "context_packet": valid_packet()},
        lambda: {"answer": "ok"},
        lambda: {"answer": "ok", "context_packet": []},
        lambda: {"answer": "ok", "context_packet": valid_packet(), "validation_mode": "deep"},
    ],
)
def test_runtime_validate_request_schema_errors_return_422(api_context, payload_factory):
    app, runtime_registry = api_context
    runtime_registry.clear()
    client = TestClient(app)

    response = client.post("/runtime/validate", json=payload_factory())

    assert response.status_code == 422


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda p: p.update({"packet_version": "boris-context/1.0"}), "PACKET_VERSION_UNSUPPORTED"),
        (lambda p: p.update({"packet_version": "boris-context/9.9"}), "PACKET_VERSION_UNSUPPORTED"),
        (lambda p: p.update({"frame_id": "not-a-uuid"}), "FRAME_ID_INVALID"),
        (lambda p: p.pop("sima"), "PACKET_MISSING_FIELD"),
        (lambda p: p.update({"unexpected": True}), "PACKET_UNEXPECTED_FIELD"),
        (lambda p: p.update({"runtime_mode": "answer_provider"}), "RUNTIME_MODE_INVALID"),
        (lambda p: p.update({"llm_called": True}), "LLM_CALLED_INVALID"),
        (lambda p: p.update({"runtime_generated_prompt": 123}), "RUNTIME_GENERATED_PROMPT_INVALID"),
        (lambda p: p["bois_frame"].update({"raw_prompt": "secret"}), "BOIS_FRAME_INVALID"),
        (lambda p: p["sima"].update({"extra": True}), "SIMA_INVALID"),
        (lambda p: p["boris_context"].update({"authorization": "secret"}), "BORIS_CONTEXT_INVALID"),
        (lambda p: p["boris_context"].setdefault("session", {}).update({"last_decision": "secret"}), "BORIS_SESSION_INVALID"),
        (lambda p: p["projected_core"].append({"chunk_id": "a", "section": "s", "title": "t", "text": "x", "relevance": 1.0, "embedding": [1]}), "PROJECTED_CHUNK_INVALID"),
        (lambda p: p["projected_core"].extend([chunk("a", "x"), chunk("a", "y")]) or p["projection_metadata"].update({"returned_chunks": 2, "total_characters": 2}), "DUPLICATE_CHUNK_ID"),
        (lambda p: p["projected_core"].extend([chunk(str(i), "x") for i in range(7)]) or p["projection_metadata"].update({"returned_chunks": 7, "total_characters": 7}), "PROJECTION_LIMIT_EXCEEDED"),
        (lambda p: p["projected_core"].append(chunk("long", "x" * 3001)) or p["projection_metadata"].update({"returned_chunks": 1, "total_characters": 3001}), "PROJECTION_LIMIT_EXCEEDED"),
        (lambda p: p["projection_metadata"].update({"returned_chunks": 99}), "PROJECTION_METADATA_MISMATCH"),
        (lambda p: p["projection_metadata"].update({"total_characters": 99}), "PROJECTION_METADATA_MISMATCH"),
        (lambda p: p["projection_metadata"].update({"max_chunks": 7}), "PROJECTION_LIMIT_INVALID"),
        (lambda p: p["bois_frame"].update({"core": {"system_prompt": "hidden"}}), "FORBIDDEN_PACKET_FIELD"),
    ],
)
def test_preflight_failures_return_200_fail(api_context, mutate, code):
    app, runtime_registry = api_context
    runtime_registry.clear()
    packet = valid_packet()
    mutate(packet)
    client = TestClient(app)

    response = client.post(
        "/runtime/validate",
        json={"answer": "BOIS Runtime answer", "context_packet": packet},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "FAIL"
    assert body["llm_called"] is False
    assert body["preflight"]["status"] == "failed"
    assert body["deterministic"]["status"] == "not_run"
    assert body["semantic"]["status"] == "not_run"
    assert code in {issue["code"] for issue in body["issues"]}


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda p: p["sima"].update({"risk": True}), "SIMA_TYPE_INVALID"),
        (lambda p: p["projection_metadata"].update({"returned_chunks": False}), "PROJECTION_METADATA_TYPE_INVALID"),
        (lambda p: p["bois_frame"].update({"framework": 123}), "BOIS_FRAME_TYPE_INVALID"),
        (lambda p: p["bois_frame"].update({"core": "invalid"}), "BOIS_FRAME_TYPE_INVALID"),
        (lambda p: p["bois_frame"].update({"input": []}), "BOIS_FRAME_TYPE_INVALID"),
        (lambda p: p["bois_frame"].update({"constraints": "invalid"}), "BOIS_FRAME_TYPE_INVALID"),
        (lambda p: p["bois_frame"].update({"constraints": ["ok", 1]}), "BOIS_FRAME_TYPE_INVALID"),
        (lambda p: p["sima"].update({"risk": "high"}), "SIMA_TYPE_INVALID"),
        (lambda p: p["sima"].update({"uncertainty": None}), "SIMA_TYPE_INVALID"),
        (lambda p: p["sima"].update({"ambiguity_score": False}), "SIMA_TYPE_INVALID"),
        (lambda p: p["sima"].update({"missing_fields": "target"}), "SIMA_TYPE_INVALID"),
        (lambda p: p["sima"].update({"missing_fields": ["target", 1]}), "SIMA_TYPE_INVALID"),
        (lambda p: p["sima"].update({"risk": -0.1}), "SIMA_RANGE_INVALID"),
        (lambda p: p["sima"].update({"risk": 1.1}), "SIMA_RANGE_INVALID"),
        (lambda p: p["sima"].update({"uncertainty": 1.1}), "SIMA_RANGE_INVALID"),
        (lambda p: p["sima"].update({"ambiguity_score": -0.1}), "SIMA_RANGE_INVALID"),
        (lambda p: p["boris_context"].update({"name": 123}), "BORIS_CONTEXT_TYPE_INVALID"),
        (lambda p: p["boris_context"].update({"role": []}), "BORIS_CONTEXT_TYPE_INVALID"),
        (lambda p: p["boris_context"].update({"context": "invalid"}), "BORIS_CONTEXT_TYPE_INVALID"),
        (lambda p: p["boris_context"].update({"definition": []}), "BORIS_CONTEXT_TYPE_INVALID"),
        (lambda p: p["boris_context"].update({"session": []}), "BORIS_SESSION_INVALID"),
        (lambda p: p["boris_context"].update({"session": {"session_id": "   "}}), "BORIS_SESSION_TYPE_INVALID"),
        (lambda p: p["boris_context"].update({"session": {"clarification_cycles": True}}), "BORIS_SESSION_TYPE_INVALID"),
        (lambda p: p["boris_context"].update({"session": {"clarification_cycles": -1}}), "CLARIFICATION_CYCLES_INVALID"),
        (lambda p: p["boris_context"].update({"session": {"max_clarification_cycles": -1}}), "CLARIFICATION_CYCLES_INVALID"),
        (lambda p: p["bois_frame"].update({"framework": "NOT_BOIS"}), "BOIS_FRAMEWORK_INVALID"),
        (lambda p: p["bois_frame"].update({"input": "Different input"}), "BOIS_INPUT_MISMATCH"),
        (lambda p: p["boris_context"].update({"name": "NOT_BORIS"}), "BORIS_NAME_INVALID"),
        (lambda p: p["boris_context"].update({"session": {"session_id": "different"}}), "BORIS_SESSION_ID_MISMATCH"),
        (lambda p: p["boris_context"].update({"session": {"clarification_cycles": 3, "max_clarification_cycles": 2}}), "CLARIFICATION_CYCLES_INVALID"),
        (lambda p: p["projected_core"].append(chunk("a", "x") | {"section": 1}) or p["projection_metadata"].update({"returned_chunks": 1, "total_characters": 1}), "PROJECTED_CHUNK_TYPE_INVALID"),
        (lambda p: p["projected_core"].append(chunk("a", "x") | {"title": 1}) or p["projection_metadata"].update({"returned_chunks": 1, "total_characters": 1}), "PROJECTED_CHUNK_TYPE_INVALID"),
        (lambda p: p["projected_core"].append(chunk("a", "x") | {"relevance": "0.1"}) or p["projection_metadata"].update({"returned_chunks": 1, "total_characters": 1}), "PROJECTED_CHUNK_TYPE_INVALID"),
        (lambda p: p["projected_core"].append(chunk("a", "x") | {"relevance": True}) or p["projection_metadata"].update({"returned_chunks": 1, "total_characters": 1}), "PROJECTED_CHUNK_TYPE_INVALID"),
        (lambda p: p["projection_metadata"].update({"truncated": None}), "PROJECTION_METADATA_INVALID"),
        (lambda p: p["projection_metadata"].update({"truncated": 0}), "PROJECTION_METADATA_INVALID"),
        (lambda p: p["projection_metadata"].update({"total_characters": 0.0}), "PROJECTION_METADATA_TYPE_INVALID"),
        (lambda p: p["projection_metadata"].update({"max_chunks": True}), "PROJECTION_METADATA_TYPE_INVALID"),
        (lambda p: p["projection_metadata"].update({"max_chunk_characters": False}), "PROJECTION_METADATA_TYPE_INVALID"),
        (lambda p: p["projection_metadata"].update({"max_total_characters": True}), "PROJECTION_METADATA_TYPE_INVALID"),
        (lambda p: p["projection_metadata"].update({"returned_chunks": -1}), "PROJECTION_METADATA_TYPE_INVALID"),
        (lambda p: p["projection_metadata"].update({"total_characters": -1}), "PROJECTION_METADATA_TYPE_INVALID"),
    ],
)
def test_preflight_strict_types_and_invariants_return_200_fail(api_context, mutate, code):
    app, runtime_registry = api_context
    runtime_registry.clear()
    packet = valid_packet()
    mutate(packet)
    client = TestClient(app)

    response = client.post(
        "/runtime/validate",
        json={"answer": "BOIS Runtime answer", "context_packet": packet},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "FAIL"
    assert body["llm_called"] is False
    assert body["preflight"]["status"] == "failed"
    assert body["deterministic"]["status"] == "not_run"
    assert body["semantic"]["status"] == "not_run"
    assert code in {issue["code"] for issue in body["issues"]}


def test_projection_metadata_cross_field_limits_are_enforced(api_context):
    app, runtime_registry = api_context
    runtime_registry.clear()
    packet = valid_packet()
    packet["projection_metadata"]["returned_chunks"] = 7
    packet["projection_metadata"]["total_characters"] = 12001
    client = TestClient(app)

    response = client.post(
        "/runtime/validate",
        json={"answer": "BOIS Runtime answer", "context_packet": packet},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["verdict"] == "FAIL"
    assert "PROJECTION_METADATA_MISMATCH" in {issue["code"] for issue in body["issues"]}


def test_validation_preflight_accepts_runtime_generated_prompt(api_context):
    app, runtime_registry = api_context
    runtime_registry.clear()
    client = TestClient(app)

    response = client.post(
        "/runtime/validate",
        json={"answer": "BOIS Runtime answer", "context_packet": valid_packet()},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["preflight"]["status"] == "completed"
    assert "RUNTIME_GENERATED_PROMPT_INVALID" not in {issue["code"] for issue in body["issues"]}


def test_preflight_detects_configured_secret_but_not_top_level_input(api_context, monkeypatch):
    app, runtime_registry = api_context
    runtime_registry.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-test-value")
    packet = valid_packet()
    packet["input"] = "User typed super-secret-test-value as model-visible content"
    packet["bois_frame"]["core"] = {"public": "leaks super-secret-test-value"}
    client = TestClient(app)

    response = client.post(
        "/runtime/validate",
        json={"answer": "BOIS Runtime answer", "context_packet": packet},
    )

    body = response.json()
    assert body["verdict"] == "FAIL"
    assert "PACKET_SECRET_LEAK" in {issue["code"] for issue in body["issues"]}
    assert all(issue["path"] != "input" for issue in body["issues"])


def test_semantic_mode_answer_size_gate_blocks_adapter_construction():
    ValidationEngine = active_module("application.validation").ValidationEngine

    report = ValidationEngine(validator_adapter_factory=ForbiddenAdapterFactory()).validate(
        answer="x" * 20001,
        context_packet=valid_packet(),
        validation_mode="semantic",
    )

    assert report["verdict"] == "REVISE"
    assert report["llm_called"] is False
    assert report["semantic"]["status"] == "not_run"
    assert report["deterministic"]["status"] == "not_run"
    assert "ANSWER_TOO_LARGE" in {issue["code"] for issue in report["issues"]}


def test_semantic_mode_packet_size_gate_blocks_adapter_construction():
    ValidationEngine = active_module("application.validation").ValidationEngine
    packet = valid_packet()
    packet["input"] = "x" * 60001

    report = ValidationEngine(validator_adapter_factory=ForbiddenAdapterFactory()).validate(
        answer="BOIS Runtime answer",
        context_packet=packet,
        validation_mode="semantic",
    )

    assert report["verdict"] == "FAIL"
    assert report["llm_called"] is False
    assert report["semantic"]["status"] == "not_run"
    assert report["deterministic"]["status"] == "not_run"
    assert "PACKET_TOO_LARGE" in {issue["code"] for issue in report["issues"]}


def test_hybrid_size_gate_blocks_semantic_escalation():
    ValidationEngine = active_module("application.validation").ValidationEngine
    packet = valid_packet()
    packet["sima"]["risk"] = 0.9

    report = ValidationEngine(validator_adapter_factory=ForbiddenAdapterFactory()).validate(
        answer="x" * 20001,
        context_packet=packet,
        validation_mode="hybrid",
    )

    assert report["verdict"] == "REVISE"
    assert report["llm_called"] is False
    assert report["semantic"]["status"] == "not_run"


def test_deterministic_checks_secret_leak_missing_fields_and_duplicate_questions(monkeypatch):
    ValidationEngine = active_module("application.validation").ValidationEngine

    monkeypatch.setenv("OPENAI_API_KEY", "answer-secret-value")
    packet = valid_packet()
    packet["sima"]["missing_fields"] = ["target"]
    answer = "Which scope? Which scope? Also answer-secret-value"

    report = ValidationEngine(validator_adapter_factory=ForbiddenAdapterFactory()).validate(
        answer=answer,
        context_packet=packet,
        validation_mode="deterministic",
    )

    assert report["verdict"] == "FAIL"
    assert report["llm_called"] is False
    assert report["semantic"]["status"] == "not_run"
    codes = {issue["code"] for issue in report["issues"]}
    assert {"ANSWER_SECRET_LEAK", "DUPLICATE_CLARIFICATION_QUESTION"}.issubset(codes)
    assert any(issue["code"] == "MISSING_FIELDS_NOT_ADDRESSED" and issue["semantic_required"] for issue in report["issues"])


def test_semantic_mode_uses_strict_validator_output():
    ValidationEngine = active_module("application.validation").ValidationEngine

    adapter = FakeSemanticAdapter({
        "verdict": "REVISE",
        "issues": [
            {
                "code": "SEMANTIC_BOIS_MISALIGNMENT",
                "severity": "high",
                "message": "The answer contradicts the BOIS frame.",
                "path": "bois_frame.core",
            }
        ],
        "recommendations": ["Revise the claim so it remains supported by the packet."],
    })

    report = ValidationEngine(validator_adapter_factory=lambda: adapter).validate(
        answer="BOIS Runtime answer",
        context_packet=valid_packet(),
        validation_mode="semantic",
    )

    assert report["verdict"] == "REVISE"
    assert report["llm_called"] is True
    assert report["deterministic"]["status"] == "not_run"
    assert report["semantic"]["status"] == "completed"
    assert report["issues"][0]["source"] == "semantic"
    assert adapter.calls
    assert "Do not rewrite the answer" in adapter.calls[0]


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        {"verdict": "MAYBE", "issues": [], "recommendations": []},
        {"verdict": "PASS", "issues": [{"code": "X", "severity": "severe", "message": "bad"}], "recommendations": []},
        {"verdict": "PASS"},
        {"verdict": "PASS", "issues": [], "recommendations": [], "revised_answer": "no"},
    ],
)
def test_semantic_invalid_output_is_controlled(payload):
    validation_module = active_module("application.validation")
    semantic_module = sys.modules["application.semantic_validation"]
    SemanticValidationOutputError = semantic_module.SemanticValidationOutputError
    ValidationEngine = validation_module.ValidationEngine

    adapter = FakeSemanticAdapter(payload)

    with pytest.raises(SemanticValidationOutputError):
        ValidationEngine(validator_adapter_factory=lambda: adapter).validate(
            answer="BOIS Runtime answer",
            context_packet=valid_packet(),
            validation_mode="semantic",
        )


def test_semantic_unavailable_and_invalid_output_api_errors(api_context, monkeypatch):
    app, runtime_registry = api_context
    runtime_registry.clear()
    monkeypatch.setenv("BORIS_VALIDATOR_LLM", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)

    unavailable = client.post(
        "/runtime/validate",
        json={"answer": "BOIS Runtime answer", "context_packet": valid_packet(), "validation_mode": "semantic"},
    )

    assert unavailable.status_code == 503
    assert unavailable.json()["error"] == "llm_unavailable"
    assert "Traceback" not in unavailable.text

    monkeypatch.delenv("BORIS_VALIDATOR_LLM", raising=False)
    invalid = client.post(
        "/runtime/validate",
        json={"answer": "BOIS Runtime answer", "context_packet": valid_packet(), "validation_mode": "semantic"},
    )

    assert invalid.status_code == 502
    assert invalid.json()["error"] == "semantic_validation_error"
    assert "type" not in invalid.text


@pytest.mark.parametrize(
    "packet_factory,deterministic_answer,semantic_verdict,expected",
    [
        (lambda: elevated_packet(), "BOIS Runtime mentions unknown uncertainty.", "PASS", "REVISE"),
        (lambda: elevated_packet(), "BOIS Runtime mentions unknown uncertainty.", "REVISE", "REVISE"),
        (lambda: elevated_packet(), "BOIS Runtime mentions unknown uncertainty.", "FAIL", "FAIL"),
        (lambda: elevated_packet(), "BOIS Runtime mentions unknown uncertainty.", "INDETERMINATE", "INDETERMINATE"),
        (lambda: valid_packet(), "Nothing overlaps.", "PASS", "PASS"),
        (lambda: valid_packet(), "Nothing overlaps.", "FAIL", "FAIL"),
    ],
)
def test_hybrid_escalation_and_merge(packet_factory, deterministic_answer, semantic_verdict, expected):
    ValidationEngine = active_module("application.validation").ValidationEngine

    packet = packet_factory()
    adapter = FakeSemanticAdapter({"verdict": semantic_verdict, "issues": [], "recommendations": []})

    report = ValidationEngine(validator_adapter_factory=lambda: adapter).validate(
        answer=deterministic_answer,
        context_packet=packet,
        validation_mode="hybrid",
    )

    assert report["verdict"] == expected
    assert report["llm_called"] is True
    assert report["semantic"]["status"] == "completed"


def test_hybrid_deterministic_fail_does_not_call_semantic(monkeypatch):
    ValidationEngine = active_module("application.validation").ValidationEngine

    monkeypatch.setenv("OPENAI_API_KEY", "answer-secret-value")

    report = ValidationEngine(validator_adapter_factory=ForbiddenAdapterFactory()).validate(
        answer="BOIS Runtime leaks answer-secret-value",
        context_packet=valid_packet(),
        validation_mode="hybrid",
    )

    assert report["verdict"] == "FAIL"
    assert report["semantic"]["status"] == "not_run"
    assert report["llm_called"] is False


def test_hybrid_semantic_unavailable_and_invalid_output_preserve_deterministic(monkeypatch):
    validation_module = active_module("application.validation")
    from llm.errors import LLMConfigurationError

    ValidationEngine = validation_module.ValidationEngine

    packet = valid_packet()
    packet["sima"]["risk"] = 0.8

    unavailable = ValidationEngine(
        validator_adapter_factory=lambda: (_ for _ in ()).throw(LLMConfigurationError("missing key"))
    ).validate(
        answer="BOIS Runtime answer without risk disclosure",
        context_packet=packet,
        validation_mode="hybrid",
    )

    assert unavailable["verdict"] == "INDETERMINATE"
    assert unavailable["semantic"]["status"] == "unavailable"
    assert unavailable["deterministic"]["status"] == "completed"
    assert unavailable["llm_called"] is False

    invalid = ValidationEngine(
        validator_adapter_factory=lambda: FakeSemanticAdapter("not-json")
    ).validate(
        answer="BOIS Runtime answer without risk disclosure",
        context_packet=packet,
        validation_mode="hybrid",
    )

    assert invalid["verdict"] == "INDETERMINATE"
    assert invalid["semantic"]["status"] == "invalid_output"
    assert invalid["deterministic"]["status"] == "completed"
    assert invalid["llm_called"] is True


def test_validator_specific_config_falls_back_to_main_settings(monkeypatch):
    config = active_module("llm.config")

    captured = {}

    class FakeOpenAIAdapter:
        def __init__(self, model=None, api_key=None, debug_prompt_enabled=False):
            captured["model"] = model
            captured["api_key"] = api_key
            captured["debug_prompt_enabled"] = debug_prompt_enabled

    monkeypatch.setattr(config, "OpenAIAdapter", FakeOpenAIAdapter)
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("BOIS_LLM", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "main-model")
    monkeypatch.delenv("BORIS_VALIDATOR_LLM", raising=False)
    monkeypatch.delenv("BORIS_VALIDATOR_MODEL", raising=False)

    adapter = config.build_validator_llm_adapter()

    assert isinstance(adapter, FakeOpenAIAdapter)
    assert captured["model"] == "main-model"

    monkeypatch.setenv("BORIS_VALIDATOR_LLM", "openai")
    monkeypatch.setenv("BORIS_VALIDATOR_MODEL", "validator-model")

    config.build_validator_llm_adapter()

    assert captured["model"] == "validator-model"
def valid_packet():
    return {
        "packet_version": "boris-context/2.0",
        "frame_id": "00000000-0000-4000-8000-000000000000",
        "session_id": "validate-session",
        "input": "Explain BOIS Runtime",
        "runtime_mode": "context_provider",
        "llm_called": False,
        "bois_frame": {},
        "sima": {
            "risk": 0.2,
            "uncertainty": 0.2,
            "missing_fields": [],
            "ambiguity_score": 0.1,
        },
        "boris_context": {},
        "projected_core": [],
        "projection_metadata": {
            "returned_chunks": 0,
            "total_characters": 0,
            "truncated": False,
            "max_chunks": 6,
            "max_chunk_characters": 3000,
            "max_total_characters": 12000,
        },
        "answer_instructions": [],
        "runtime_generated_prompt": "## User input\nExplain BOIS Runtime",
    }


def chunk(chunk_id, text):
    return {
        "chunk_id": chunk_id,
        "section": "section",
        "title": "title",
        "text": text,
        "relevance": 1.0,
    }


def elevated_packet():
    packet = valid_packet()
    packet["sima"].update({"risk": 0.9, "uncertainty": 0.9, "missing_fields": ["target"]})
    return packet


def minimal_report(verdict="PASS"):
    return {
        "validation_version": "boris-validation/1.0",
        "frame_id": "00000000-0000-4000-8000-000000000000",
        "validation_mode": "deterministic",
        "verdict": verdict,
        "llm_called": False,
        "preflight": {"status": "completed", "issues": []},
        "deterministic": {
            "status": "completed",
            "verdict": verdict,
            "checks": [],
            "issues": [],
            "recommendations": [],
        },
        "semantic": {
            "status": "not_run",
            "verdict": "INDETERMINATE",
            "issues": [],
            "recommendations": [],
        },
        "issues": [],
        "recommendations": [],
    }
