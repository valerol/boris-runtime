from typing import Any

from pydantic import BaseModel, Field, constr


class BorisFrameRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: str = "default"
    context: dict[str, Any] = Field(default_factory=dict)
