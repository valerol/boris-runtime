class SemanticExecutorError(ValueError):
    """Base error for the isolated Phase 4F semantic execution boundary."""


class SemanticViewError(SemanticExecutorError):
    """The Core Surface cannot be projected into a compatible semantic view."""


class SemanticCalculationError(SemanticExecutorError):
    """The semantic calculator returned an invalid or ungrounded calculation."""


class SemanticCompatibilityError(SemanticExecutorError):
    """Runtime compatibility does not permit this semantic evaluation."""
