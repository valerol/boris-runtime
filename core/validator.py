class CoreValidationError(ValueError):
    pass


REQUIRED_TOP_LEVEL_FIELDS = {
    "bois_core",
    "sima_rules",
    "boris_context",
    "meta",
}

REQUIRED_META_FIELDS = {
    "source",
    "version",
    "hash",
}


def validate_core(core):
    if not isinstance(core, dict):
        raise CoreValidationError("Core must be a dictionary.")

    missing = REQUIRED_TOP_LEVEL_FIELDS - set(core)
    if missing:
        raise CoreValidationError(f"Missing core fields: {sorted(missing)}")

    meta = core.get("meta")
    if not isinstance(meta, dict):
        raise CoreValidationError("Core meta must be a dictionary.")

    missing_meta = REQUIRED_META_FIELDS - set(meta)
    if missing_meta:
        raise CoreValidationError(f"Missing meta fields: {sorted(missing_meta)}")

    if not isinstance(core["bois_core"], dict):
        raise CoreValidationError("bois_core must be a dictionary.")

    if not isinstance(core["sima_rules"], dict):
        raise CoreValidationError("sima_rules must be a dictionary.")

    if not isinstance(core["boris_context"], dict):
        raise CoreValidationError("boris_context must be a dictionary.")

    return core

