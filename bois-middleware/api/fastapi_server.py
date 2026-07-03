from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.llm import MockLLMAdapter
from runtime.engine import MiddlewareEngine

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ModuleNotFoundError as exc:
    raise RuntimeError("FastAPI server requires optional fastapi and pydantic packages.") from exc


class Request(BaseModel):
    input: str
    context: dict = {}


app = FastAPI(title="BOIS Middleware SDK")
engine = MiddlewareEngine(MockLLMAdapter())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run(request: Request):
    response = engine.run(request.input, context=request.context)
    return {
        "type": response.type,
        "content": response.content,
        "tool_request": response.tool_request,
        "trace": response.trace,
    }

