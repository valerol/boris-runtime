import builtins
import inspect

from adapters.cli import CLIAdapter
from adapters.web import WebAdapter
from core.loader import SchemaLoader
import kernel.runtime as kernel_runtime
from kernel.llm import LLM
from kernel.memory import Memory
from kernel.runtime import BORISKernel
import main_cli
import runtime.engine as runtime_engine
from physiology.domain import DEFAULT_DOMAIN


def build_test_kernel(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return BORISKernel(memory=Memory(":memory:"), llm=LLM(api_key="", load_environment=False))


def test_schema_loads_from_core_package():
    schema = SchemaLoader().schema

    assert schema["entrypoint"] == "INGEST"
    assert "RETURN" in schema["states"]


def test_kernel_initializes(monkeypatch):
    kernel = build_test_kernel(monkeypatch)

    assert kernel.memory is not None
    assert kernel.engine is not None


def test_cli_style_event_returns_valid_response(monkeypatch):
    adapter = CLIAdapter(build_test_kernel(monkeypatch))

    result = adapter.handle("Explain BOIS Runtime v0", session_id="test")

    assert result["type"] in {"ANSWER", "CLARIFICATION", "TOOL_REQUEST", "ERROR"}
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
