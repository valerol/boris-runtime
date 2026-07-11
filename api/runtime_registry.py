from dataclasses import dataclass
from threading import Lock

from runtime.config import build_lazy_llm_adapter, build_lazy_validator_llm_adapter
from runtime.runtime import BOISRuntime
from runtime.validation import ValidationEngine


@dataclass
class RuntimeHandle:
    runtime: BOISRuntime
    lock: Lock


class RuntimeRegistry:
    def __init__(self):
        self._lock = Lock()
        self._handles = {}

    def _get_or_create_handle(self, session_id):
        with self._lock:
            handle = self._handles.get(session_id)
            if handle is None:
                runtime = BOISRuntime(
                    session_id=session_id,
                    llm_adapter=build_lazy_llm_adapter(),
                )
                handle = RuntimeHandle(runtime=runtime, lock=Lock())
                self._handles[session_id] = handle
            return handle

    def get_or_create(self, session_id):
        return self._get_or_create_handle(session_id).runtime

    def run(self, session_id, user_input):
        handle = self._get_or_create_handle(session_id)
        with handle.lock:
            return handle.runtime.run(user_input)

    def frame(self, session_id, user_input):
        handle = self._get_or_create_handle(session_id)
        with handle.lock:
            return handle.runtime.frame(user_input)

    def validate(self, answer, context_packet, validation_mode="deterministic"):
        engine = ValidationEngine(
            validator_adapter_factory=lambda: build_lazy_validator_llm_adapter()
        )
        return engine.validate(
            answer=answer,
            context_packet=context_packet,
            validation_mode=validation_mode,
        )

    def reset(self, session_id):
        with self._lock:
            return self._handles.pop(session_id, None) is not None

    def exists(self, session_id):
        with self._lock:
            return session_id in self._handles

    def get_handle(self, session_id):
        with self._lock:
            return self._handles.get(session_id)

    def get(self, session_id):
        handle = self.get_handle(session_id)
        if handle:
            return handle.runtime
        return None

    def clear(self):
        with self._lock:
            self._handles.clear()
