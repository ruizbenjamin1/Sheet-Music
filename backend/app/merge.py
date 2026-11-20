"""Une el MusicXML de varias páginas en una sola partitura."""

from __future__ import annotations

import copy

from music21 import converter, stream
from music21.musicxml.m21ToXml import GeneralObjectExporter


def _staves(n: int) -> str:
    return f"{n} pentagrama" if n == 1 else f"{n} pentagramas"


def merge_pages(pages_xml: list[str]) -> tuple[str, list[str]]:
    """Devuelve (musicxml, avisos). Con una sola página la devuelve tal cual.

    Si una página se leyó con otra cantidad de pentagramas que la primera, se saltea
    y se avisa (no se puede saber a qué pentagrama corresponde cada uno).
    """
    if not pages_xml:
        raise ValueError("merge_pages necesita al menos una página")
    if len(pages_xml) == 1:
        return pages_xml[0], []

    warnings: list[str] = []
    scores = [converter.parseData(xml, format="musicxml") for xml in pages_xml]
    base = scores[0]
    base_parts = list(base.parts)

    for page_no, score in enumerate(scores[1:], start=2):
        parts = list(score.parts)
        if len(parts) != len(base_parts):
            warnings.append(
                f"La página {page_no} se leyó con {_staves(len(parts))} en vez de {_staves(len(base_parts))}; "
                "la salteé."
            )
            continue
        for target, part in zip(base_parts, parts):
            for measure in part.getElementsByClass(stream.Measure):
                target.append(copy.deepcopy(measure))

    for part in base_parts:
        for number, measure in enumerate(part.getElementsByClass(stream.Measure), start=1):
            measure.number = number

    xml_bytes = GeneralObjectExporter(base).parse()
    return xml_bytes.decode("utf-8"), warnings
