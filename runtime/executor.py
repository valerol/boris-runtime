import json

from runtime.state import ALLOWED_OUTPUT_TYPES, ProtocolOutput


class ProtocolResponseParser:
    """Strict parser from LLM text to protocol output schema."""

    def parse(self, raw_output):
        text = (raw_output or "").strip()
        parsed_json = self._parse_json_object(text)
        if parsed_json:
            return parsed_json

        output_type, separator, content = text.partition(":")
        normalized_type = output_type.strip().upper()

        if not separator or normalized_type not in ALLOWED_OUTPUT_TYPES:
            return ProtocolOutput(
                "GAP",
                "LLM output did not match the protocol schema.",
                {
                    "raw_output": text,
                    "validation_error": "malformed_llm_output",
                },
            )

        return ProtocolOutput(
            normalized_type,
            content.strip(),
            {"raw_output": text},
        )

    @staticmethod
    def _parse_json_object(text):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return None

        if not isinstance(value, dict):
            return None

        return ProtocolOutput(
            str(value.get("type", "")).upper(),
            str(value.get("content", "")),
            value.get("metadata", {}) if isinstance(value.get("metadata", {}), dict) else {},
        )


class ToolStub:
    """Tool boundary stub. It does not execute real tools."""

    def handle(self, output):
        return ProtocolOutput(
            "TOOL_CALL",
            output.content,
            {
                **output.metadata,
                "tool_status": "stubbed",
                "tool_execution": "not_executed",
            },
        )


class DecisionExecutor:
    """Evaluates parsed protocol output and applies non-agentic decisions."""

    def __init__(self, tool_stub=None):
        self.tool_stub = tool_stub or ToolStub()

    def evaluate(self, output):
        if output.type == "TOOL_CALL":
            return self.tool_stub.handle(output)
        return output
