class CoreSurfaceError(ValueError):
    """Base error for rejected Core Surface packages."""


class PackageLayoutError(CoreSurfaceError):
    """The package cannot be read without ambiguous or unsafe paths."""


class ManifestError(CoreSurfaceError):
    """The package manifest is missing, malformed, or inconsistent."""


class IntegrityError(CoreSurfaceError):
    """The package inventory, dependency order, size, or hash is invalid."""


class LifecycleError(CoreSurfaceError):
    """The requested use is not allowed by the package lifecycle state."""


class CatalogError(CoreSurfaceError):
    """A passive canonical catalog cannot be represented faithfully."""
