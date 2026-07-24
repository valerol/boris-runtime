import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from application.context_provider import ContextProvider, CoreSurfaceUnavailable
from llm.config import load_env_file


def main():
    load_env_file()
    provider = ContextProvider()

    while True:
        try:
            user_input = input("> ").strip()
        except EOFError:
            break

        if user_input.lower() in {"exit", "quit", "/exit", "/quit"}:
            break

        try:
            output = provider.frame(user_input)
        except CoreSurfaceUnavailable as exc:
            print(f"BOIS Core Surface error: {exc}", file=sys.stderr)
            break
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
