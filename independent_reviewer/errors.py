class IndependentReviewerError(RuntimeError):
    """Base error for the fail-closed Independent Reviewer boundary."""


class IndependentReviewBindingError(IndependentReviewerError):
    """The review input is not bound to the active Runtime calculation."""


class IndependentReviewOutputError(IndependentReviewerError):
    """The independent review output does not satisfy its strict contract."""
