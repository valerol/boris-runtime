from uuid import uuid4


class WebAdapter:

    def __init__(self, kernel):
        self.kernel = kernel

    def normalize(self, payload):
        return {
            "session_id": str(payload.get("session_id", "web")),
            "input": str(payload.get("input", "")),
            "meta": {
                **payload.get("meta", {}),
                "source": "web"
            }
        }

    def handle(self, payload):
        trace_id = str(uuid4())
        event = self.normalize(payload)
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
