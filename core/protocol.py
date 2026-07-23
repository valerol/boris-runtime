from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProtocolResponse:
    """Compatibility response returned by the pre-Phase-4 SDK facade."""

    type: str
    content: str
    trace: Mapping[str, Any] = field(default_factory=dict)
    tool_request: Mapping[str, Any] | None = None
