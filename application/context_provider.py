from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from application.context_packet import build_context_packet
from application.context_projection import project_core_context
from core_surface import CoreSurfaceError, load_core_surface


DEFAULT_CORE_SURFACE_SOURCE = "/opt/boris-core"


class CoreSurfaceUnavailable(RuntimeError):
    """Raised when the configured canonical package cannot be loaded."""


class CoreSurfaceProvider:
    """Lazy, process-local owner of one immutable Core Surface."""

    def __init__(self, source: str | None = None):
        self._source = source
        self._lock = Lock()
        self._cached_source = None
        self._surface = None

    def get(self):
        source = self._resolve_source()
        with self._lock:
            if self._surface is not None and source == self._cached_source:
                return self._surface
            try:
                surface = load_core_surface(source, purpose="evaluation")
            except (CoreSurfaceError, OSError) as exc:
                raise CoreSurfaceUnavailable(
                    "The configured Core Surface package is unavailable or invalid."
                ) from exc
            self._surface = surface
            self._cached_source = source
            return surface

    def clear(self):
        with self._lock:
            self._cached_source = None
            self._surface = None

    def _resolve_source(self) -> str:
        return (
            self._source
            or os.getenv("BORIS_CORE_PACKAGE")
            or DEFAULT_CORE_SURFACE_SOURCE
        )


@dataclass(frozen=True)
class FrameContext:
    user_input: str
    sima: dict
    bois_frame: dict
    boris_context: dict
    core_projection: dict


class ContextProvider:
    """Build a read-only ChatGPT frame from a verified Core Surface."""

    def __init__(self, surface_provider=None):
        self.surface_provider = surface_provider or CoreSurfaceProvider()

    def frame(self, user_input: str, session_id: str | None = None) -> dict:
        text = str(user_input or "").strip()
        if not text:
            raise ValueError("Context frame input must not be empty.")
        resolved_session_id = session_id or str(uuid4())
        surface = self.surface_provider.get()
        core_projection = project_core_context(surface, text)
        frame_context = FrameContext(
            user_input=text,
            sima=_sima_signals(text),
            bois_frame=_bois_frame(surface, text),
            boris_context=_boris_context(surface, resolved_session_id),
            core_projection=core_projection,
        )
        return build_context_packet(resolved_session_id, frame_context)


def _sima_signals(user_input: str) -> dict:
    missing_fields = ["request"] if not user_input else []
    return {
        "risk": 0.5 if missing_fields else 0.2,
        "uncertainty": 0.6 if missing_fields else 0.2,
        "missing_fields": missing_fields,
        "ambiguity_score": 0.5 if missing_fields else 0.1,
    }


def _bois_frame(surface, user_input: str) -> dict:
    return {
        "framework": "BOIS",
        "core": {
            "projection": "core_surface",
            "package_identity": dict(surface.package_identity),
            "status": surface.status,
            "purpose": surface.purpose,
            "content_set_sha256": surface.content_set_sha256,
            "manifest_sha256": surface.manifest_sha256,
        },
        "input": user_input,
        "constraints": [
            "do_not_invent_facts",
            "treat_core_surface_as_passive_canonical_projection",
            "do_not_claim_runtime_activation_or_execution",
        ],
    }


def _boris_context(surface, session_id: str) -> dict:
    return {
        "name": "BORIS",
        "role": "operator/domain specialization",
        "context": {
            "core_projection": "core_surface",
            "package_identity": dict(surface.package_identity),
            "domain_physiology": "not_attached",
        },
        "session": {
            "session_id": session_id,
            "clarification_cycles": 0,
            "max_clarification_cycles": 3,
        },
    }
