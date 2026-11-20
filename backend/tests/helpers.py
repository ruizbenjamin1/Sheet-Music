"""Archivos de prueba generados en el momento (nada con copyright)."""

from __future__ import annotations

import struct
import zlib

import pymupdf as fitz


def make_pdf(pages: int) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=200, height=200)  # chico para que la prueba sea rápida
        page.insert_text((20, 100), f"Pagina {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def make_png() -> bytes:
    pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 8, 8), False)
    pix.clear_with(255)
    return pix.tobytes("png")


def make_jpeg() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
    pix.clear_with(255)
    return pix.tobytes("jpeg")


def webp_head(width: int = 8, height: int = 8) -> bytes:
    """Encabezado WEBP (VP8 con pérdida) con el tamaño pedido. No trae imagen de verdad."""
    frame = bytes(3) + bytes([0x9D, 0x01, 0x2A]) + struct.pack("<HH", width, height)
    chunk = b"VP8 " + struct.pack("<I", len(frame) + 16) + frame + bytes(16)
    return b"RIFF" + struct.pack("<I", len(chunk) + 4) + b"WEBP" + chunk


WEBP_HEAD = webp_head()

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_head(width: int, height: int) -> bytes:
    """PNG con un encabezado (IHDR) que dice `width` x `height`, sin la imagen.

    Sirve para probar el tope de píxeles sin generar un archivo gigante.
    """
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return PNG_SIGNATURE + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + crc


def make_big_pdf(width_pt: float, height_pt: float) -> bytes:
    """PDF de una página vacía de tamaño enorme (pesa poco: no tiene contenido)."""
    doc = fitz.open()
    doc.new_page(width=width_pt, height=height_pt)
    data = doc.tobytes()
    doc.close()
    return data


def page_xml(staves: int, measures: int, step: str = "C") -> str:
    """MusicXML mínimo de piano: una parte con `staves` pentagramas y `measures` compases."""
    out = []
    for m in range(1, measures + 1):
        attrs = ""
        if m == 1:
            clefs = "".join(
                f'<clef number="{s}"><sign>{"G" if s == 1 else "F"}</sign><line>{2 if s == 1 else 4}</line></clef>'
                for s in range(1, staves + 1)
            )
            attrs = (
                "<attributes><divisions>1</divisions><key><fifths>0</fifths></key>"
                "<time><beats>4</beats><beat-type>4</beat-type></time>"
                f"<staves>{staves}</staves>{clefs}</attributes>"
            )
        notes = ""
        for s in range(1, staves + 1):
            if s > 1:
                notes += "<backup><duration>4</duration></backup>"
            octave = 4 if s == 1 else 3
            notes += (
                f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
                f"<duration>4</duration><voice>{s}</voice><type>whole</type><staff>{s}</staff></note>"
            )
        out.append(f'<measure number="{m}">{attrs}{notes}</measure>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<score-partwise version="4.0">'
        '<part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>'
        f'<part id="P1">{"".join(out)}</part>'
        "</score-partwise>"
    )
