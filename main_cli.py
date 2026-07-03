from adapters.cli import CLIAdapter
from kernel.runtime import BORISKernel


def main():
    adapter = CLIAdapter(BORISKernel())

    print("BORIS CLI READY")

    while True:
        user_input = input("> ").strip()

        if user_input.lower() in {"exit", "quit"}:
            break

        if not user_input:
            continue

        print(f"QUESTION: {user_input}")
        result = adapter.handle(user_input)
        print(f"{result['type']}: {result['answer']}")


if __name__ == "__main__":
    main()
