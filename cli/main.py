import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_retriever.retrieve import CoreRetrieverError
from runtime.config import build_llm_adapter, load_env_file
from runtime.runtime import BOISRuntime


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

        try:
            output = runtime.run(user_input, input_provider=ask_for_clarification)
        except CoreRetrieverError as exc:
            print(f"BOIS Core retriever error: {exc}", file=sys.stderr)
            break
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
