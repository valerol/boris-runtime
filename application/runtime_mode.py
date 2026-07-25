import os


def developer_mode_enabled() -> bool:
    return os.getenv("BORIS_RUNTIME_MODE", "").strip().lower() == "dev"
