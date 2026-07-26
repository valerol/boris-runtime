from typing import Any, Literal

from pydantic import BaseModel, Field, constr, model_validator


class BorisOperatorInput(BaseModel):
    statement: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    resolved_unknowns: list[str] | None = None


class BorisExecuteResume(BaseModel):
    continuation_token: constr(strip_whitespace=True, min_length=1)
    operator_input: str | BorisOperatorInput


class BorisExecuteRequest(BaseModel):
    operation: Literal["execute", "prepare", "submit"] = "execute"
    input: constr(strip_whitespace=True, min_length=1) | None = None
    session_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    resume: BorisExecuteResume | None = None
    work_order_id: constr(strip_whitespace=True, min_length=1) | None = None
    work_order_token: constr(strip_whitespace=True, min_length=1) | None = None
    semantic_input: dict[str, Any] | None = None
    semantic_result: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_route(self):
        host_fields = (
            self.work_order_id,
            self.work_order_token,
            self.semantic_input,
            self.semantic_result,
        )
        if self.operation in {"execute", "prepare"}:
            if (self.input is None) == (self.resume is None):
                raise ValueError(
                    "Provide exactly one of input or resume."
                )
            if self.resume is not None and self.context:
                raise ValueError(
                    "Continuation context is bound by continuation_token."
                )
            if any(value is not None for value in host_fields):
                raise ValueError(
                    "Host submission fields are allowed only in submit mode."
                )
        else:
            if self.input is not None or self.resume is not None or self.context:
                raise ValueError(
                    "Submit mode cannot replace work-order-bound input or context."
                )
            if self.work_order_id is None or self.work_order_token is None:
                raise ValueError(
                    "Submit mode requires work_order_id and work_order_token."
                )
            if (self.semantic_input is None) == (
                self.semantic_result is None
            ):
                raise ValueError(
                    "Submit mode requires exactly one of semantic_input or "
                    "semantic_result."
                )
        return self
