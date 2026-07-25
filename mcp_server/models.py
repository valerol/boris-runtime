from typing import Any

from pydantic import BaseModel, Field, constr


class BorisExecuteRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
