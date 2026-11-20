"""Interfaz común para los lectores OMR.

Cada motor recibe la ruta de UNA imagen de una página y devuelve el MusicXML
de esa página como texto. Así se puede cambiar oemer por homr o Audiveris
sin tocar el resto del backend.

Los motores pueden avisar cosas al trabajo en curso (mensaje de progreso o un aviso
para el usuario) con `report_progress` y `report_warning`. `jobs.py` los conecta con
`notifying(...)`; si nadie escucha (por ejemplo, en una prueba), no pasa nada.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class OmrError(RuntimeError):
    """El motor no pudo leer la página."""


class OmrEngine(Protocol):
    name: str

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        """Lee la imagen y devuelve MusicXML. Puede usar work_dir para archivos temporales."""
        ...


@dataclass
class Notifier:
    progress: Callable[[str], None]
    warning: Callable[[str], None]
    # Cómo nombrar lo que se está leyendo en los mensajes: "esta foto", "la página 2"…
    subject: str = "esta página"


_current: ContextVar[Notifier | None] = ContextVar("omr_notifier", default=None)


@contextmanager
def notifying(notifier: Notifier) -> Iterator[None]:
    token = _current.set(notifier)
    try:
        yield
    finally:
        _current.reset(token)


def current_subject() -> str:
    n = _current.get()
    return n.subject if n is not None else "esta página"


def report_progress(text: str) -> None:
    n = _current.get()
    if n is not None:
        n.progress(text)


def report_warning(text: str) -> None:
    n = _current.get()
    if n is not None:
        n.warning(text)
