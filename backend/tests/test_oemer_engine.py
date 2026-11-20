"""Pruebas de OemerEngine sin correr oemer: se reemplaza el proceso por uno falso."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.omr import OemerEngine, OmrError
from app.omr import oemer_engine
from tests.helpers import page_xml


def _fake_run(returncode: int = 0, write: str | None = None, stderr: str = ""):
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        if write is not None:
            (out_dir / f"{Path(cmd[1]).stem}.musicxml").write_text(write, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    run.calls = calls
    return run


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "pages" / "page_01.png"
    path.parent.mkdir()
    path.write_bytes(b"no importa")
    return path


@pytest.fixture(autouse=True)
def fake_command(monkeypatch):
    monkeypatch.setattr(oemer_engine, "_oemer_command", lambda: "oemer")


def test_devuelve_el_musicxml(monkeypatch, tmp_path, image):
    xml = page_xml(staves=2, measures=1)
    run = _fake_run(write=xml)
    monkeypatch.setattr(oemer_engine.subprocess, "run", run)

    assert OemerEngine().recognize(image, tmp_path) == xml
    cmd = run.calls[0]
    assert cmd[:2] == ["oemer", str(image)]
    # Cada página tiene su propia carpeta de salida dentro del trabajo.
    assert Path(cmd[cmd.index("-o") + 1]).parent == tmp_path


def test_falla_de_oemer_da_mensaje_en_espanol(monkeypatch, tmp_path, image, caplog):
    monkeypatch.setattr(
        oemer_engine.subprocess, "run", _fake_run(returncode=1, stderr="IndexError: invalid index")
    )
    with pytest.raises(OmrError) as err:
        OemerEngine().recognize(image, tmp_path)
    assert "No pude leer la página" in str(err.value)
    assert "IndexError" not in str(err.value)
    assert "IndexError" in caplog.text  # el detalle técnico queda en el log


def test_sin_archivo_de_salida_es_error(monkeypatch, tmp_path, image):
    monkeypatch.setattr(oemer_engine.subprocess, "run", _fake_run(returncode=0, write=None))
    with pytest.raises(OmrError):
        OemerEngine().recognize(image, tmp_path)


def test_si_tarda_demasiado_se_cancela(monkeypatch, tmp_path, image):
    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(oemer_engine.subprocess, "run", run)
    with pytest.raises(OmrError) as err:
        OemerEngine().recognize(image, tmp_path)
    assert "tardó demasiado" in str(err.value)


def test_sin_comando_oemer(monkeypatch, tmp_path, image):
    monkeypatch.undo()
    monkeypatch.setattr(oemer_engine.shutil, "which", lambda *a, **k: None)
    with pytest.raises(OmrError) as err:
        OemerEngine().recognize(image, tmp_path)
    assert "no está disponible" in str(err.value)
