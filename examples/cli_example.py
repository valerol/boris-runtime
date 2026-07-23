from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm.llm_adapter import MockLLMAdapter
from runtime.runtime import BOISRuntime


runtime = BOISRuntime(llm_adapter=MockLLMAdapter())
response = runtime.run("Summarize the new architecture principle.")
print(response["type"])
print(response["content"])
