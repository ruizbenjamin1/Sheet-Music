"""Convierte lo que sube el usuario (PDF o imagen) en imágenes de página listas para el OMR."""

from __future__ import annotations

import logging
import struct
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
# Tope del lado mayor de cada página del PDF en píxeles. Una hoja A4 a 300 ppp da 3508 px;
# si la página es más grande se bajan los ppp para no pasar de acá (oemer igual achica cada
# página a unos 3,7 megapíxeles antes de leerla, así que no se pierde nada).
PDF_MAX_SIDE_PX = 5000
MAX_PAGES = 10
# Tope para fotos e imágenes: se mira solo el encabezado, antes de decodificar nada.
# 60 MP deja pasar las fotos de celular de 48-50 MP; por encima, decodificarla ocupa
# cientos de MB a GB de memoria.
MAX_IMAGE_PIXELS = 60_000_000

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


DAMAGED_IMAGE = "No pude leer la imagen. ¿Está dañada?"

# Marcadores JPEG "start of frame" (traen el tamaño). C4, C8 y CC son otra cosa.
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # relleno
            i += 1
            continue
        if marker in (0x01, *range(0xD0, 0xD9)):  # marcadores sin largo
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        if marker in _JPEG_SOF:
            if i + 9 > len(data):
                return None
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        if marker in (0xD9, 0xDA) or length < 2:  # fin o comienzo de datos sin haber visto el tamaño
            return None
        i += 2 + length
    return None


VP8_START_CODE = bytes([0x9D, 0x01, 0x2A])


def _webp_size(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == VP8_START_CODE:
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        (bits,) = struct.unpack("<I", data[21:25])
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """Ancho y alto leídos del encabezado (sin decodificar la imagen). None si no se entiende."""
    fmt = sniff_format(data[:1024])
    if fmt == "png":
        if len(data) >= 24 and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        return None
    if fmt == "jpeg":
        return _jpeg_size(data)
    if fmt == "webp":
        return _webp_size(data)
    return None


def check_image_size(src: Path) -> None:
    """Rechaza imágenes con demasiados píxeles mirando solo el encabezado."""
    try:
        size = image_size(src.read_bytes())
    except InputError:
        size = None
    if not size or size[0] <= 0 or size[1] <= 0:
        raise InputError(DAMAGED_IMAGE)
    width, height = size
    if width * height > MAX_IMAGE_PIXELS:
        raise InputError(
            f"La imagen es demasiado grande ({width} × {height} píxeles). "
            f"El máximo es de {MAX_IMAGE_PIXELS // 1_000_000} megapíxeles: achicala o sacá la foto con menos resolución."
        )


def pdf_page_dpi(width_pt: float, height_pt: float) -> float:
    """PDF_DPI, o menos si la página es tan grande que pasaría de PDF_MAX_SIDE_PX."""
    longest_in = max(width_pt, height_pt) / 72
    if longest_in <= 0:
        return PDF_DPI
    return min(PDF_DPI, PDF_MAX_SIDE_PX / longest_in)


def to_page_images(src: Path, kind: str, out_dir: Path) -> list[Path]:
    """Devuelve una imagen por página. Para imágenes es la misma imagen (si no es gigante)."""
    if kind == "image":
        check_image_size(src)
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
                dpi = pdf_page_dpi(page.rect.width, page.rect.height)
                if dpi < PDF_DPI:
                    log.info("Página %d de %s muy grande (%s): se rasteriza a %.0f ppp", i, src, page.rect, dpi)
                # Con matrix (y no dpi=) se pueden usar ppp con decimales.
                zoom = dpi / 72
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
                pix.save(path)
            except Exception as exc:
                log.warning("No se pudo convertir la página %d de %s: %r", i, src, exc)
                raise InputError(f"No pude convertir la página {i} del PDF. ¿Está dañado?") from exc
            pages.append(path)
        return pages
