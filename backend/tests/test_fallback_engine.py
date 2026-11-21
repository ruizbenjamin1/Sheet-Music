"""Pruebas del motor con respaldo y de la elección del motor por defecto (sin Audiveris ni oemer)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import omr
from app.jobs import JobManager
from app.main import app
from app.omr import FallbackEngine, OemerEngine, OmrError
from app.omr.base import Notifier, notifying
from app.omr.fallback_engine import has_music
from tests.helpers import make_jpeg, make_pdf, page_xml

EMPTY = '<?xml version="1.0"?><score-partwise><part-list/></score-partwise>'


class Fake:
    def __init__(self, name: str, result: str | None = None, error: Exception | None = None):
        self.name = name
        self.result = result
        self.error = error
        self.calls: list[Path] = []

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        self.calls.append(image_path)
        if self.error is not None:
            raise self.error
        return self.result


def _listen():
    progress: list[str] = []
    warnings: list[str] = []
    return progress, warnings, Notifier(progress=progress.append, warning=warnings.append, subject="esta foto")


def test_si_el_principal_anda_no_usa_el_respaldo(tmp_path):
    xml = page_xml(staves=2, measures=1)
    main, backup = Fake("rapido", result=xml), Fake("lento", result="otro")
    progress, warnings, notifier = _listen()
    with notifying(notifier):
        assert FallbackEngine(main, backup).recognize(tmp_path / "a.png", tmp_path) == xml
    assert backup.calls == [] and warnings == [] and progress == []


@pytest.mark.parametrize(
    "main",
    [
        Fake("rapido", error=OmrError("no")),
        Fake("rapido", error=RuntimeError("inesperado")),
        Fake("rapido", result=EMPTY),
        Fake("rapido", result="esto no es xml"),
    ],
)
def test_si_el_principal_falla_usa_el_respaldo_y_avisa(tmp_path, main):
    backup = Fake("lento", result="xml del respaldo")
    progress, warnings, notifier = _listen()
    image = tmp_path / "a.png"
    with notifying(notifier):
        assert FallbackEngine(main, backup).recognize(image, tmp_path) == "xml del respaldo"
    assert backup.calls == [image]  # la misma imagen que recibió el principal
    assert progress == ["La lectura rápida no funcionó con esta foto; usé el lector lento, puede tardar unos minutos"]
    assert warnings == ["La lectura rápida no funcionó con esta foto; se leyó con el lector lento."]


def test_si_fallan_los_dos_queda_el_error_del_respaldo(tmp_path):
    engine = FallbackEngine(Fake("rapido", error=OmrError("a")), Fake("lento", error=OmrError("b")))
    with pytest.raises(OmrError, match="b"):
        engine.recognize(tmp_path / "a.png", tmp_path)


def test_has_music():
    assert has_music(page_xml(staves=2, measures=1))
    assert not has_music(EMPTY)
    solo_silencios = page_xml(staves=1, measures=1).replace(
        "<pitch><step>C</step><octave>4</octave></pitch>", "<rest/>"
    )
    assert not has_music(solo_silencios)


def test_nombre_compuesto():
    assert FallbackEngine(Fake("audiveris"), Fake("oemer")).name == "audiveris+oemer"


def test_sin_audiveris_queda_solo_oemer(monkeypatch):
    monkeypatch.delenv("OMR_USE_CLAUDE", raising=False)
    monkeypatch.setattr(omr, "find_audiveris", lambda: None)
    engine = omr.default_engine()
    assert isinstance(engine, OemerEngine) and engine.name == "oemer"


def test_con_audiveris_usa_el_respaldo(monkeypatch, tmp_path):
    monkeypatch.delenv("OMR_USE_CLAUDE", raising=False)
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    engine = omr.default_engine()
    assert isinstance(engine, FallbackEngine) and engine.name == "audiveris+oemer"
    assert engine.primary.exe == tmp_path / "Audiveris.exe"


# --- Por la API: el aviso llega a `warnings` del trabajo ---


@pytest.fixture
def manager():
    original = app.state.jobs
    created: list[JobManager] = []

    def install(engine) -> JobManager:
        m = JobManager(engine)
        created.append(m)
        app.state.jobs = m
        return m

    yield install
    app.state.jobs = original
    for m in created:
        m.shutdown(wait=True)


def _wait(client, job_id):
    end = time.time() + 10
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("el trabajo no terminó a tiempo")


def test_api_foto_con_respaldo_avisa(manager, monkeypatch):
    monkeypatch.setattr("app.jobs.preprocess_file", lambda src, dst: False)
    manager(FallbackEngine(Fake("audiveris", error=OmrError("x")), Fake("oemer", result=page_xml(2, 2))))
    client = TestClient(app)
    job_id = client.post("/api/jobs", files={"file": ("foto.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    job = _wait(client, job_id)
    assert job["status"] == "done"
    assert job["warnings"] == ["La lectura rápida no funcionó con esta foto; se leyó con el lector lento."]


def test_api_pdf_dice_que_pagina(manager):
    calls = {"n": 0}

    class SecondPageFails:
        name = "audiveris"

        def recognize(self, image_path, work_dir):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OmrError("x")
            return page_xml(2, 1)

    manager(FallbackEngine(SecondPageFails(), Fake("oemer", result=page_xml(2, 1))))
    client = TestClient(app)
    job_id = client.post("/api/jobs", files={"file": ("vals.pdf", make_pdf(3), "application/pdf")}).json()["id"]
    job = _wait(client, job_id)
    assert job["status"] == "done"
    assert job["warnings"] == ["La lectura rápida no funcionó con la página 2; se leyó con el lector lento."]
