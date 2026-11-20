"""Interfaz común para los lectores OMR.

Cada motor recibe la ruta de UNA imagen de una página y devuelve el MusicXML
de esa página como texto. Así se puede cambiar oemer por homr o Audiveris
sin tocar el resto del backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class OmrError(RuntimeError):
    """El motor no pudo leer la página."""


class OmrEngine(Protocol):
    name: str

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        """Lee la imagen y devuelve MusicXML. Puede usar work_dir para archivos temporales."""
        ...
