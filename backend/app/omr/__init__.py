from .audiveris_engine import AudiverisEngine, find_audiveris
from .base import OmrEngine, OmrError
from .fallback_engine import FallbackEngine
from .oemer_engine import OemerEngine

__all__ = ["AudiverisEngine", "FallbackEngine", "OmrEngine", "OmrError", "OemerEngine", "default_engine", "find_audiveris"]


def default_engine() -> OmrEngine:
    """Audiveris (rápido) con oemer de respaldo; si Audiveris no está instalado, solo oemer."""
    exe = find_audiveris()
    if exe is None:
        return OemerEngine()
    return FallbackEngine(AudiverisEngine(exe), OemerEngine())
