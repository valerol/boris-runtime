from adapters.cli import CLIAdapter
from kernel.runtime import BORISKernel


def main():
    adapter = CLIAdapter(BORISKernel())

    print("BORIS CLI READY")

    while True:
        user_input = input("> ").strip()

        command = user_input.lower()

        if command in {"exit", "quit", "q"}:
            break

        if not user_input:
            print('Please enter a question or type "quit" to exit.')
            continue

        if command == "quite":
            print('Did you mean "quit"? Type "quit" to exit.')
            continue

        print(f"QUESTION: {user_input}")
        result = adapter.handle(user_input)
        print(f"{result['type']}: {result['answer']}")


if __name__ == "__main__":
    main()
