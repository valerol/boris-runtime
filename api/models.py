from typing import Any, Literal

from pydantic import BaseModel, Field, constr


ProtocolOutputType = Literal["ANSWER", "QUESTION", "TOOL_CALL", "GAP"]


class RuntimeAskRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: str = "default"
    context: dict[str, Any] = Field(default_factory=dict)


class RuntimeAskResponse(BaseModel):
    session_id: str
    type: ProtocolOutputType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
    api: str
