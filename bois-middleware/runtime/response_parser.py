import json

from core.protocol import ParsedResponse


class ResponseParser:
    """Parses a narrow response contract without interpreting model reasoning."""

    def parse(self, raw_text):
        text = (raw_text or "").strip()

        if text.upper().startswith("CLARIFY:"):
            return ParsedResponse("clarification", text.split(":", 1)[1].strip())

        if text.upper().startswith("TOOL:"):
            return self._parse_tool(text.split(":", 1)[1].strip())

        if text.upper().startswith("FINAL:"):
            return ParsedResponse("final", text.split(":", 1)[1].strip())

        return ParsedResponse("final", text)

    def _parse_tool(self, body):
        name, _, raw_args = body.partition(" ")
        args = {}
        if raw_args.strip():
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    args = parsed
            except json.JSONDecodeError:
                args = {"raw": raw_args.strip()}
        return ParsedResponse("tool", "", tool_name=name.strip(), tool_args=args)

