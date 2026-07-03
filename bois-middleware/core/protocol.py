from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProtocolDefinitions:
    bois: str
    sima: str
    boris: str


@dataclass(frozen=True)
class ProtocolRequest:
    user_input: str
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedResponse:
    kind: str
    content: str
    tool_name: str | None = None
    tool_args: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProtocolResponse:
    type: str
    content: str
    trace: Mapping[str, Any] = field(default_factory=dict)
    tool_request: Mapping[str, Any] | None = None

