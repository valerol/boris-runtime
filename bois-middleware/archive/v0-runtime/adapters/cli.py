from uuid import uuid4


class CLIAdapter:

    def __init__(self, kernel):
        self.kernel = kernel

    def normalize(self, user_input, session_id="cli"):
        return {
            "session_id": session_id,
            "input": user_input,
            "meta": {
                "source": "cli"
            }
        }

    def handle(self, user_input, session_id="cli"):
        trace_id = str(uuid4())
        event = self.normalize(user_input, session_id=session_id)
        return self.format_response(self.kernel.run(event), trace_id)

    def format_response(self, result, trace_id):
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
