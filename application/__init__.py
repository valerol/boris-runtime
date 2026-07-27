__all__ = [
    "ContextProvider",
    "CoreSurfaceProvider",
    "ChatGPTHostProvider",
    "SemanticProvider",
    "ServerLLMProvider",
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
    if name in {
        "ChatGPTHostProvider",
        "SemanticProvider",
        "ServerLLMProvider",
    }:
        from application.semantic_provider import (
            ChatGPTHostProvider,
            SemanticProvider,
            ServerLLMProvider,
        )

        return {
            "ChatGPTHostProvider": ChatGPTHostProvider,
            "SemanticProvider": SemanticProvider,
            "ServerLLMProvider": ServerLLMProvider,
        }[name]
    raise AttributeError(name)
