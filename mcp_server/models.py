from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, constr, model_validator


class BorisOperatorInput(BaseModel):
    resolution_mode: Literal[
        "PROVIDE_INFORMATION",
        "CONFIRM_ASSUMPTION",
        "ALLOW_CONDITIONAL_PROCEEDING",
        "CHANGE_SCOPE",
        "TERMINATE_CYCLE",
    ]
    statement: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    resolved_unknowns: list[str] | None = None
    scope: "BorisOperatorScopeChange | None" = None


class BorisOperatorScopeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_layers: list[str] | None = None
    triggers: list[str] | None = None
    applicability_scopes: list[str] | None = None
    requested_norm_refs: list[str] | None = None

    @model_validator(mode="after")
    def require_selector(self):
        if all(
            value is None
            for value in (
                self.active_layers,
                self.triggers,
                self.applicability_scopes,
                self.requested_norm_refs,
            )
        ):
            raise ValueError(
                "Operator scope change requires at least one selector array."
            )
        return self


class BorisExecuteResume(BaseModel):
    continuation_token: constr(strip_whitespace=True, min_length=1)
    operator_input: BorisOperatorInput


class BorisExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
