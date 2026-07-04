from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from core.loader import load_core
from runtime.state import RuntimeState


@dataclass(frozen=True)
class RuntimeSession:
    session_id: str
    core: object
    state: RuntimeState
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def create_runtime_session(core_ref="core/definitions", session_id=None):
    resolved_session_id = session_id or str(uuid4())
    immutable_core = load_core(core_ref)
    state = RuntimeState(session_id=resolved_session_id)
    return RuntimeSession(
        session_id=resolved_session_id,
        core=immutable_core,
        state=state,
    )

