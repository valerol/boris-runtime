class RuntimeCompatibilityError(ValueError):
    """Base error for the Core Surface to Runtime compatibility boundary."""


class RuntimeContractError(RuntimeCompatibilityError):
    """The package runtime contract is missing, invalid, or unsupported."""


class RuntimeInstanceValidationError(RuntimeContractError):
    """A value does not conform to a valid package-owned schema."""


class RuntimeAttestationError(RuntimeCompatibilityError):
    """A Runtime attestation is invalid or does not authorize the requested scope."""
