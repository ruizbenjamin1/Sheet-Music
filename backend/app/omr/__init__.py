import logging

from .audiveris_engine import AudiverisEngine, find_audiveris
from .base import OmrEngine, OmrError
from .claude_engine import ClaudeEngine, claude_enabled, find_claude_cli
from .fallback_engine import AI_FALLBACK_PROGRESS, AI_FALLBACK_WARNING, FallbackEngine
from .oemer_engine import OemerEngine

__all__ = [
    "AudiverisEngine",
    "ClaudeEngine",
    "FallbackEngine",
    "OmrEngine",
    "OmrError",
    "OemerEngine",
    "default_engine",
    "find_audiveris",
    "find_claude_cli",
]

log = logging.getLogger(__name__)


def default_engine() -> OmrEngine:
    """Audiveris (rápido) con oemer de respaldo; si Audiveris no está instalado, solo oemer.

    Solo en desarrollo: con `OMR_USE_CLAUDE=1` y el CLI de Claude Code instalado, primero se lee
    con IA y, si falla, con lo de siempre.
    """
    exe = find_audiveris()
    engine: OmrEngine = OemerEngine() if exe is None else FallbackEngine(AudiverisEngine(exe), OemerEngine())
    if claude_enabled():
        cli = find_claude_cli()
        if cli is None:
            log.warning("OMR_USE_CLAUDE=1 pero no encontré el CLI de Claude Code; no se usa el lector con IA")
        else:
            engine = FallbackEngine(ClaudeEngine(cli), engine, AI_FALLBACK_PROGRESS, AI_FALLBACK_WARNING)
    return engine
