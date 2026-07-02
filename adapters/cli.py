from kernel.runtime import BORISKernel
from runtime.engine import BORISRuntimeEngine
from core.loader import SchemaLoader

kernel = BORISKernel()
schema = SchemaLoader().schema
engine = BORISRuntimeEngine(kernel, schema)

print("BORIS RUNTIME v0 READY")

while True:

    user_input = input("> ")

    event = {"input": user_input}

    while True:

        result = engine.step(event)

        if isinstance(result, dict) and result.get("type") == "FINAL":
            print(result)
            break

        if isinstance(result, dict) and result.get("type") == "QUESTION":
            print("ASK:", result["content"])
            break
