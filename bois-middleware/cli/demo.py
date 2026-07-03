from cli.run import format_response
from adapters.llm import MockLLMAdapter
from runtime.engine import MiddlewareEngine


def main():
    engine = MiddlewareEngine(MockLLMAdapter())
    print(format_response(engine.run("Explain the middleware boundary.")))


if __name__ == "__main__":
    main()

