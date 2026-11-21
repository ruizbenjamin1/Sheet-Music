"""Formato intermedio que devuelve el lector con IA (`ClaudeEngine`) y su conversión a MusicXML.

La IA no escribe MusicXML: devuelve un JSON compacto (ver `SCORE_SCHEMA`) y acá se arma la
partitura con music21: una parte de piano con un pentagrama por cada clave (normalmente 2,
con llave), voces con `stream.Voice` y duraciones en negras como fracción ("1/3" = corchea
de tresillo, "3/2" = negra con puntillo).

Cada voz tiene que llenar el compás. Si le falta, se completa con silencios; si le sobra,
se recorta. Las dos cosas quedan en el log como advertencia (no le llegan al usuario).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from typing import Any

from music21 import chord, clef, duration, key, layout, meter, note, stream, tie
from music21.musicxml.m21ToXml import GeneralObjectExporter

from ..merge import TITLE_READ_FIELD

log = logging.getLogger(__name__)

PITCH_PATTERN = r"^[A-G](##|#|bb|b)?[0-8]$"
DURATION_PATTERN = r"^[0-9]+(/[0-9]+)?$"
# Largo máximo del título leído: se muestra en la app (E1-26).
MAX_TITLE_CHARS = 120

_EVENT = {
    "type": "object",
    "properties": {
        "pitches": {
            "type": "array",
            "description": "Sounding pitches, e.g. ['C4','E4','G4'] for a chord. Empty list = rest.",
            "items": {"type": "string", "pattern": PITCH_PATTERN},
        },
        "duration": {
            "type": "string",
            "description": "Length in quarter notes as a fraction: '4' whole, '2' half, '1' quarter, "
            "'1/2' eighth, '1/4' sixteenth, '3/2' dotted quarter, '1/3' triplet eighth, '2/3' triplet quarter.",
            "pattern": DURATION_PATTERN,
        },
        "tie": {"type": "boolean", "description": "True if tied to the next note of this same voice."},
    },
    "required": ["pitches", "duration"],
    "additionalProperties": False,
}

SCORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": ["string", "null"], "description": "Printed title, or null if none is visible."},
        "time": {
            "type": "object",
            "properties": {
                "beats": {"type": "integer", "minimum": 1, "maximum": 32},
                "beat_type": {"type": "integer", "enum": [1, 2, 4, 8, 16, 32]},
                "symbol": {"type": "string", "enum": ["normal", "common", "cut"]},
            },
            "required": ["beats", "beat_type"],
            "additionalProperties": False,
        },
        "fifths": {
            "type": "integer",
            "minimum": -7,
            "maximum": 7,
            "description": "Key signature: number of sharps (positive) or flats (negative).",
        },
        "clefs": {
            "type": "array",
            "description": "Clef at the start of each staff of the piano system, top to bottom.",
            "items": {"type": "string", "enum": ["treble", "bass"]},
            "minItems": 1,
            "maxItems": 4,
        },
        "measures": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "staves": {
                        "type": "array",
                        "description": "One entry per staff, top to bottom.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "clef": {
                                    "type": "string",
                                    "enum": ["treble", "bass"],
                                    "description": "Only if the clef changes at the start of this measure.",
                                },
                                "voices": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"events": {"type": "array", "items": _EVENT}},
                                        "required": ["events"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["voices"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["staves"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["time", "fifths", "clefs", "measures"],
    "additionalProperties": False,
}

_PITCH = re.compile(PITCH_PATTERN)
MAX_EVENT_QL = Fraction(16)


class ScoreFormatError(ValueError):
    """El JSON de la IA no tiene la forma esperada."""


def _parse_duration(text: Any) -> Fraction | None:
    try:
        value = Fraction(str(text).strip())
    except (ValueError, ZeroDivisionError):
        return None
    if value <= 0 or value > MAX_EVENT_QL:
        return None
    return value


def _m21_pitch(name: str) -> str | None:
    """'Bb3' -> 'B-3', 'F#4' -> 'F#4'. None si no es una altura válida."""
    name = str(name).strip()
    if not _PITCH.match(name):
        return None
    step, rest = name[0], name[1:-1]
    return step + rest.replace("b", "-") + name[-1]


def _split(ql: Fraction) -> list[Fraction]:
    """Parte una duración que no es una figura sola (por ejemplo 5/4) en figuras ligadas."""
    d = duration.Duration(ql)
    if d.type != "complex":
        return [ql]
    parts = [Fraction(c.quarterLength).limit_denominator(64) for c in d.components]
    return parts if sum(parts) == ql else [ql]


def _make_clef(name: str | None) -> clef.Clef:
    return clef.BassClef() if name == "bass" else clef.TrebleClef()


def _time_signature(data: dict) -> meter.TimeSignature:
    t = data.get("time") or {}
    beats, beat_type = int(t.get("beats", 4)), int(t.get("beat_type", 4))
    if not (1 <= beats <= 32) or beat_type not in (1, 2, 4, 8, 16, 32):
        log.warning("Compás %s/%s inválido en la lectura con IA; uso 4/4", beats, beat_type)
        beats, beat_type = 4, 4
    ts = meter.TimeSignature(f"{beats}/{beat_type}")
    symbol = t.get("symbol")
    if symbol == "common" and (beats, beat_type) == (4, 4):
        ts.symbol = "common"
    elif symbol == "cut" and (beats, beat_type) == (2, 2):
        ts.symbol = "cut"
    return ts


def _fit_voice(events: list[dict], bar: Fraction, where: str) -> list[tuple[list[str], Fraction, bool]]:
    """Normaliza los eventos de una voz y hace que sumen exactamente `bar`."""
    out: list[tuple[list[str], Fraction, bool]] = []
    total = Fraction(0)
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ql = _parse_duration(ev.get("duration"))
        if ql is None:
            log.warning("%s: duración inválida %r; la salteo", where, ev.get("duration"))
            continue
        pitches = []
        for p in ev.get("pitches") or []:
            m21 = _m21_pitch(p)
            if m21 is None:
                log.warning("%s: altura inválida %r; la salteo", where, p)
            else:
                pitches.append(m21)
        if total >= bar:
            log.warning("%s: la voz se pasa del compás; recorto lo que sobra", where)
            break
        if total + ql > bar:
            log.warning("%s: la voz se pasa del compás (%s de %s); recorto", where, total + ql, bar)
            ql = bar - total
        out.append((pitches, ql, bool(ev.get("tie")) and bool(pitches)))
        total += ql
    if total < bar:
        if out:
            log.warning("%s: la voz suma %s y el compás %s; completo con un silencio", where, total, bar)
        out.append(([], bar - total, False))
    return out


def _build_events(
    target: stream.Stream,
    events: list[tuple[list[str], Fraction, bool]],
    pending: dict,
    voice_key: tuple[int, int],
    stem: str | None,
) -> None:
    for pitches, ql, tie_next in events:
        pieces = _split(ql)
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            if not pitches:
                target.append(note.Rest(quarterLength=piece))
                continue
            el = note.Note(pitches[0]) if len(pitches) == 1 else chord.Chord(pitches)
            el.duration = duration.Duration(piece)
            if stem:
                el.stemDirection = stem
            prev = pending.pop(voice_key, None) if i == 0 else set(pitches)
            stops = bool(prev) and bool(set(pitches) & prev)
            starts = (not last) or tie_next
            if stops or starts:
                el.tie = tie.Tie("continue" if stops and starts else "stop" if stops else "start")
            target.append(el)
        if tie_next and pitches:
            pending[voice_key] = set(pitches)


def build_score(data: dict) -> stream.Score:
    """Arma la partitura de music21 a partir del formato intermedio."""
    if not isinstance(data, dict) or not isinstance(data.get("measures"), list) or not data["measures"]:
        raise ScoreFormatError("la lectura no trae compases")
    clefs = [c for c in (data.get("clefs") or []) if c in ("treble", "bass")][:4]
    if not clefs:
        first = data["measures"][0].get("staves") if isinstance(data["measures"][0], dict) else None
        n = len(first) if isinstance(first, list) and first else 2
        clefs = (["treble", "bass"] if n == 2 else ["treble"] * n)[:4]

    ts = _time_signature(data)
    bar = Fraction(ts.barDuration.quarterLength).limit_denominator(64)
    try:
        fifths = max(-7, min(7, int(data.get("fifths", 0))))
    except (TypeError, ValueError):
        fifths = 0

    score = stream.Score()
    staves = [stream.PartStaff(id=f"P1-Staff{i + 1}") for i in range(len(clefs))]
    pending: dict = {}

    for number, mdata in enumerate(data["measures"], start=1):
        staff_list = mdata.get("staves") if isinstance(mdata, dict) else None
        staff_list = staff_list if isinstance(staff_list, list) else []
        if len(staff_list) > len(staves):
            log.warning("Compás %s: la IA leyó %s pentagramas y hay %s; ignoro los de más",
                        number, len(staff_list), len(staves))
        for s_idx, part in enumerate(staves):
            sdata = staff_list[s_idx] if s_idx < len(staff_list) and isinstance(staff_list[s_idx], dict) else {}
            m = stream.Measure(number=number)
            if number == 1:
                m.insert(0, _make_clef(clefs[s_idx]))
                m.insert(0, key.KeySignature(fifths))
                m.insert(0, _copy_ts(ts))
            elif sdata.get("clef") in ("treble", "bass"):
                m.insert(0, _make_clef(sdata["clef"]))
            voices = [v for v in (sdata.get("voices") or []) if isinstance(v, dict)]
            voices = [v for v in voices if v.get("events")] or [{"events": []}]
            if not staff_list or s_idx >= len(staff_list):
                log.warning("Compás %s: falta el pentagrama %s; pongo un silencio", number, s_idx + 1)
            multi = len(voices) > 1
            for v_idx, vdata in enumerate(voices):
                where = f"Compás {number}, pentagrama {s_idx + 1}, voz {v_idx + 1}"
                events = _fit_voice(vdata.get("events") or [], bar, where)
                stem = ("up" if v_idx % 2 == 0 else "down") if multi else None
                if multi:
                    v = stream.Voice(id=str(v_idx + 1))
                    _build_events(v, events, pending, (s_idx, v_idx), stem)
                    m.insert(0, v)
                else:
                    _build_events(m, events, pending, (s_idx, v_idx), stem)
            part.append(m)

    for part in staves:
        score.insert(0, part)
    if len(staves) > 1:
        score.insert(0, layout.StaffGroup(staves, symbol="brace", barTogether=True))
    return score


def _copy_ts(ts: meter.TimeSignature) -> meter.TimeSignature:
    copy = meter.TimeSignature(ts.ratioString)
    copy.symbol = ts.symbol
    return copy


def to_musicxml(data: dict) -> str:
    """Formato intermedio -> MusicXML (texto). Si trae título, lo deja marcado como leído."""
    score = build_score(data)
    xml = GeneralObjectExporter(score).parse().decode("utf-8")
    title = data.get("title")
    # Una línea y corto: se muestra en la app y no tiene que poder traer otra cosa (E1-26).
    title = " ".join(title.split())[:MAX_TITLE_CHARS] if isinstance(title, str) else ""
    root = ET.fromstring(xml)
    for tag in ("work", "movement-number", "movement-title"):
        for el in root.findall(tag):
            root.remove(el)
    if title:
        work = ET.Element("work")
        ET.SubElement(work, "work-title").text = title
        root.insert(0, work)
        iden = root.find("identification")
        if iden is None:
            iden = ET.Element("identification")
            root.insert(1, iden)
        misc = iden.find("miscellaneous")
        if misc is None:
            misc = ET.SubElement(iden, "miscellaneous")
        field = ET.SubElement(misc, "miscellaneous-field", name=TITLE_READ_FIELD)
        field.text = "true"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
