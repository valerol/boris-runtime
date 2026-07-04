import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm.llm_adapter import MockLLMAdapter, OpenAIAdapter
from runtime.runtime import BOISRuntime


def load_env_file(path=None):
    env_path = Path(path) if path else PROJECT_ROOT / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def build_llm_adapter():
    if os.getenv("BOIS_LLM", "").lower() == "openai":
        return OpenAIAdapter()
    return MockLLMAdapter()


def ask_for_clarification(output):
    print(json.dumps(output, ensure_ascii=False))
    try:
        return input("clarification> ").strip()
    except EOFError:
        return ""


def main():
    load_env_file()
    runtime = BOISRuntime(llm_adapter=build_llm_adapter())

    while True:
        try:
            user_input = input("> ").strip()
        except EOFError:
            break

        if runtime.engine.is_exit(user_input):
            break

        output = runtime.run(user_input, input_provider=ask_for_clarification)
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
