"""Convierte lo que sube el usuario (PDF o imagen) en imágenes de página listas para el OMR."""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# Resolución a la que se rasteriza el PDF. 300 ppp es lo estándar para OMR.
PDF_DPI = 300
MAX_PAGES = 10


class InputError(ValueError):
    """El archivo subido no sirve (tipo, tamaño o cantidad de páginas)."""


def kind_of(filename: str, content_type: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if content_type in PDF_TYPES or suffix == ".pdf":
        return "pdf"
    if content_type in IMAGE_TYPES or suffix in IMAGE_SUFFIXES:
        return "image"
    raise InputError("Formato no soportado. Subí un PDF o una imagen (PNG, JPG o WEBP).")


def to_page_images(src: Path, kind: str, out_dir: Path) -> list[Path]:
    """Devuelve una imagen por página. Para imágenes es la misma imagen."""
    if kind == "image":
        return [src]

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        doc = fitz.open(src)
    except Exception as exc:  # PyMuPDF tira varios tipos de error para PDFs rotos
        raise InputError("No pude abrir el PDF. ¿Está dañado o protegido?") from exc

    with doc:
        if doc.page_count == 0:
            raise InputError("El PDF no tiene páginas.")
        if doc.page_count > MAX_PAGES:
            raise InputError(f"El PDF tiene {doc.page_count} páginas; por ahora el máximo es {MAX_PAGES}.")
        pages = []
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=PDF_DPI, colorspace=fitz.csGRAY)
            path = out_dir / f"page_{i:02d}.png"
            pix.save(path)
            pages.append(path)
        return pages
