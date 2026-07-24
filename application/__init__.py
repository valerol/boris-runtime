__all__ = [
    "ContextProvider",
    "CoreSurfaceProvider",
    "ValidationEngine",
]


def __getattr__(name):
    if name in {"ContextProvider", "CoreSurfaceProvider"}:
        from application.context_provider import ContextProvider, CoreSurfaceProvider

        return {
            "ContextProvider": ContextProvider,
            "CoreSurfaceProvider": CoreSurfaceProvider,
        }[name]
    if name == "ValidationEngine":
        from application.validation import ValidationEngine

        return ValidationEngine
    raise AttributeError(name)
