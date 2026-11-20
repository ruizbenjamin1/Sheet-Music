import pytest
from music21 import converter, stream

from app.merge import merge_pages
from tests.helpers import page_xml


def _staves(score):
    return list(score.parts)


def test_una_sola_pagina_queda_igual():
    xml = page_xml(staves=2, measures=3)
    assert merge_pages([xml]) == (xml, [])


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
