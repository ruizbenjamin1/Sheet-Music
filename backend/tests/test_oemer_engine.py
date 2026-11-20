"""Pruebas de OemerEngine sin correr oemer: se reemplaza el proceso por uno falso."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.omr import OemerEngine, OmrError
from app.omr import oemer_engine
from tests.helpers import page_xml


def _fake_run(returncode: int = 0, write: str | None = None, stderr: str = ""):
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        out_dir = Path(cmd[cmd.index("-o") + 1])
        if write is not None:
            image = Path(cmd[cmd.index("-o") - 1])
            (out_dir / f"{image.stem}.musicxml").write_text(write, encoding="utf-8")
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
def fake_installed(monkeypatch):
    # Las pruebas no dependen de que oemer esté instalado.
    monkeypatch.setattr(oemer_engine, "_check_oemer_installed", lambda: None)


def test_devuelve_el_musicxml(monkeypatch, tmp_path, image):
    xml = page_xml(staves=2, measures=1)
    run = _fake_run(write=xml)
    monkeypatch.setattr(oemer_engine.subprocess, "run", run)

    assert OemerEngine().recognize(image, tmp_path) == xml
    cmd, kwargs = run.calls[0]
    # Corre nuestro runner (con el parche de E1-18) con el mismo Python del backend.
    assert cmd[:5] == [sys.executable, "-m", "app.omr.oemer_runner", str(image), "-o"]
    # Cada página tiene su propia carpeta de salida dentro del trabajo.
    assert Path(cmd[5]).parent == tmp_path
    # Desde la carpeta backend/, para que se encuentre el paquete `app`.
    backend = Path(oemer_engine.__file__).resolve().parents[2]
    assert (backend / "app" / "omr" / "oemer_runner.py").exists()
    assert Path(kwargs["cwd"]) == backend
    assert kwargs["env"]["PYTHONPATH"].split(oemer_engine.os.pathsep)[0] == str(backend)


def test_avisa_en_el_log_si_no_se_aplico_el_parche(monkeypatch, tmp_path, image, caplog):
    stderr = "otra línea\nPARCHE_OEMER_NO_APLICADO: AttributeError('x')\n"
    monkeypatch.setattr(oemer_engine.subprocess, "run", _fake_run(write=page_xml(staves=1, measures=1), stderr=stderr))
    OemerEngine().recognize(image, tmp_path)
    assert "sin la corrección de has_key" in caplog.text


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


def test_sin_oemer_instalado(monkeypatch, tmp_path, image):
    monkeypatch.undo()
    monkeypatch.setattr(oemer_engine.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(OmrError) as err:
        OemerEngine().recognize(image, tmp_path)
    assert "no está disponible" in str(err.value)
