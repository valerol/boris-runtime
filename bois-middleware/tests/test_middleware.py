import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.llm import MockLLMAdapter
from runtime.engine import MiddlewareEngine


def test_engine_returns_final_response():
    engine = MiddlewareEngine(MockLLMAdapter())

    response = engine.run("Explain the protocol.")

    assert response.type == "final"
    assert "Explain the protocol." in response.content


def test_engine_clarifies_empty_input_without_llm_call():
    engine = MiddlewareEngine(MockLLMAdapter())

    response = engine.run("")

    assert response.type == "clarification"
    assert response.content == "Please provide a request."

