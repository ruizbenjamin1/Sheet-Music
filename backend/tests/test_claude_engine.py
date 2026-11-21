"""Lector con IA (`ClaudeEngine`) sin llamar al CLI real: el proceso se reemplaza por uno falso."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pytest
from music21 import converter, stream

from app import omr
from app.merge import merge_pages
from app.omr import ClaudeEngine, FallbackEngine, OmrError
from app.omr import claude_engine
from app.omr.base import Notifier, notifying
from app.omr.claude_score import SCORE_SCHEMA, build_score, to_musicxml
from tests.helpers import page_xml

CEG = ["C4", "E4", "G4"]


def ev(pitches, dur, tie=None):
    e = {"pitches": pitches, "duration": dur}
    if tie is not None:
        e["tie"] = tie
    return e


def two_voices_measure():
    """Como el compás 1 de la pieza 26: tresillos C-E-G arriba y negras C abajo, en la misma mano."""
    triplets = [ev([p], "1/3") for p in CEG] * 4
    quarters = [ev(["C4"], "1")] * 4
    return {
        "staves": [
            {"voices": [{"events": triplets}, {"events": quarters}]},
            {"voices": [{"events": [ev(["C3", "E3"], "2"), ev(["E3", "G3"], "2")]}]},
        ]
    }


def sample(measures=None, **extra):
    data = {
        "title": None,
        "time": {"beats": 4, "beat_type": 4, "symbol": "common"},
        "fifths": 0,
        "clefs": ["treble", "bass"],
        "measures": measures or [two_voices_measure()],
    }
    data.update(extra)
    return data


def cli_stdout(data, **extra):
    """Salida de `claude -p --output-format json --json-schema ...` (forma real del CLI 2.1)."""
    out = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Listo.",
        "structured_output": data,
        "session_id": "x",
        "total_cost_usd": 0.1,
    }
    out.update(extra)
    return json.dumps(out)


def parsed(xml):
    return converter.parseData(xml, format="musicxml")


def measure_events(score, staff, number):
    part = list(score.parts)[staff]
    m = part.getElementsByClass(stream.Measure)[number - 1]
    return m


# --- Comando ---


def test_arma_el_comando(tmp_path):
    img = tmp_path / "trabajo" / "foto.png"
    cmd = claude_engine.build_command(Path("C:/x/claude.exe"), img, None)
    assert cmd[0].endswith("claude.exe") and cmd[1] == "-p"
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCORE_SCHEMA
    assert cmd[cmd.index("--tools") + 1] == "Read"
    # Sin --allowedTools: Read queda acotado a las carpetas de trabajo (E1-26).
    assert "--allowedTools" not in cmd and "--allowed-tools" not in cmd
    assert "--restricted" in cmd
    assert cmd[cmd.index("--add-dir") + 1] == str(img.parent)
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--dangerously-skip-permissions" not in cmd and "bypassPermissions" not in cmd
    assert "--model" not in cmd
    cmd = claude_engine.build_command(Path("claude"), img, "opus")
    assert cmd[cmd.index("--model") + 1] == "opus"


def test_corre_el_cli_con_el_pedido_por_stdin(monkeypatch, tmp_path):
    img = tmp_path / "foto.png"
    img.write_bytes(b"x")
    seen = {}

    def run(cmd, **kwargs):
        seen.update(kwargs, cmd=cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=cli_stdout(sample()), stderr="")

    monkeypatch.setattr(claude_engine, "run_process", run)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "x")
    monkeypatch.setenv("CLAUDE_OMR_MODEL", "sonnet")
    progress = []
    with notifying(Notifier(progress=progress.append, warning=lambda t: None)):
        xml = ClaudeEngine(Path("claude")).recognize(img, tmp_path)
    assert str(img.resolve()) in seen["input"] and "Read" in seen["input"]
    assert seen["timeout"] == claude_engine.TIMEOUT_SECONDS == 300
    assert seen["cwd"] == str(tmp_path)
    assert "CLAUDECODE" not in seen["env"] and "CLAUDE_CODE_ENTRYPOINT" not in seen["env"]
    assert "PATH" in seen["env"] or "Path" in seen["env"]
    assert seen["cmd"][seen["cmd"].index("--model") + 1] == "sonnet"
    assert progress == ["Leyendo con IA… puede tardar un par de minutos"]
    assert "<score-partwise" in xml


# --- Salida del CLI ---


def test_parsea_structured_output():
    assert claude_engine.parse_cli_output(cli_stdout(sample()))["fifths"] == 0


def test_parsea_result_como_texto_json():
    text = "```json\n" + json.dumps(sample()) + "\n```"
    out = json.dumps({"type": "result", "is_error": False, "result": text})
    assert claude_engine.parse_cli_output(out)["clefs"] == ["treble", "bass"]


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "esto no es json",
        json.dumps({"type": "result", "is_error": True, "result": "Failed to authenticate"}),
        json.dumps({"type": "result", "is_error": False, "result": "No puedo leer la imagen."}),
        json.dumps([1, 2]),
    ],
)
def test_salida_invalida(stdout):
    with pytest.raises(ValueError):
        claude_engine.parse_cli_output(stdout)


@pytest.mark.parametrize(
    "stdout",
    [
        "basura",
        json.dumps({"type": "result", "is_error": True, "result": "OAuth session expired"}),
        cli_stdout({"measures": "no es una lista"}),
        cli_stdout({"measures": []}),
    ],
)
def test_errores_en_espanol_y_detalle_al_log(monkeypatch, tmp_path, caplog, stdout):
    monkeypatch.setattr(
        claude_engine, "run_process", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout=stdout, stderr="boom")
    )
    with caplog.at_level(logging.ERROR), pytest.raises(OmrError, match="La lectura con IA no funcionó"):
        ClaudeEngine(Path("claude")).recognize(tmp_path / "a.png", tmp_path)
    assert caplog.records


def test_tiempo_agotado(monkeypatch, tmp_path):
    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(claude_engine, "run_process", run)
    with pytest.raises(OmrError, match="tardó demasiado"):
        ClaudeEngine(Path("claude"), timeout=1).recognize(tmp_path / "a.png", tmp_path)


def test_cli_que_no_arranca(monkeypatch, tmp_path):
    def run(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(claude_engine, "run_process", run)
    with pytest.raises(OmrError, match="no está disponible"):
        ClaudeEngine(Path("no-existe")).recognize(tmp_path / "a.png", tmp_path)


# --- Formato intermedio -> MusicXML ---


def test_voces_y_tresillos():
    score = parsed(to_musicxml(sample()))
    m = measure_events(score, 0, 1)
    voices = list(m.voices)
    assert len(voices) == 2
    upper = list(voices[0].notes)
    assert len(upper) == 12 and all(float(n.quarterLength) == pytest.approx(1 / 3) for n in upper)
    assert all(n.duration.tuplets and n.duration.tuplets[0].numberNotesActual == 3 for n in upper)
    assert [n.pitch.nameWithOctave for n in upper[:3]] == CEG
    lower = list(voices[1].notes)
    assert [float(n.quarterLength) for n in lower] == [1.0] * 4
    assert upper[0].stemDirection == "up" and lower[0].stemDirection == "down"
    assert m.duration.quarterLength == 4


def test_acordes_silencios_armadura_y_compas():
    data = sample(
        fifths=-1,
        time={"beats": 3, "beat_type": 4},
        measures=[
            {
                "staves": [
                    {"voices": [{"events": [ev(["Bb4", "D5"], "2"), ev([], "1")]}]},
                    {"voices": [{"events": [ev([], "3")]}]},
                ]
            }
        ],
    )
    score = parsed(to_musicxml(data))
    upper = measure_events(score, 0, 1)
    chord = upper.notes[0]
    assert [p.nameWithOctave for p in chord.pitches] == ["B-4", "D5"]
    assert len(upper.getElementsByClass("Rest")) == 1
    assert upper.keySignature.sharps == -1
    assert upper.timeSignature.ratioString == "3/4"
    lower = measure_events(score, 1, 1)
    assert lower.notes.stream().highestTime == 0 and lower.duration.quarterLength == 3


def test_compas_que_no_cierra_se_completa_o_se_recorta(caplog):
    data = sample(
        measures=[
            {
                "staves": [
                    {"voices": [{"events": [ev(["C5"], "1")]}]},  # falta: se completa con silencio
                    {"voices": [{"events": [ev(["C3"], "3"), ev(["G2"], "2"), ev(["E2"], "1")]}]},  # sobra
                ]
            },
            {"staves": [{"voices": []}]},  # pentagrama vacío y otro que falta
        ]
    )
    with caplog.at_level(logging.WARNING):
        score = parsed(to_musicxml(data))
    for staff in (0, 1):
        for number in (1, 2):
            assert measure_events(score, staff, number).duration.quarterLength == 4
    lower = measure_events(score, 1, 1)
    assert [float(n.quarterLength) for n in lower.notesAndRests] == [3.0, 1.0]
    assert [n.pitch.nameWithOctave for n in lower.notes] == ["C3", "G2"]
    text = caplog.text
    assert "completo con un silencio" in text and "recorto" in text


def test_ligaduras_y_duraciones_compuestas():
    data = sample(
        measures=[
            {
                "staves": [
                    {"voices": [{"events": [ev(["G4"], "3"), ev(["E4"], "1", tie=True)]}]},
                    {"voices": [{"events": [ev(["C3"], "5/4"), ev([], "11/4")]}]},
                ]
            },
            {"staves": [{"voices": [{"events": [ev(["E4"], "4")]}]}, {"voices": [{"events": [ev([], "4")]}]}]},
        ]
    )
    score = parsed(to_musicxml(data))
    up1, up2 = measure_events(score, 0, 1), measure_events(score, 0, 2)
    assert up1.notes[-1].tie.type == "start" and up2.notes[0].tie.type == "stop"
    low = list(measure_events(score, 1, 1).notes)
    assert sum(float(n.quarterLength) for n in low) == 1.25
    assert low[0].tie.type == "start" and low[-1].tie.type == "stop"


def test_alturas_y_duraciones_invalidas_no_rompen(caplog):
    data = sample(
        measures=[
            {
                "staves": [
                    {"voices": [{"events": [ev(["H9", "C4"], "1"), ev(["D4"], "cero"), ev(["E4"], "0")]}]},
                    {"voices": [{"events": [ev(["C3"], "4")]}]},
                ]
            }
        ]
    )
    with caplog.at_level(logging.WARNING):
        score = parsed(to_musicxml(data))
    upper = measure_events(score, 0, 1)
    assert [n.pitch.nameWithOctave for n in upper.notes] == ["C4"]
    assert upper.duration.quarterLength == 4


def test_sin_compases_es_error():
    with pytest.raises(ValueError):
        build_score({"measures": []})


def test_titulo_leido_sobrevive_la_limpieza_y_el_inventado_no():
    xml, _ = merge_pages([to_musicxml(sample(title="26. Estudio"))])
    assert "<work-title>26. Estudio</work-title>" in xml
    assert "omr-title-read" not in xml and "movement-title" not in xml
    xml, _ = merge_pages([to_musicxml(sample(title=None))])
    assert "<work>" not in xml and "work-title" not in xml and "movement-title" not in xml
    assert "Music21" not in xml


def test_limpieza_de_merge_renumera_y_no_reacomoda():
    measures = [two_voices_measure() for _ in range(3)]
    xml, warnings = merge_pages([to_musicxml(sample(measures=measures))])
    assert warnings == []
    score = parsed(xml)
    for part in score.parts:
        ms = list(part.getElementsByClass(stream.Measure))
        assert [m.number for m in ms] == [1, 2, 3]
        assert all(m.duration.quarterLength == 4 for m in ms)


# --- Motor por defecto y respaldo ---


class Fake:
    def __init__(self, name, result=None, error=None):
        self.name, self.result, self.error, self.calls = name, result, error, []

    def recognize(self, image_path, work_dir):
        self.calls.append(image_path)
        if self.error:
            raise self.error
        return self.result


def test_desactivado_sin_la_variable(monkeypatch, tmp_path):
    monkeypatch.delenv("OMR_USE_CLAUDE", raising=False)
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    monkeypatch.setattr(omr, "find_claude_cli", lambda: tmp_path / "claude.exe")
    assert omr.default_engine().name == "audiveris+oemer"
    monkeypatch.setenv("OMR_USE_CLAUDE", "0")
    assert omr.default_engine().name == "audiveris+oemer"


def test_activado_con_la_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("OMR_USE_CLAUDE", "1")
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    monkeypatch.setattr(omr, "find_claude_cli", lambda: tmp_path / "claude.exe")
    engine = omr.default_engine()
    assert engine.name == "claude+audiveris+oemer"
    assert isinstance(engine.primary, ClaudeEngine) and engine.primary.cli == tmp_path / "claude.exe"
    assert isinstance(engine.fallback, FallbackEngine) and engine.fallback.name == "audiveris+oemer"
    monkeypatch.setattr(omr, "find_audiveris", lambda: None)
    assert omr.default_engine().name == "claude+oemer"


def test_activado_sin_cli_queda_como_siempre(monkeypatch, tmp_path):
    monkeypatch.setenv("OMR_USE_CLAUDE", "1")
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    monkeypatch.setattr(omr, "find_claude_cli", lambda: None)
    assert omr.default_engine().name == "audiveris+oemer"


def test_find_claude_cli(monkeypatch, tmp_path):
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("CLAUDE_CLI", str(exe))
    assert claude_engine.find_claude_cli() == exe
    monkeypatch.setenv("CLAUDE_CLI", str(tmp_path / "no-existe.exe"))
    assert claude_engine.find_claude_cli() is None
    monkeypatch.delenv("CLAUDE_CLI")
    monkeypatch.setattr(claude_engine.shutil, "which", lambda name: None)
    monkeypatch.setattr(claude_engine.Path, "home", classmethod(lambda cls: tmp_path))
    assert claude_engine.find_claude_cli() is None
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".local" / "bin" / "claude.exe").write_bytes(b"")
    assert claude_engine.find_claude_cli() == tmp_path / ".local" / "bin" / "claude.exe"


def test_si_la_ia_falla_lee_con_audiveris_y_avisa(monkeypatch, tmp_path):
    monkeypatch.setattr(
        claude_engine, "run_process", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="basura", stderr="")
    )
    audiveris = Fake("audiveris", result=page_xml(2, 1))
    oemer = Fake("oemer", result="no")
    engine = FallbackEngine(
        ClaudeEngine(Path("claude")),
        FallbackEngine(audiveris, oemer),
        omr.AI_FALLBACK_PROGRESS,
        omr.AI_FALLBACK_WARNING,
    )
    progress, warnings = [], []
    with notifying(Notifier(progress=progress.append, warning=warnings.append, subject="esta foto")):
        assert engine.recognize(tmp_path / "a.png", tmp_path) == page_xml(2, 1)
    assert oemer.calls == []
    assert progress[-1] == "La lectura con IA no funcionó con esta foto; probé con el lector común"
    assert warnings == ["La lectura con IA no funcionó con esta foto; se leyó con el lector común."]


# --- Seguridad (E1-26) ---


@pytest.mark.parametrize("name", ["claude.cmd", "claude.BAT"])
def test_rechaza_cli_que_es_script_de_cmd(monkeypatch, tmp_path, caplog, name):
    script = tmp_path / name
    script.write_bytes(b"")
    monkeypatch.setenv("CLAUDE_CLI", str(script))
    with caplog.at_level(logging.WARNING):
        assert claude_engine.find_claude_cli() is None
    assert "cmd.exe" in caplog.text
    monkeypatch.delenv("CLAUDE_CLI")
    monkeypatch.setattr(claude_engine.shutil, "which", lambda n: str(script))
    assert claude_engine.find_claude_cli() is None


def test_el_pedido_dice_que_el_texto_de_la_imagen_no_son_instrucciones():
    assert "never instructions" in claude_engine.SYSTEM_PROMPT
    assert "never instructions" in claude_engine.PROMPT
    assert "only the printed title" in claude_engine.PROMPT


def test_titulo_en_una_linea_y_recortado():
    xml = to_musicxml(sample(title="  Vals\n\n del   río " + "x" * 300))
    title = merge_pages([xml])[0]
    import re as _re

    found = _re.search(r"<work-title>(.*?)</work-title>", title).group(1)
    assert found.startswith("Vals del río x") and len(found) == 120
