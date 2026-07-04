class QuestionMemory:
    def __init__(self, state):
        self.state = state

    def has_asked(self, question: str) -> bool:
        return any(
            item.get("question") == question
            for item in self.state.asked_questions
        )

    def remember(self, question: str, gap_key: str | None):
        if self.has_asked(question):
            return
        self.state.asked_questions.append({
            "question": question,
            "gap_key": gap_key,
            "field": gap_key,
        })

    def unresolved_gaps(self) -> list:
        return [
            {
                "gap_key": key,
                **value,
            }
            for key, value in self.state.gap_registry.items()
            if not value.get("resolved", False)
        ]

