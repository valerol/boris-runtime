from fastapi import FastAPI
from pydantic import BaseModel, Field

from adapters.web import WebAdapter
from kernel.runtime import BORISKernel


class EventRequest(BaseModel):
    session_id: str = "web"
    input: str
    meta: dict = Field(default_factory=dict)


app = FastAPI(title="BORIS Runtime v0")
adapter = WebAdapter(BORISKernel())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/event")
def event(req: EventRequest):
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return adapter.handle(payload)
