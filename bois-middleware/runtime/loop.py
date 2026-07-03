from core.protocol import ProtocolResponse


class ProtocolLoop:
    """Chooses the protocol envelope after parsing an LLM response."""

    def decide(self, parsed):
        if parsed.kind == "clarification":
            return ProtocolResponse("clarification", parsed.content)

        if parsed.kind == "tool":
            return ProtocolResponse(
                "tool_call",
                "",
                tool_request={
                    "name": parsed.tool_name,
                    "arguments": dict(parsed.tool_args),
                },
            )

        return ProtocolResponse("final", parsed.content)

