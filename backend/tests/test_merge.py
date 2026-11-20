import re

import pytest
from music21 import converter, stream

from app.merge import merge_pages
from tests.helpers import page_xml


def _staves(score):
    return list(score.parts)


def _with_oemer_metadata(xml: str, title: str) -> str:
    # Así escribe oemer 0.1.8 el título (nombre de la imagen) y el "compositor".
    return xml.replace(
        "<part-list>",
        f"<work><work-title>{title}</work-title></work>"
        '<identification><creator type="composer">Transcribed by Oemer</creator></identification>'
        "<part-list>",
    )


def _repeat_measure_numbers(xml: str) -> str:
    # oemer repite números de compás: todos quedan como "1".
    return re.sub(r'<measure number="\d+"', '<measure number="1"', xml)


def test_una_sola_pagina_se_renumera():
    xml = _repeat_measure_numbers(page_xml(staves=2, measures=3))
    merged, warnings = merge_pages([xml])
    assert warnings == []
    score = converter.parseData(merged, format="musicxml")
    for staff in _staves(score):
        assert [m.number for m in staff.getElementsByClass(stream.Measure)] == [1, 2, 3]
        assert [n.pitch.step for n in staff.recurse().notes] == ["C", "C", "C"]


@pytest.mark.parametrize("pages", [1, 2])
def test_saca_titulo_y_compositor_inventados(pages):
    xml = [_with_oemer_metadata(page_xml(2, 2), f"Page_{i:02d}") for i in range(1, pages + 1)]
    xml[0] = xml[0].replace("Page_01", "Upload")
    merged, _ = merge_pages(xml)
    for invented in ("Upload", "Page_0", "Oemer", "Music21 Fragment", ">Music21<"):
        assert invented not in merged
    for tag in ("<work", "<movement-title", "<creator"):
        assert tag not in merged
    score = converter.parseData(merged, format="musicxml")
    assert not score.metadata.title
    assert not score.metadata.composer
    # Sigue siendo una partitura válida.
    assert len(_staves(score)) == 2


def test_un_compositor_de_verdad_no_se_toca():
    xml = page_xml(2, 1).replace(
        "<part-list>", '<identification><creator type="composer">J. S. Bach</creator></identification><part-list>'
    )
    merged, _ = merge_pages([xml])
    assert "J. S. Bach" in merged


def test_sin_paginas_es_error():
    with pytest.raises(ValueError):
        merge_pages([])


def test_une_dos_paginas_de_piano():
    xml, warnings = merge_pages([page_xml(2, 3, "C"), page_xml(2, 2, "D")])
    assert warnings == []
    score = converter.parseData(xml, format="musicxml")
    staves = _staves(score)
    assert len(staves) == 2  # mano derecha y mano izquierda
    for staff in staves:
        measures = list(staff.getElementsByClass(stream.Measure))
        assert [m.number for m in measures] == [1, 2, 3, 4, 5]
        steps = [n.pitch.step for n in staff.recurse().notes]
        assert steps == ["C", "C", "C", "D", "D"]
    # Sigue siendo una sola parte de piano con dos pentagramas.
    assert xml.count("<score-part ") == 1
    assert "<staves>2</staves>" in xml


def test_pagina_con_otra_cantidad_de_pentagramas_se_saltea():
    xml, warnings = merge_pages([page_xml(2, 2, "C"), page_xml(1, 2, "D"), page_xml(2, 1, "E")])
    assert len(warnings) == 1
    assert "página 2" in warnings[0] and "1 pentagrama en vez de 2 pentagramas" in warnings[0]
    score = converter.parseData(xml, format="musicxml")
    for staff in _staves(score):
        assert [n.pitch.step for n in staff.recurse().notes] == ["C", "C", "E"]
        assert [m.number for m in staff.getElementsByClass(stream.Measure)] == [1, 2, 3]


def _note(step: str, dur: int, kind: str, staff: int = 1) -> str:
    return (
        f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>{dur}</duration>"
        f"<type>{kind}</type><staff>{staff}</staff><voice>1</voice></note>"
    )


def _rest(dur: int, staff: int, dot: bool = False) -> str:
    return f'<note><rest measure="yes"/><duration>{dur}</duration>{"<dot/>" if dot else ""}<staff>{staff}</staff></note>'


# Copia reducida de cómo escribe oemer 0.1.8 (sin <time>, con <backup> y silencios de compás
# en el medio, compases que no cierran). Es lo que salió en E1-03 con una partitura generada.
OEMER_LIKE_PAGE = (
    '<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><part-list>'
    '<score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1">'
    '<measure number="1"><attributes><divisions>16</divisions><key><fifths>0</fifths></key><staves>2</staves>'
    '<clef number="1"><sign>G</sign><line>2</line></clef><clef number="2"><sign>F</sign><line>4</line></clef>'
    "</attributes>"
    + _note("E", 16, "quarter") + _note("E", 16, "quarter")
    + "<backup><duration>32</duration></backup>" + _rest(48, 2, dot=True)
    + "<backup><duration>16</duration></backup>" + _note("G", 16, "quarter")
    + '</measure><measure number="2">'
    + _note("G", 16, "quarter") + _rest(8, 1) + _note("E", 16, "quarter")
    + "<backup><duration>40</duration></backup>" + _rest(96, 2, dot=True) + _note("D", 64, "whole")
    + "</measure></part></score-partwise>"
)


def _notes_per_measure(xml: str) -> list[list[list[str]]]:
    score = converter.parseData(xml, format="musicxml")
    return [
        [[n.pitch.step for n in m.recurse().notes] for m in staff.getElementsByClass(stream.Measure)]
        for staff in _staves(score)
    ]


def test_salida_tipo_oemer_no_se_reacomoda_al_unir():
    # En E1-03 music21 "arreglaba" estos compases al exportar: movía notas de un compás a otro
    # y agregaba un compás vacío al final. Al unir hay que respetar lo que leyó el motor.
    page = _notes_per_measure(OEMER_LIKE_PAGE)
    xml, warnings = merge_pages([OEMER_LIKE_PAGE, OEMER_LIKE_PAGE])
    assert warnings == []
    merged = _notes_per_measure(xml)
    assert merged == [staff + staff for staff in page]


def test_salida_tipo_oemer_de_una_pagina_no_se_reacomoda():
    xml, _ = merge_pages([OEMER_LIKE_PAGE])
    assert _notes_per_measure(xml) == _notes_per_measure(OEMER_LIKE_PAGE)
