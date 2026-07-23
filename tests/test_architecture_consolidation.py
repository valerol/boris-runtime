import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = PROJECT_ROOT / "archive" / "v0-runtime"
ACTIVE_PREFIXES = ("adapters", "api", "core", "llm", "prompt", "protocol", "runtime")


def test_old_fastapi_module_exports_the_canonical_app():
    with activate_runtime_imports():
        from api.app import app as canonical_app
        from api.fastapi_server import app as compatibility_app

        assert compatibility_app is canonical_app


def test_old_run_endpoint_delegates_to_canonical_runtime():
    with activate_runtime_imports():
        from api.fastapi_server import app

        response = TestClient(app).post(
            "/run",
            json={
                "input": "Use the canonical Runtime path.",
                "context": {"source": "legacy-client"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["type"] == "final"
        assert payload["trace"]["compatibility_facade"] is True
        assert payload["trace"]["context_received"] is True


def test_middleware_engine_is_only_a_bois_runtime_compatibility_facade():
    with activate_runtime_imports():
        from adapters.llm import MockLLMAdapter
        from runtime.engine import MiddlewareEngine
        from runtime.runtime import BOISRuntime

        engine = MiddlewareEngine(MockLLMAdapter())

        response = engine.run("Use the canonical Runtime path.")

        assert isinstance(engine.runtime, BOISRuntime)
        assert response.type == "final"
        assert response.trace["compatibility_facade"] is True
        assert response.trace["canonical_output_type"] == "ANSWER"

        empty = engine.run("   ")
        assert empty.type == "clarification"
        assert empty.content == "Please provide a request."


def test_middleware_engine_rejects_parallel_component_injection():
    with activate_runtime_imports():
        from adapters.llm import MockLLMAdapter
        from runtime.engine import MiddlewareEngine

        with pytest.raises(ValueError, match="no longer supported"):
            MiddlewareEngine(
                MockLLMAdapter(),
                prompt_builder=object(),
            )


@contextmanager
def activate_runtime_imports():
    saved_path = list(sys.path)
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if (
            name in ACTIVE_PREFIXES
            or name.startswith(
                tuple(f"{prefix}." for prefix in ACTIVE_PREFIXES)
            )
        )
    }
    for path in (str(ARCHIVE_ROOT), str(PROJECT_ROOT)):
        if path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, str(PROJECT_ROOT))
    for name in list(sys.modules):
        if (
            name in ACTIVE_PREFIXES
            or name.startswith(
                tuple(f"{prefix}." for prefix in ACTIVE_PREFIXES)
            )
        ):
            sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if (
                name in ACTIVE_PREFIXES
                or name.startswith(
                    tuple(f"{prefix}." for prefix in ACTIVE_PREFIXES)
                )
            ):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path
