"""Compatibility server backed by the canonical BORIS Runtime path."""

from adapters.llm import MockLLMAdapter
from api.app import app
from pydantic import BaseModel, Field
from runtime.engine import MiddlewareEngine


class Request(BaseModel):
    input: str
    context: dict = Field(default_factory=dict)


engine = MiddlewareEngine(MockLLMAdapter())


@app.post("/run", deprecated=True)
def run(request: Request):
    response = engine.run(request.input, context=request.context)
    return {
        "type": response.type,
        "content": response.content,
        "tool_request": response.tool_request,
        "trace": response.trace,
    }


__all__ = ["Request", "app", "run"]
