from threading import Lock

from runtime.config import build_llm_adapter
from runtime.runtime import BOISRuntime


class RuntimeRegistry:
    def __init__(self):
        self._lock = Lock()
        self._runtimes = {}

    def get_or_create(self, session_id):
        with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                runtime = BOISRuntime(
                    session_id=session_id,
                    llm_adapter=build_llm_adapter(),
                )
                self._runtimes[session_id] = runtime
            return runtime

    def get(self, session_id):
        with self._lock:
            return self._runtimes.get(session_id)

    def clear(self):
        with self._lock:
            self._runtimes.clear()
