"""Convierte lo que sube el usuario (PDF o imagen) en imágenes de página listas para el OMR."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf as fitz

log = logging.getLogger(__name__)

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# Sufijo fijo del archivo temporal según el formato real (nunca el nombre que manda el usuario).
SUFFIXES = {"pdf": ".pdf", "png": ".png", "jpeg": ".jpg", "webp": ".webp"}

# Resolución a la que se rasteriza el PDF. 300 ppp es lo estándar para OMR.
PDF_DPI = 300
MAX_PAGES = 10

UNSUPPORTED = "Formato no soportado. Subí un PDF o una imagen (PNG, JPG o WEBP)."


class InputError(ValueError):
    """El archivo subido no sirve (tipo, tamaño o cantidad de páginas)."""


def kind_of(filename: str, content_type: str | None) -> str:
    """Tipo declarado por el navegador (nombre y content-type): "pdf" o "image"."""
    suffix = Path(filename or "").suffix.lower()
    if content_type in PDF_TYPES or suffix == ".pdf":
        return "pdf"
    if content_type in IMAGE_TYPES or suffix in IMAGE_SUFFIXES:
        return "image"
    raise InputError(UNSUPPORTED)


def sniff_format(head: bytes) -> str:
    """Mira los primeros bytes y devuelve el formato real: "pdf", "png", "jpeg" o "webp"."""
    # Algunos PDF traen basura antes de la cabecera; los lectores aceptan hasta 1 KB.
    if b"%PDF-" in head[:1024]:
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    raise InputError("El archivo no parece un PDF ni una imagen PNG, JPG o WEBP. ¿Puede estar dañado?")


def check_upload(filename: str, content_type: str | None, data: bytes) -> str:
    """Confirma con los primeros bytes que el archivo es lo que dice ser. Devuelve el formato."""
    declared = kind_of(filename, content_type)
    fmt = sniff_format(data[:1024])
    real = "pdf" if fmt == "pdf" else "image"
    if real != declared:
        raise InputError(
            "El archivo dice ser un PDF pero es una imagen, o al revés. Revisá que sea el archivo correcto."
        )
    return fmt


def kind_of_format(fmt: str) -> str:
    return "pdf" if fmt == "pdf" else "image"


def to_page_images(src: Path, kind: str, out_dir: Path) -> list[Path]:
    """Devuelve una imagen por página. Para imágenes es la misma imagen."""
    if kind == "image":
        return [src]

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        doc = fitz.open(src, filetype="pdf")
    except Exception as exc:  # PyMuPDF tira varios tipos de error para PDFs rotos
        log.warning("No se pudo abrir el PDF %s: %r", src, exc)
        raise InputError("No pude abrir el PDF. ¿Está dañado?") from exc

    with doc:
        if doc.needs_pass:
            raise InputError("El PDF está protegido con contraseña. Subí una copia sin contraseña.")
        if doc.page_count == 0:
            raise InputError("El PDF no tiene páginas.")
        if doc.page_count > MAX_PAGES:
            raise InputError(f"El PDF tiene {doc.page_count} páginas; por ahora el máximo es {MAX_PAGES}.")
        pages = []
        for i, page in enumerate(doc, start=1):
            path = out_dir / f"page_{i:02d}.png"
            try:
                pix = page.get_pixmap(dpi=PDF_DPI, colorspace=fitz.csGRAY)
                pix.save(path)
            except Exception as exc:
                log.warning("No se pudo convertir la página %d de %s: %r", i, src, exc)
                raise InputError(f"No pude convertir la página {i} del PDF. ¿Está dañado?") from exc
            pages.append(path)
        return pages
