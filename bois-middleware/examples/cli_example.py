from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.llm import MockLLMAdapter
from runtime.engine import MiddlewareEngine


engine = MiddlewareEngine(MockLLMAdapter())
response = engine.run("Summarize the new architecture principle.")
print(response.type)
print(response.content)

