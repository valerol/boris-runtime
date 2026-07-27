from application.execution import SemanticInputCompiler
from application.semantic_provider import (
    CHATGPT_HOST_PROVIDER,
    SERVER_LLM_PROVIDER,
    ChatGPTHostProvider,
    SemanticProvider,
    ServerLLMProvider,
)
from tests.test_execution import (
    CompilerAdapter,
    RecordingCalculator,
    compiler_payload,
)
from tests.test_semantic_executor import (
    build_accepted_compatibility,
    build_surface,
)


def test_server_llm_provider_is_the_canonical_semantic_port():
    surface = build_surface()
    compatibility = build_accepted_compatibility(surface)
    events = []
    text = "Explain the runtime."
    adapter = CompilerAdapter(compiler_payload(text), events)
    calculator = RecordingCalculator(events)
    provider = ServerLLMProvider(
        llm_adapter_factory=lambda: adapter,
        compiler_factory=lambda value: SemanticInputCompiler(value),
        calculator_factory=lambda _value: calculator,
    )

    result = provider.execute(
        surface=surface,
        compatibility=compatibility,
        source_text=text,
        context={},
    )

    assert isinstance(provider, SemanticProvider)
    assert provider.provider_id == SERVER_LLM_PROVIDER
    assert provider.canonical is True
    assert result.semantic_input.phase == "C03"
    assert result.candidate.phase == "C03"
    assert result.candidate.gate == "PASS"
    assert events == [
        "semantic_input_compiler",
        "semantic_executor",
    ]
    assert set(result.stage_timings_ms) == {
        "semantic_input_compile",
        "semantic_executor",
    }


def test_server_llm_provider_reuses_signed_semantic_input_on_resume():
    surface = build_surface()
    compatibility = build_accepted_compatibility(surface)
    events = []
    text = "Explain the runtime."
    adapter = CompilerAdapter(compiler_payload(text), events)
    compiler = SemanticInputCompiler(adapter)
    semantic_input = compiler.compile(surface, text)
    events.clear()
    calculator = RecordingCalculator(events)
    provider = ServerLLMProvider(
        llm_adapter_factory=lambda: adapter,
        compiler_factory=lambda value: SemanticInputCompiler(value),
        calculator_factory=lambda _value: calculator,
    )

    result = provider.execute(
        surface=surface,
        compatibility=compatibility,
        source_text=text,
        semantic_input=semantic_input,
        operator_decision={
            "resolution_mode": "ALLOW_CONDITIONAL_PROCEEDING",
        },
    )

    assert result.semantic_input is semantic_input
    assert events == ["semantic_executor"]
    assert set(result.stage_timings_ms) == {"semantic_executor"}


def test_chatgpt_host_provider_is_explicitly_experimental():
    calls = []
    provider = ChatGPTHostProvider(
        prepare_callback=lambda *args, **kwargs: (
            calls.append(("prepare", args, kwargs)) or {"status": "prepared"}
        ),
        submit_callback=lambda *args, **kwargs: (
            calls.append(("submit", args, kwargs)) or {"status": "submitted"}
        ),
    )

    prepared = provider.prepare("phenomenon", session_id="host-test")
    submitted = provider.submit(work_order_id="work-order")

    assert isinstance(provider, SemanticProvider)
    assert provider.provider_id == CHATGPT_HOST_PROVIDER
    assert provider.canonical is False
    assert provider.interaction_mode == "signed_work_order"
    assert prepared == {"status": "prepared"}
    assert submitted == {"status": "submitted"}
    assert [item[0] for item in calls] == ["prepare", "submit"]
