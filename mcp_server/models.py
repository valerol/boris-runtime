from typing import Any, Literal

from pydantic import BaseModel, Field, constr


ProtocolOutputType = Literal["ANSWER", "QUESTION", "TOOL_CALL", "GAP"]


class BorisAskRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: str = "default"
    context: dict[str, Any] = Field(default_factory=dict)


class BorisFrameRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: str = "default"
    context: dict[str, Any] = Field(default_factory=dict)


class BorisValidateRequest(BaseModel):
    answer: constr(strip_whitespace=True, min_length=1)
    context_packet: dict[str, Any]
    validation_mode: Literal["deterministic", "semantic", "hybrid"] = "deterministic"


class BorisAskResponse(BaseModel):
    session_id: str
    type: ProtocolOutputType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BorisAskError(BaseModel):
    error: str
    detail: str
    session_id: str | None = None
