"""Pruebas de AudiverisEngine sin Audiveris: el proceso se reemplaza por uno falso que deja
.mxl generados en la prueba (zip con META-INF/container.xml y el MusicXML)."""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from music21 import converter, stream

from app.omr import AudiverisEngine, OmrError, find_audiveris
from app.omr import audiveris_engine
from app.omr.base import Notifier, notifying
from tests.helpers import page_xml

EXE = Path("C:/herramientas/Audiveris/Audiveris.exe")


def write_mxl(path: Path, xml: str, inner: str | None = None) -> None:
    inner = inner or path.name.replace(".mxl", ".xml")
    container = (
        '<?xml version="1.0" encoding="UTF-8"?><container><rootfiles>'
        f'<rootfile full-path="{inner}" media-type="application/vnd.recordare.musicxml+xml"/>'
        "</rootfiles></container>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(inner, xml)
        z.writestr("META-INF/container.xml", container)


def fake_run(outputs: dict[str, str] | None = None, returncode: int = 0, stdout: str = ""):
    """`outputs`: sufijo del archivo de salida ('.mxl', '.mvt1.mxl'…) -> MusicXML."""
    calls: list = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        out_dir = Path(cmd[cmd.index("-output") + 1])
        image = Path(cmd[-1])
        for suffix, xml in (outputs or {}).items():
            write_mxl(out_dir / f"{image.stem}{suffix}", xml)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    run.calls = calls
    return run


@pytest.fixture
def image(tmp_path):
    img = np.full((300, 1000), 230, dtype=np.uint8)
    for y in range(100, 150, 10):
        img[y, 50:950] = 40
    path = tmp_path / "pages" / "page_01.png"
    path.parent.mkdir()
    cv2.imwrite(str(path), img)
    return path


def test_arma_el_comando_y_devuelve_el_musicxml(monkeypatch, tmp_path, image):
    xml = page_xml(staves=2, measures=2)
    run = fake_run({".mxl": xml})
    monkeypatch.setattr(audiveris_engine.subprocess, "run", run)

    assert AudiverisEngine(EXE, timeout=42).recognize(image, tmp_path) == xml
    cmd, kwargs = run.calls[0]
    out_dir = Path(cmd[4])
    assert cmd[:4] == [str(EXE), "-batch", "-export", "-output"]
    assert cmd[5] == "--"
    assert out_dir.parent == tmp_path
    assert kwargs["timeout"] == 42
    # Le pasa una imagen preparada (no la original), dentro de la carpeta del trabajo.
    prepared = Path(cmd[6])
    assert prepared != image and prepared.parent == out_dir


def test_prepara_la_imagen_binarizada_y_agrandada(tmp_path, image):
    dst = audiveris_engine.prepare_image(image, tmp_path / "prep.png")
    out = cv2.imread(str(dst), cv2.IMREAD_UNCHANGED)
    assert out.ndim == 2  # gris
    assert set(np.unique(out)) <= {0, 255}  # binarizada
    assert out.shape[1] == audiveris_engine.MIN_WIDTH_PX  # 1000 px -> 2500 px
    assert (out == 0).any()  # las líneas siguen estando


def test_imagen_ancha_no_se_agranda(tmp_path):
    src = tmp_path / "ancha.png"
    cv2.imwrite(str(src), np.full((100, 3000), 200, dtype=np.uint8))
    out = cv2.imread(str(audiveris_engine.prepare_image(src, tmp_path / "p.png")), cv2.IMREAD_UNCHANGED)
    assert out.shape == (100, 3000)


def test_une_los_movimientos_en_orden(monkeypatch, tmp_path, image):
    outputs = {f".mvt{n}.mxl": page_xml(staves=2, measures=1, step=step) for n, step in [(1, "C"), (2, "D"), (10, "E")]}
    monkeypatch.setattr(audiveris_engine.subprocess, "run", fake_run(outputs))

    xml = AudiverisEngine(EXE).recognize(image, tmp_path)
    score = converter.parseData(xml, format="musicxml")
    parts = list(score.parts)
    assert len(parts) == 2
    measures = list(parts[0].getElementsByClass(stream.Measure))
    # mvt10 va después de mvt2 (orden numérico, no alfabético) y se renumeran.
    assert [m.notes[0].pitch.step for m in measures] == ["C", "D", "E"]
    assert [m.number for m in measures] == [1, 2, 3]


def test_movimiento_con_otros_pentagramas_se_saltea_con_aviso(monkeypatch, tmp_path, image):
    outputs = {
        ".mvt1.mxl": page_xml(staves=1, measures=1, step="C"),
        ".mvt2.mxl": page_xml(staves=2, measures=1, step="D"),
        ".mvt3.mxl": page_xml(staves=2, measures=1, step="E"),
    }
    monkeypatch.setattr(audiveris_engine.subprocess, "run", fake_run(outputs))
    warnings: list[str] = []
    with notifying(Notifier(progress=lambda t: None, warning=warnings.append, subject="esta foto")):
        xml = AudiverisEngine(EXE).recognize(image, tmp_path)

    parts = list(converter.parseData(xml, format="musicxml").parts)
    assert len(parts) == 2  # gana la cantidad de la mayoría, aunque el primero sea distinto
    assert [m.notes[0].pitch.step for m in parts[0].getElementsByClass(stream.Measure)] == ["D", "E"]
    assert warnings == ["Un tramo de esta foto (el 1) se leyó con 1 pentagrama en vez de 2 pentagramas; lo salteé."]


def test_saca_la_ruta_de_la_imagen(monkeypatch, tmp_path, image):
    xml = page_xml(staves=2, measures=1).replace(
        "<part-list>",
        "<identification><source>C:\\tmp\\secreto\\x.png</source><miscellaneous>"
        '<miscellaneous-field name="source-file">C:\\tmp\\secreto\\x.png</miscellaneous-field>'
        "</miscellaneous></identification><part-list>",
    )
    monkeypatch.setattr(audiveris_engine.subprocess, "run", fake_run({".mxl": xml}))
    assert "secreto" not in AudiverisEngine(EXE).recognize(image, tmp_path)


def test_falla_en_espanol_y_detalle_al_log(monkeypatch, tmp_path, image, caplog):
    run = fake_run(returncode=1, stdout="WARN  StepException: No regularly spaced lines found")
    monkeypatch.setattr(audiveris_engine.subprocess, "run", run)
    with pytest.raises(OmrError, match="No pude leer la página"):
        AudiverisEngine(EXE).recognize(image, tmp_path)
    assert "No regularly spaced lines found" in caplog.text


def test_sin_salida_es_error(monkeypatch, tmp_path, image):
    monkeypatch.setattr(audiveris_engine.subprocess, "run", fake_run(returncode=0))
    with pytest.raises(OmrError, match="No pude leer la página"):
        AudiverisEngine(EXE).recognize(image, tmp_path)


def test_tiempo_agotado(monkeypatch, tmp_path, image):
    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(audiveris_engine.subprocess, "run", run)
    with pytest.raises(OmrError, match="tardó demasiado"):
        AudiverisEngine(EXE, timeout=1).recognize(image, tmp_path)


def test_ejecutable_que_no_arranca(monkeypatch, tmp_path, image):
    def run(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(audiveris_engine.subprocess, "run", run)
    with pytest.raises(OmrError, match="no está disponible"):
        AudiverisEngine(EXE).recognize(image, tmp_path)


def test_imagen_ilegible(tmp_path):
    bad = tmp_path / "rota.png"
    bad.write_bytes(b"no es una imagen")
    with pytest.raises(OmrError, match="dañada"):
        AudiverisEngine(EXE).recognize(bad, tmp_path)


def test_buscar_audiveris(monkeypatch, tmp_path):
    exe = tmp_path / "Audiveris.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("AUDIVERIS_EXE", str(exe))
    assert find_audiveris() == exe
    monkeypatch.setenv("AUDIVERIS_EXE", str(tmp_path / "no-existe.exe"))
    assert find_audiveris() is None
    # Sin variable: la ruta por defecto dentro de LOCALAPPDATA, si existe.
    monkeypatch.delenv("AUDIVERIS_EXE")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert find_audiveris() is None
    default = audiveris_engine.default_exe()
    default.parent.mkdir(parents=True)
    default.write_bytes(b"")
    assert find_audiveris() == default


def test_lee_mxl_sin_container(tmp_path):
    path = tmp_path / "x.mxl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("x.xml", "<score-partwise/>")
    assert audiveris_engine.read_mxl(path) == "<score-partwise/>"
