import builtins
import inspect

from adapters.cli import CLIAdapter
from adapters.web import WebAdapter
from core.loader import EpistemicHierarchyLoader, SchemaLoader
import kernel.runtime as kernel_runtime
from kernel.llm import LLM
from kernel.memory import Memory
from kernel.runtime import BORISKernel
from kernel.self_introspection import explain_system
import main_cli
import runtime.engine as runtime_engine
from physiology.domain import DEFAULT_DOMAIN


def build_test_kernel(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return BORISKernel(memory=Memory(":memory:"), llm=LLM(api_key="", load_environment=False))


class CountingLLM:

    def __init__(self):
        self.calls = 0

    def generate(self, context):
        self.calls += 1
        return "counting llm answer"


def test_schema_loads_from_core_package():
    schema = SchemaLoader().schema

    assert schema["entrypoint"] == "INGEST"
    assert "RETURN" in schema["states"]


def test_epistemic_hierarchy_loads_priority_order():
    hierarchy = EpistemicHierarchyLoader().hierarchy

    assert hierarchy["priority_order"] == [
        "DOMAIN",
        "MEMORY",
        "RUNTIME_STATE",
        "LLM"
    ]
    assert hierarchy["question_memory"]["max_clarifications_per_session_topic"] == 2
    assert "sima_uncertainty_clarification" in hierarchy["thresholds"]


def test_kernel_initializes(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    assert kernel.memory is not None
    assert kernel.engine is not None


def test_cli_style_event_returns_valid_response(monkeypatch):
    adapter = CLIAdapter(build_test_kernel(monkeypatch))

    result = adapter.handle("Explain BOIS Runtime v0", session_id="test")

    assert result["type"] in {
        "ANSWER",
        "CLARIFICATION",
        "TOOL_REQUEST",
        "ERROR",
        "SELF_DESCRIPTION"
    }
    assert isinstance(result["answer"], str)
    assert isinstance(result["content"], str)
    assert result["answer"] == result["content"]
    assert isinstance(result["trace"], dict)
    assert isinstance(result["state"], dict)
    assert isinstance(result["actions"], list)
    assert result["trace_id"]
    assert "requires_user_input" in result["meta"]


def test_web_adapter_normalizes_input(monkeypatch):
    adapter = WebAdapter(build_test_kernel(monkeypatch))

    event = adapter.normalize({
        "session_id": "test",
        "input": "hello",
        "meta": {"source": "client"}
    })

    assert event == {
        "session_id": "test",
        "input": "hello",
        "meta": {
            "source": "web"
        }
    }


def test_missing_openai_key_does_not_crash(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm = LLM(api_key="", load_environment=False)

    result = llm.generate({"input": "hello"})

    assert result.startswith("LOCAL_STUB_RESPONSE")
    assert "hello" in result


def test_local_stub_does_not_require_openai_sdk(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai":
            raise ModuleNotFoundError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    llm = LLM(api_key="", load_environment=False)
    result = llm.generate({"input": "hello"})

    assert result.startswith("LOCAL_STUB_RESPONSE")


def test_configured_key_without_openai_sdk_returns_clear_message(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai":
            raise ModuleNotFoundError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    llm = LLM(api_key="test-key", load_environment=False)
    result = llm.generate({"input": "hello"})

    assert result.startswith("OPENAI_SDK_NOT_INSTALLED")


def test_llm_extracts_plain_answer_from_json_content():
    llm = LLM(api_key="", load_environment=False)

    result = llm._to_user_answer('{"response":{"message":"Hello from BORIS."},"sima":{}}')

    assert result == "Hello from BORIS."


def test_runtime_response_contract_separates_answer_trace_state(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "Explain BOIS Runtime v0",
        "meta": {"source": "test"}
    })

    assert set(["type", "answer", "trace", "state", "actions"]).issubset(result)
    assert isinstance(result["answer"], str)
    assert isinstance(result["trace"], dict)
    assert isinstance(result["state"], dict)
    assert isinstance(result["actions"], list)
    assert "sima" in result["trace"]
    assert "bois" in result["trace"]
    assert result["state"]["domain"]["name"] == "default"


def test_domain_contains_v1_static_descriptor_fields():
    domain = DEFAULT_DOMAIN.snapshot()

    assert isinstance(domain["name"], str)
    assert isinstance(domain["capabilities"], list)
    assert isinstance(domain["limitations"], list)
    assert isinstance(domain["success_criteria"], list)
    assert isinstance(domain["version"], str)
    assert "text reasoning" in domain["capabilities"]
    assert "runtime state machine execution" in domain["capabilities"]
    assert "no autonomous self-modification" in domain["limitations"]
    assert "ensure single terminal state per input" in domain["success_criteria"]


def test_introspection_response_for_capabilities_query(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "what can you do",
        "meta": {"source": "test"}
    })

    assert result["type"] == "SELF_DESCRIPTION"
    assert isinstance(result["answer"], str)
    assert result["answer"]
    assert "text reasoning" in result["answer"]
    assert result["trace"]["source"] == ["domain", "memory"]
    assert result["state"]["read_only"] is True


def test_normal_input_does_not_use_introspection(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "Explain BOIS Runtime v0",
        "meta": {"source": "test"}
    })

    assert result["type"] != "SELF_DESCRIPTION"
    assert "sima" in result["trace"]
    assert "bois" in result["trace"]


def test_introspection_is_read_only_for_memory_and_engine(monkeypatch):
    memory = Memory(":memory:")
    kernel = BORISKernel(
        memory=memory,
        llm=LLM(api_key="", load_environment=False)
    )
    before_memory = memory.read_recent()
    before_state = kernel.engine.state

    result = kernel.run({
        "session_id": "test",
        "input": "limitations",
        "meta": {"source": "test"}
    })

    after_memory = memory.read_recent()
    after_state = kernel.engine.state

    assert result["type"] == "SELF_DESCRIPTION"
    assert after_memory == before_memory
    assert after_state == before_state


def test_explain_system_direct_entry_shape():
    result = explain_system("who are you", DEFAULT_DOMAIN)

    assert result["type"] == "SELF_DESCRIPTION"
    assert result["answer"]
    assert result["trace"]["source"] == ["domain"]
    assert result["state"]["mode"] == "self_introspection"
    assert result["actions"] == []


def test_explanatory_input_returns_single_answer_terminal(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "Explain BOIS Runtime v0",
        "meta": {"source": "test"}
    })

    assert result["type"] == "ANSWER"
    assert result["answer"]
    assert result["type"] != "CLARIFICATION"
    assert result["state"]["phase"] == "FINALIZE"


def test_answer_decision_uses_epistemic_priority_order(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "Explain BOIS Runtime v0",
        "meta": {"source": "test"}
    })

    assert result["type"] == "ANSWER"
    assert result["trace"]["epistemic"]["priority_order"] == [
        "DOMAIN",
        "MEMORY",
        "RUNTIME_STATE",
        "LLM"
    ]
    assert [
        item["source"] for item in result["trace"]["epistemic"]["decisions"]
    ] == [
        "DOMAIN",
        "MEMORY",
        "RUNTIME_STATE",
        "LLM"
    ]
    assert result["trace"]["llm_allowed"] is True


def test_empty_input_returns_single_non_answer_terminal(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "",
        "meta": {"source": "test"}
    })

    assert result["type"] in {"CLARIFICATION", "ERROR"}
    assert result["type"] != "ANSWER"
    assert result["answer"]
    assert result["state"]["phase"] == "DECIDE"
    assert result["trace"]["epistemic"]["decisions"][0]["source"] == "DOMAIN"


def test_ambiguous_non_empty_input_returns_one_terminal(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "Do it",
        "meta": {"source": "test"}
    })

    assert result["type"] in {"CLARIFICATION", "ANSWER"}
    assert result["type"] in {"ANSWER", "CLARIFICATION", "TOOL_REQUEST", "ERROR"}
    assert result["answer"]


def test_answer_does_not_contain_stringified_internal_json(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "Explain BOIS Runtime v0",
        "meta": {"source": "test"}
    })

    assert "'sima':" not in result["answer"]
    assert '"sima":' not in result["answer"]
    assert "'bois':" not in result["answer"]
    assert '"bois":' not in result["answer"]


def test_cli_skips_empty_prompt_after_answer(monkeypatch, capsys):
    calls = []

    class FakeAdapter:
        def __init__(self, kernel):
            self.kernel = kernel

        def handle(self, user_input):
            calls.append(user_input)
            return {"type": "ANSWER", "answer": "ok"}

    inputs = iter(["Explain BOIS Runtime v0", "", "quit"])

    monkeypatch.setattr(main_cli, "BORISKernel", lambda: object())
    monkeypatch.setattr(main_cli, "CLIAdapter", FakeAdapter)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    main_cli.main()

    output = capsys.readouterr().out
    assert calls == ["Explain BOIS Runtime v0"]
    assert "ANSWER: ok" in output
    assert "CLARIFICATION: need_more_input" not in output


def test_cli_answer_is_terminal_and_quit_is_local(monkeypatch, capsys):
    calls = []

    class FakeAdapter:
        def __init__(self, kernel):
            self.kernel = kernel

        def handle(self, user_input):
            calls.append(user_input)
            return {"type": "ANSWER", "answer": "Napoleon did not have an elephant."}

    inputs = iter(["What color is Napoleon's elephant?", "quit"])

    monkeypatch.setattr(main_cli, "BORISKernel", lambda: object())
    monkeypatch.setattr(main_cli, "CLIAdapter", FakeAdapter)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    main_cli.main()

    output = capsys.readouterr().out
    assert calls == ["What color is Napoleon's elephant?"]
    assert output.count("QUESTION: What color is Napoleon's elephant?") == 1
    assert output.count("ANSWER:") == 1
    assert "CLARIFICATION:" not in output


def test_cli_quite_typo_is_local(monkeypatch, capsys):
    calls = []

    class FakeAdapter:
        def __init__(self, kernel):
            self.kernel = kernel

        def handle(self, user_input):
            calls.append(user_input)
            return {"type": "CLARIFICATION", "answer": "should not happen"}

    inputs = iter(["quite", "quit"])

    monkeypatch.setattr(main_cli, "BORISKernel", lambda: object())
    monkeypatch.setattr(main_cli, "CLIAdapter", FakeAdapter)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    main_cli.main()

    output = capsys.readouterr().out
    assert calls == []
    assert 'Did you mean "quit"? Type "quit" to exit.' in output
    assert "QUESTION: quite" not in output
    assert "CLARIFICATION: need_more_input" not in output


def test_cli_empty_input_is_local(monkeypatch, capsys):
    calls = []

    class FakeAdapter:
        def __init__(self, kernel):
            self.kernel = kernel

        def handle(self, user_input):
            calls.append(user_input)
            return {"type": "CLARIFICATION", "answer": "should not happen"}

    inputs = iter(["", "quit"])

    monkeypatch.setattr(main_cli, "BORISKernel", lambda: object())
    monkeypatch.setattr(main_cli, "CLIAdapter", FakeAdapter)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    main_cli.main()

    output = capsys.readouterr().out
    assert calls == []
    assert 'Please enter a question or type "quit" to exit.' in output
    assert "QUESTION:" not in output
    assert "CLARIFICATION: need_more_input" not in output


def test_cli_q_exits_locally(monkeypatch, capsys):
    calls = []

    class FakeAdapter:
        def __init__(self, kernel):
            self.kernel = kernel

        def handle(self, user_input):
            calls.append(user_input)
            return {"type": "ANSWER", "answer": "should not happen"}

    inputs = iter(["q"])

    monkeypatch.setattr(main_cli, "BORISKernel", lambda: object())
    monkeypatch.setattr(main_cli, "CLIAdapter", FakeAdapter)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    main_cli.main()

    output = capsys.readouterr().out
    assert calls == []
    assert "QUESTION:" not in output


def test_clarification_answer_is_user_facing(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    result = kernel.run({
        "session_id": "test",
        "input": "Do it",
        "meta": {"source": "test"}
    })

    assert result["type"] == "CLARIFICATION"
    assert result["answer"] != "need_more_input"
    assert "Please clarify" in result["answer"]
    assert "need_more_input" in result["trace"]["clarification_reason"]


def test_llm_is_not_called_for_gap_clarification(monkeypatch):
    llm = CountingLLM()
    kernel = BORISKernel(memory=Memory(":memory:"), llm=llm)

    result = kernel.run({
        "session_id": "test",
        "input": "Do it",
        "meta": {"source": "test"}
    })

    assert result["type"] == "CLARIFICATION"
    assert llm.calls == 0
    assert [
        item["source"] for item in result["trace"]["epistemic"]["decisions"]
    ] == [
        "DOMAIN",
        "MEMORY",
        "RUNTIME_STATE"
    ]


def test_question_memory_prevents_repeated_clarification(monkeypatch):
    llm = CountingLLM()
    kernel = BORISKernel(memory=Memory(":memory:"), llm=llm)
    event = {
        "session_id": "test",
        "input": "Do it",
        "meta": {"source": "test"}
    }

    first = kernel.run(event)
    second = kernel.run(event)

    assert first["type"] == "CLARIFICATION"
    assert second["type"] == "ANSWER"
    assert "best available answer" in second["answer"]
    assert llm.calls == 0
    assert kernel.memory.clarification_count("test", "do it") == 1


def test_question_memory_limit_forces_answer_from_json_config(monkeypatch):
    llm = CountingLLM()
    memory = Memory(":memory:")
    memory.remember_clarification("test", "do it", "first question")
    memory.remember_clarification("test", "do it", "second question")
    kernel = BORISKernel(memory=memory, llm=llm)

    result = kernel.run({
        "session_id": "test",
        "input": "Do it",
        "meta": {"source": "test"}
    })

    assert result["type"] == "ANSWER"
    assert "best available answer" in result["answer"]
    assert llm.calls == 0
    assert result["trace"]["epistemic"]["decisions"][1]["source"] == "MEMORY"
    assert result["trace"]["epistemic"]["decisions"][1]["max_clarifications"] == 2


def test_runtime_engine_is_state_machine_owner():
    engine_source = inspect.getsource(runtime_engine.BORISRuntimeEngine)
    kernel_source = inspect.getsource(kernel_runtime)

    assert "def step(" in engine_source
    assert "def decide_next_state(" in engine_source
    assert "def step(" not in kernel_source
    assert "def decide_next_state(" not in kernel_source
    assert "composition root" in (kernel_runtime.__doc__ or "")


def test_schema_does_not_advertise_unused_gap_transition():
    schema = SchemaLoader().schema
    gap_state = schema["states"]["GAP_DETECTION"]

    assert gap_state == {
        "type": "decision",
        "next": "TOOL_ROUTING"
    }
    assert "ASK_OPERATOR" not in schema["states"]
    assert "next_true" not in gap_state
    assert "next_false" not in gap_state


def test_default_domain_loads_correctly():
    domain = DEFAULT_DOMAIN.snapshot()

    assert domain["name"] == "default"
    assert "general reasoning" in domain["scope"]
    assert domain["out_of_scope"] == []
    assert "answer is useful" in domain["success_criteria"]
    assert domain["learning_policy"] == (
        "store only stable operator-approved or repeatedly confirmed knowledge"
    )
