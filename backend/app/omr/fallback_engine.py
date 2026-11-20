"""Motor con respaldo: prueba un lector principal (rápido) y, si falla, usa otro (lento).

Hoy: Audiveris (~10–60 s por página) y, de respaldo, oemer (~5 min por página).
"Falla" es: lanza un error, o devuelve un MusicXML sin compases o sin ninguna nota.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from .base import OmrEngine, current_subject, report_progress, report_warning

log = logging.getLogger(__name__)

FALLBACK_PROGRESS = "La lectura rápida no funcionó con {subject}; usé el lector lento, puede tardar unos minutos"
FALLBACK_WARNING = "La lectura rápida no funcionó con {subject}; se leyó con el lector lento."


def has_music(xml: str) -> bool:
    """True si el MusicXML tiene al menos un compás con una nota (no solo silencios)."""
    try:
        root = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError:
        return False
    return any(m.find("note/pitch") is not None for m in root.iter("measure"))


class FallbackEngine:
    def __init__(self, primary: OmrEngine, fallback: OmrEngine):
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}+{fallback.name}"

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        try:
            xml = self.primary.recognize(image_path, work_dir)
            if has_music(xml):
                return xml
            log.warning("%s no encontró notas en %s; paso a %s", self.primary.name, image_path, self.fallback.name)
        except Exception:  # cualquier falla del principal: se intenta con el respaldo
            log.warning(
                "%s falló con %s; paso a %s", self.primary.name, image_path, self.fallback.name, exc_info=True
            )
        subject = current_subject()
        report_progress(FALLBACK_PROGRESS.format(subject=subject))
        report_warning(FALLBACK_WARNING.format(subject=subject))
        return self.fallback.recognize(image_path, work_dir)
