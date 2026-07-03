import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.llm import MockLLMAdapter, OpenAIChatAdapter
from adapters.tools import EchoToolAdapter
from runtime.engine import MiddlewareEngine


def build_llm_adapter():
    if os.getenv("BOIS_LLM", "").lower() == "openai":
        return OpenAIChatAdapter()
    return MockLLMAdapter()


def format_response(response):
    if response.type == "clarification":
        return f"CLARIFICATION: {response.content}"
    if response.type == "tool_call":
        return f"TOOL_CALL: {response.tool_request}"
    return f"FINAL: {response.content}"


def main():
    engine = MiddlewareEngine(
        llm_adapter=build_llm_adapter(),
        tool_adapter=EchoToolAdapter(),
    )

    print("BOIS / SIMA / BORIS middleware CLI")
    print('Type "exit" or "quit" to stop.')

    while True:
        try:
            user_input = input("> ")
        except EOFError:
            break

        if user_input.strip().lower() in {"exit", "quit"}:
            break

        response = engine.run(user_input)
        print(format_response(response))


if __name__ == "__main__":
    main()

