from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from application.context_provider import ContextProvider


provider = ContextProvider()
frame = provider.frame("Summarize the new architecture principle.")
print(frame["runtime_generated_prompt"])
