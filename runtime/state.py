from dataclasses import dataclass, field


ALLOWED_OUTPUT_TYPES = {"ANSWER", "QUESTION", "TOOL_CALL", "GAP"}


@dataclass
class ProtocolOutput:
    type: str
    content: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        output_type = self.type if self.type in ALLOWED_OUTPUT_TYPES else "GAP"
        return {
            "type": output_type,
            "content": str(self.content or ""),
            "metadata": dict(self.metadata or {}),
        }


@dataclass
class RuntimeState:
    gap_registry: dict = field(default_factory=dict)
    question_memory: list = field(default_factory=list)
    clarification_cycles: int = 0
    max_clarification_cycles: int = 3
    current_input: str = ""
    last_output_type: str | None = None

    def has_asked_about(self, field_name):
        return any(item["field"] == field_name for item in self.question_memory)

    def register_gap(self, missing_fields, question):
        for field_name in missing_fields:
            self.gap_registry[field_name] = {
                "question": question,
                "asked": self.has_asked_about(field_name),
            }

    def remember_question(self, field_name, question):
        if not self.has_asked_about(field_name):
            self.question_memory.append({
                "field": field_name,
                "question": question,
            })

    def can_clarify(self):
        return self.clarification_cycles < self.max_clarification_cycles

    def record_clarification(self, user_input):
        self.clarification_cycles += 1
        self.current_input = f"{self.current_input}\nClarification: {user_input}"

    def snapshot(self):
        return {
            "gap_registry": dict(self.gap_registry),
            "question_memory": list(self.question_memory),
            "clarification_cycles": self.clarification_cycles,
            "max_clarification_cycles": self.max_clarification_cycles,
            "last_output_type": self.last_output_type,
        }

