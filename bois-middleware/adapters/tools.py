class ToolAdapter:
    """External tool interface. Tool execution belongs to the host platform."""

    def call(self, name, arguments):
        raise NotImplementedError


class EchoToolAdapter(ToolAdapter):
    def call(self, name, arguments):
        if name != "echo":
            return f"Tool '{name}' is not available."
        return arguments.get("text", "")

