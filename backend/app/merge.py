"""Une el MusicXML de varias páginas en una sola partitura."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from music21 import converter, stream
from music21.musicxml.m21ToXml import GeneralObjectExporter


def _staves(n: int) -> str:
    return f"{n} pentagrama" if n == 1 else f"{n} pentagramas"


# Compositores que no son de verdad: los escriben oemer ("Transcribed by Oemer") o music21
# cuando la partitura no trae uno.
INVENTED_COMPOSERS = {"transcribed by oemer", "music21"}
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>' + chr(10)


# Marca que deja el lector con IA (`omr/claude_score.py`) cuando el título lo leyó de la hoja.
TITLE_READ_FIELD = "omr-title-read"


def read_title(xml: str) -> str | None:
    """El título de la página si está marcado como leído de la hoja (lector con IA); si no, None."""
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError:
        return None
    marked = any(
        f.get("name") == TITLE_READ_FIELD for f in root.iter("miscellaneous-field")
    )
    title = (root.findtext("work/work-title") or "").strip()
    return title if marked and title else None


def _drop_invented_metadata(xml: str, title: str | None = None) -> str:
    """Saca el título y el compositor que inventan el motor y music21.

    oemer pone como título el nombre de la imagen temporal ("Upload", "Page_01") y como
    compositor "Transcribed by Oemer"; music21 completa con "Music21 Fragment" y "Music21".
    El OMR no lee títulos, así que el título queda vacío y el frontend muestra el nombre
    del archivo. La excepción es `title`: el que leyó el lector con IA de la hoja.
    """
    root = ET.fromstring(xml)
    for tag in ("work", "movement-number", "movement-title"):
        for el in root.findall(tag):
            root.remove(el)
    for iden in root.findall("identification"):
        for misc in iden.findall("miscellaneous"):
            for field in misc.findall("miscellaneous-field"):
                if field.get("name") == TITLE_READ_FIELD:
                    misc.remove(field)
            if len(misc) == 0:
                iden.remove(misc)
    if title:
        work = ET.Element("work")
        ET.SubElement(work, "work-title").text = title
        root.insert(0, work)
    for iden in root.findall("identification"):
        for creator in iden.findall("creator"):
            if (creator.text or "").strip().lower() in INVENTED_COMPOSERS:
                iden.remove(creator)
    return XML_DECLARATION + ET.tostring(root, encoding="unicode")


SKIPPED_PAGE = "La página {n} se leyó con {got} en vez de {want}; la salteé."


def merge_pages(pages_xml: list[str], skipped_message: str = SKIPPED_PAGE) -> tuple[str, list[str]]:
    """Devuelve (musicxml, avisos).

    Siempre renumera los compases (oemer repite números, aun en una sola página) y saca
    el título y compositor inventados. Si una página se leyó con otra cantidad de
    pentagramas que la primera, se saltea y se avisa (no se puede saber a qué pentagrama
    corresponde cada uno). `skipped_message` es el texto de ese aviso, con `{n}` (número de
    página), `{got}` y `{want}` (cantidad de pentagramas).
    """
    if not pages_xml:
        raise ValueError("merge_pages necesita al menos una página")

    warnings: list[str] = []
    title = read_title(pages_xml[0])
    scores = [converter.parseData(xml, format="musicxml") for xml in pages_xml]
    base = scores[0]
    base_parts = list(base.parts)

    for page_no, score in enumerate(scores[1:], start=2):
        parts = list(score.parts)
        if len(parts) != len(base_parts):
            warnings.append(
                skipped_message.format(n=page_no, got=_staves(len(parts)), want=_staves(len(base_parts)))
            )
            continue
        for target, part in zip(base_parts, parts):
            for measure in part.getElementsByClass(stream.Measure):
                target.append(copy.deepcopy(measure))

    for part in base_parts:
        for number, measure in enumerate(part.getElementsByClass(stream.Measure), start=1):
            measure.number = number

    # Sin makeNotation: si no, music21 "arregla" los compases que no cierran (oemer deja muchos),
    # mueve notas de un compás a otro y agrega compases vacíos. Hay que respetar lo que leyó el motor.
    exporter = GeneralObjectExporter(base)
    exporter.makeNotation = False
    xml_bytes = exporter.parse()
    return _drop_invented_metadata(xml_bytes.decode("utf-8"), title), warnings
