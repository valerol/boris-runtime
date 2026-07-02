from kernel.runtime import BORISKernel

kernel = BORISKernel()

print("BORIS CLI READY")

while True:
    user_input = input("> ")

    if user_input in ["exit", "quit"]:
        break

    event = {"input": user_input}

    result = kernel.run(event)

    print("\n", result)
