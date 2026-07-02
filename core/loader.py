import json

class SchemaLoader:

    def __init__(self, path="core/schema.json"):
        with open(path, "r") as f:
            self.schema = json.load(f)

    def get_entry(self):
        return self.schema["entrypoint"]

    def get_state(self, state_name):
        return self.schema["states"][state_name]
