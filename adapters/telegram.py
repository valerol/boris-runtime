from uuid import uuid4


class TelegramAdapter:

    def __init__(self, kernel):
        self.kernel = kernel

    def normalize(self, text, session_id="telegram"):
        return {
            "session_id": session_id,
            "input": text,
            "meta": {
                "source": "telegram"
            }
        }

    def handle(self, text, session_id="telegram"):
        trace_id = str(uuid4())
        result = self.kernel.run(self.normalize(text, session_id=session_id))
        response_type = result.get("type", "ERROR")
        answer = result.get("answer", result.get("content", ""))
        return {
            "type": response_type,
            "answer": answer,
            "content": answer,
            "trace": result.get("trace", {}),
            "state": result.get("state", {}),
            "actions": result.get("actions", []),
            "trace_id": trace_id,
            "meta": {
                "requires_user_input": response_type == "CLARIFICATION"
            }
        }
