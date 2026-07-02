from adapters.cli import CLIAdapter
from adapters.web import WebAdapter
from core.loader import SchemaLoader
from kernel.llm import LLM
from kernel.memory import Memory
from kernel.runtime import BORISKernel


def build_test_kernel(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return BORISKernel(memory=Memory(":memory:"))


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

    assert result["type"] in {"ANSWER", "QUESTION", "ERROR"}
    assert isinstance(result["content"], str)
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
    llm = LLM()

    result = llm.generate({"input": "hello"})

    assert result.startswith("LOCAL_STUB_RESPONSE")
    assert "hello" in result
