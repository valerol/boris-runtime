"""Compatibility facade for the pre-Phase-4 canonical SDK entrypoint."""

import json

from core.protocol import ProtocolResponse
from runtime.runtime import BOISRuntime


class MiddlewareEngine:
    """Deprecated facade that delegates all execution to ``BOISRuntime``."""

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
        if any((
            loader,
            prompt_builder,
            response_parser,
            protocol_loop,
            memory_adapter,
            tool_adapter,
        )):
            raise ValueError(
                "Legacy MiddlewareEngine component injection is no longer "
                "supported; use BOISRuntime composition boundaries."
            )
        self.runtime = BOISRuntime(
            llm_adapter=_canonical_llm_port(llm_adapter),
        )

    def run(self, user_input, context=None):
        text = (user_input or "").strip()
        if not text:
            return ProtocolResponse(
                type="clarification",
                content="Please provide a request.",
                trace={
                    "compatibility_facade": True,
                    "canonical_output_type": None,
                    "context_received": bool(context),
                },
            )
        output = self.runtime.run(text)
        output_type = output["type"]
        if output_type in {"QUESTION", "GAP"}:
            response_type = "clarification"
        elif output_type == "TOOL_CALL":
            response_type = "tool_call"
        else:
            response_type = "final"
        return ProtocolResponse(
            type=response_type,
            content=output["content"],
            trace={
                "compatibility_facade": True,
                "canonical_output_type": output_type,
                "context_received": bool(context),
            },
        )


class _CompletePortBridge:
    def __init__(self, adapter):
        self.adapter = adapter
        self.adapter_name = getattr(adapter, "adapter_name", "legacy-complete")

    def call(self, prompt):
        raw = self.adapter.complete(prompt)
        text = (raw or "").strip()
        prefixes = {
            "CLARIFY:": "QUESTION",
            "FINAL:": "ANSWER",
        }
        for prefix, output_type in prefixes.items():
            if text.upper().startswith(prefix):
                text = text.split(":", 1)[1].strip()
                break
        else:
            output_type = "ANSWER"
        return json.dumps({
            "type": output_type,
            "content": text,
            "metadata": {"compatibility_adapter": True},
        })

    def call_structured(self, prompt, system_message):
        raise NotImplementedError(
            "Legacy complete()-only adapters cannot provide structured calls."
        )


def _canonical_llm_port(adapter):
    if hasattr(adapter, "call"):
        return adapter
    if hasattr(adapter, "complete"):
        return _CompletePortBridge(adapter)
    raise TypeError("LLM adapter must implement call() or legacy complete().")
