from adapters.cli import CLIAdapter
from adapters.web import WebAdapter
from core.loader import SchemaLoader
from kernel.llm import LLM
from kernel.memory import Memory
from kernel.runtime import BORISKernel
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


def test_default_domain_loads_correctly():
    domain = DEFAULT_DOMAIN.snapshot()

    assert domain["name"] == "default"
    assert "general reasoning" in domain["scope"]
    assert domain["out_of_scope"] == []
    assert "answer is useful" in domain["success_criteria"]
    assert domain["learning_policy"] == (
        "store only stable operator-approved or repeatedly confirmed knowledge"
    )
