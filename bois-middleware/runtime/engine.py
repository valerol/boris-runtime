from core.loader import CoreLoader
from core.protocol import ProtocolRequest, ProtocolResponse
from runtime.loop import ProtocolLoop
from runtime.prompt_builder import PromptBuilder
from runtime.response_parser import ResponseParser


class MiddlewareEngine:
    """Stateless BOIS / SIMA / BORIS protocol execution engine."""

    def __init__(
        self,
        llm_adapter,
        loader=None,
        prompt_builder=None,
        response_parser=None,
        protocol_loop=None,
        memory_adapter=None,
        tool_adapter=None,
    ):
        self.llm_adapter = llm_adapter
        self.loader = loader or CoreLoader()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.response_parser = response_parser or ResponseParser()
        self.protocol_loop = protocol_loop or ProtocolLoop()
        self.memory_adapter = memory_adapter
        self.tool_adapter = tool_adapter

    def run(self, user_input, context=None):
        request = ProtocolRequest(user_input=(user_input or "").strip(), context=context or {})

        if not request.user_input:
            return ProtocolResponse("clarification", "Please provide a request.")

        definitions = self.loader.load()
        memory_context = self._read_memory(request)
        prompt = self.prompt_builder.build(definitions, request, memory_context)
        raw_response = self.llm_adapter.complete(prompt, context=dict(request.context))
        parsed = self.response_parser.parse(raw_response)
        response = self.protocol_loop.decide(parsed)

        if response.type == "tool_call" and self.tool_adapter:
            tool_result = self.tool_adapter.call(
                response.tool_request["name"],
                response.tool_request["arguments"],
            )
            return ProtocolResponse(
                "final",
                str(tool_result),
                trace={"tool_executed": response.tool_request["name"]},
            )

        self._write_memory(request, response)
        return response

    def _read_memory(self, request):
        if not self.memory_adapter:
            return None
        return self.memory_adapter.read(dict(request.context))

    def _write_memory(self, request, response):
        if self.memory_adapter:
            self.memory_adapter.write(
                {"input": request.user_input, "response": response.content}
            )

