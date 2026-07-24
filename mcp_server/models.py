from typing import Any, Literal

from pydantic import BaseModel, Field, constr


class BorisFrameRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: Literal["default", "production", "developer"] = "default"
    context: dict[str, Any] = Field(default_factory=dict)
