from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm.llm_adapter import MockLLMAdapter
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

question = engine.run_turn(session, "what color are my pants?")
assert_schema(question)
assert question["type"] == "QUESTION"

repeated = engine.run_turn(session, "what color are my pants?")
assert_schema(repeated)
assert repeated["type"] != "QUESTION"

limited = create_runtime_session("core/definitions", session_id="phase3-limit")
limited.state.clarification_cycles = limited.state.max_clarification_cycles
limited_out = engine.run_turn(limited, "what color are my pants?")
assert_schema(limited_out)
assert limited_out["type"] == "GAP"

answer = engine.run_turn(session, "Explain BOIS Runtime v0.")
assert_schema(answer)
assert answer["type"] == "ANSWER"

print("phase3 smoke ok")
