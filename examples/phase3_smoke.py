from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.main import build_llm_adapter
from llm.llm_adapter import MockLLMAdapter
from llm.llm_adapter import LLMAdapter
from protocol.engine import ProtocolEngine
from runtime.session import create_runtime_session


def assert_schema(output):
    assert output["type"] in {"ANSWER", "QUESTION", "TOOL_CALL", "GAP"}
    assert isinstance(output["content"], str)
    assert isinstance(output["metadata"], dict)


session = create_runtime_session("core/definitions", session_id="phase3-smoke")
engine = ProtocolEngine(llm_adapter=MockLLMAdapter())

try:
    session.core["bois_core"] = {}
except TypeError:
    pass
else:
    raise AssertionError("core must be immutable")

answer = engine.run_turn(session, "describe a hidden object")
assert_schema(answer)
assert answer["type"] == "ANSWER"
assert answer["content"] != "describe a hidden object"
assert answer["metadata"]["llm_called"] is True
assert answer["metadata"]["llm_adapter"] == "mock"

repeated = engine.run_turn(session, "describe a hidden object")
assert_schema(repeated)
assert repeated["metadata"]["duplicate"] is True
assert repeated["metadata"]["llm_called"] is False
assert repeated["metadata"]["llm_adapter"] == "mock"

exit_output = engine.run_turn(session, "exit")
assert_schema(exit_output)
assert exit_output["metadata"]["exit"] is True
assert exit_output["metadata"]["llm_called"] is False
assert exit_output["metadata"]["llm_adapter"] == "mock"


class RepeatingQuestionLLM(LLMAdapter):
    adapter_name = "mock"

    def call(self, prompt: str) -> str:
        return '{"type": "QUESTION", "content": "provide target", "metadata": {}}'


question_session = create_runtime_session("core/definitions", session_id="phase3-question")
question_engine = ProtocolEngine(llm_adapter=RepeatingQuestionLLM())
question = question_engine.run_turn(question_session, "first prompt")
assert_schema(question)
assert question["type"] == "QUESTION"

repeated_question = question_engine.run_turn(question_session, "second prompt")
assert_schema(repeated_question)
assert repeated_question["type"] == "GAP"


class CountingLLM(LLMAdapter):
    adapter_name = "mock"

    def __init__(self):
        self.calls = 0

    def call(self, prompt: str) -> str:
        self.calls += 1
        return '{"type": "ANSWER", "content": "ok", "metadata": {}}'


counting = CountingLLM()
counting_session = create_runtime_session("core/definitions", session_id="phase3-counting")
counting_engine = ProtocolEngine(llm_adapter=counting)
first = counting_engine.run_turn(counting_session, "same")
second = counting_engine.run_turn(counting_session, "same")
assert_schema(first)
assert_schema(second)
assert counting.calls == 1
assert first["metadata"]["llm_called"] is True
assert second["metadata"]["duplicate"] is True
assert second["metadata"]["llm_called"] is False

old_mode = os.environ.get("BOIS_LLM")
old_key = os.environ.get("OPENAI_API_KEY")
os.environ["BOIS_LLM"] = "openai"
os.environ.pop("OPENAI_API_KEY", None)
try:
    build_llm_adapter()
except RuntimeError:
    pass
else:
    raise AssertionError("BOIS_LLM=openai must not silently fall back to mock")
finally:
    if old_mode is None:
        os.environ.pop("BOIS_LLM", None)
    else:
        os.environ["BOIS_LLM"] = old_mode

    if old_key is None:
        os.environ.pop("OPENAI_API_KEY", None)
    else:
        os.environ["OPENAI_API_KEY"] = old_key

print("phase3 smoke ok")
