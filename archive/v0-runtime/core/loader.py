import json
from pathlib import Path

class SchemaLoader:

    def __init__(self, path=None):
        schema_path = Path(path) if path else Path(__file__).with_name("schema.json")
        with schema_path.open("r", encoding="utf-8") as f:
            self.schema = json.load(f)

    def get_entry(self):
        return self.schema["entrypoint"]

    def get_state(self, state_name):
        return self.schema["states"][state_name]


class EpistemicHierarchyLoader:

    def __init__(self, path=None):
        hierarchy_path = (
            Path(path) if path else Path(__file__).with_name("epistemic_hierarchy.json")
        )
        with hierarchy_path.open("r", encoding="utf-8") as f:
            self.hierarchy = json.load(f)
