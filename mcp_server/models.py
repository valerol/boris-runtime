from typing import Any

from pydantic import BaseModel, Field, constr, model_validator


class BorisOperatorInput(BaseModel):
    statement: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    resolved_unknowns: list[str] | None = None


class BorisExecuteResume(BaseModel):
    continuation_token: constr(strip_whitespace=True, min_length=1)
    operator_input: str | BorisOperatorInput


class BorisExecuteRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1) | None = None
    session_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    resume: BorisExecuteResume | None = None

    @model_validator(mode="after")
    def validate_route(self):
        if (self.input is None) == (self.resume is None):
            raise ValueError(
                "Provide exactly one of input or resume."
            )
        if self.resume is not None and self.context:
            raise ValueError(
                "Continuation context is bound by continuation_token."
            )
        return self
