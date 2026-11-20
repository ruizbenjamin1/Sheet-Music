"""Pruebas de la API de trabajos con un motor falso (nunca se llama a oemer)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.jobs import JobManager
from app.main import MAX_UPLOAD_BYTES, app
from app.omr import OmrError
from tests.helpers import WEBP_HEAD, make_jpeg, make_pdf, make_png, page_xml, png_head


class FakeEngine:
    name = "falso"

    def __init__(self, fail_with: Exception | None = None, gate: threading.Event | None = None):
        self.fail_with = fail_with
        self.gate = gate
        self.seen: list[Path] = []

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        self.seen.append(image_path)
        if self.gate is not None:
            self.gate.wait(timeout=10)
        if self.fail_with is not None:
            raise self.fail_with
        assert image_path.exists()
        return page_xml(staves=2, measures=2)


@pytest.fixture
def use_engine():
    """Cambia app.state.jobs por un JobManager con el motor que se le pase y al final lo restaura."""
    original = app.state.jobs
    managers: list[JobManager] = []

    def install(engine, **kwargs) -> JobManager:
        manager = JobManager(engine, **kwargs)
        managers.append(manager)
        app.state.jobs = manager
        return manager

    yield install
    app.state.jobs = original
    for manager in managers:
        gate = getattr(manager.engine, "gate", None)
        if gate is not None:
            gate.set()
        manager.shutdown(wait=True)


@pytest.fixture
def client():
    return TestClient(app)


def _wait(client, job_id, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("el trabajo no terminó a tiempo")


def test_pdf_de_varias_paginas_llega_a_done(client, use_engine):
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": ("vals.pdf", make_pdf(3), "application/pdf")})
    assert res.status_code == 202
    body = res.json()
    assert body["filename"] == "vals.pdf" and body["has_result"] is False
    assert set(body) == {"id", "filename", "status", "message", "page", "pages", "warnings", "error", "has_result"}

    job = _wait(client, body["id"])
    assert job["status"] == "done", job
    assert job["pages"] == 3 and job["page"] == 3
    assert job["error"] is None and job["has_result"] is True
    assert [p.name for p in engine.seen] == ["page_01.png", "page_02.png", "page_03.png"]

    res = client.get(f"/api/jobs/{body['id']}/musicxml")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/vnd.recordare.musicxml+xml")
    assert "<score-partwise" in res.text
    # La carpeta temporal se borra al terminar.
    assert not engine.seen[0].exists()


@pytest.mark.parametrize(
    "name,data,ctype,suffix",
    [
        ("foto.png", make_png(), "image/png", ".png"),
        ("foto.jpg", make_jpeg(), "image/jpeg", ".jpg"),
        ("foto.webp", WEBP_HEAD, "image/webp", ".webp"),
    ],
)
def test_imagen_usa_sufijo_segun_el_tipo(client, use_engine, name, data, ctype, suffix):
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": (name, data, ctype)})
    assert res.status_code == 202
    assert _wait(client, res.json()["id"])["status"] == "done"
    assert engine.seen[0].name == f"upload{suffix}"


def test_sufijo_no_sale_del_nombre_del_usuario(client, use_engine):
    engine = FakeEngine()
    use_engine(engine)
    # Nombre con carpetas y sufijo engañoso: el archivo temporal igual se llama upload.png.
    res = client.post("/api/jobs", files={"file": ("../../x.exe.png", make_png(), "image/png")})
    assert res.status_code == 202
    assert res.json()["filename"] == "x.exe.png"
    _wait(client, res.json()["id"])
    assert engine.seen[0].name == "upload.png"


def test_formato_no_soportado(client, use_engine):
    use_engine(FakeEngine())
    res = client.post("/api/jobs", files={"file": ("notas.txt", b"hola", "text/plain")})
    assert res.status_code == 415
    assert "Formato no soportado" in res.json()["detail"]


def test_bytes_que_no_son_pdf(client, use_engine):
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": ("vals.pdf", b"esto es texto, no un PDF", "application/pdf")})
    assert res.status_code == 415
    assert "no parece un PDF" in res.json()["detail"]
    assert engine.seen == []


def test_archivo_vacio(client, use_engine):
    use_engine(FakeEngine())
    res = client.post("/api/jobs", files={"file": ("vals.pdf", b"", "application/pdf")})
    assert res.status_code == 400
    assert res.json()["detail"] == "El archivo está vacío."


def test_sin_archivo_da_error_en_espanol(client, use_engine):
    use_engine(FakeEngine())
    res = client.post("/api/jobs", data={"otra": "cosa"})
    assert res.status_code == 400
    assert "Falta el archivo" in res.json()["detail"]


def test_archivo_grande_413(client, use_engine):
    engine = FakeEngine()
    use_engine(engine)
    data = b"%PDF-1.7\n" + b"0" * (MAX_UPLOAD_BYTES + 2 * 1024 * 1024)
    res = client.post("/api/jobs", files={"file": ("grande.pdf", data, "application/pdf")})
    assert res.status_code == 413
    assert "20 MB" in res.json()["detail"]
    assert engine.seen == []


def test_archivo_apenas_mayor_al_limite_413(client, use_engine):
    # Entra en el margen del middleware, pero la lectura por partes lo corta igual.
    use_engine(FakeEngine())
    data = b"%PDF-1.7\n" + b"0" * MAX_UPLOAD_BYTES
    res = client.post("/api/jobs", files={"file": ("grande.pdf", data, "application/pdf")})
    assert res.status_code == 413
    assert "20 MB" in res.json()["detail"]


def test_subida_por_partes_sin_content_length_se_corta(client, use_engine):
    use_engine(FakeEngine())

    def body():
        chunk = b"0" * (1024 * 1024)
        for _ in range(40):  # 40 MB si no se cortara
            yield chunk

    res = client.post(
        "/api/jobs",
        content=body(),
        headers={"content-type": "multipart/form-data; boundary=xyz"},
    )
    assert res.status_code == 413
    assert "20 MB" in res.json()["detail"]


def test_error_del_motor_se_muestra_en_espanol(client, use_engine):
    use_engine(FakeEngine(fail_with=OmrError("No pude leer la página.")))
    res = client.post("/api/jobs", files={"file": ("foto.png", make_png(), "image/png")})
    job = _wait(client, res.json()["id"])
    assert job["status"] == "error"
    assert job["error"] == "No pude leer la página."
    assert job["has_result"] is False
    assert client.get(f"/api/jobs/{job['id']}/musicxml").status_code == 409


def test_error_inesperado_no_muestra_detalle_tecnico(client, use_engine, caplog):
    use_engine(FakeEngine(fail_with=KeyError("internal stack detail")))
    res = client.post("/api/jobs", files={"file": ("foto.png", make_png(), "image/png")})
    job = _wait(client, res.json()["id"])
    assert job["status"] == "error"
    assert "internal" not in job["error"]
    assert job["error"].startswith("Hubo un error inesperado")
    assert "internal stack detail" in caplog.text  # el detalle queda en el log


def test_pdf_con_demasiadas_paginas_termina_en_error(client, use_engine):
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": ("largo.pdf", make_pdf(11), "application/pdf")})
    job = _wait(client, res.json()["id"])
    assert job["status"] == "error"
    assert "máximo es 10" in job["error"]
    assert engine.seen == []


def test_resultado_no_listo_409(client, use_engine):
    gate = threading.Event()
    use_engine(FakeEngine(gate=gate))
    res = client.post("/api/jobs", files={"file": ("foto.png", make_png(), "image/png")})
    job_id = res.json()["id"]
    res = client.get(f"/api/jobs/{job_id}/musicxml")
    assert res.status_code == 409
    assert res.json()["detail"] == "Todavía no está listo."
    gate.set()
    assert _wait(client, job_id)["status"] == "done"


def test_cola_llena_503(client, use_engine):
    gate = threading.Event()
    use_engine(FakeEngine(gate=gate), max_pending=2)
    files = {"file": ("foto.png", make_png(), "image/png")}
    ids = [client.post("/api/jobs", files=files).json()["id"] for _ in range(2)]
    res = client.post("/api/jobs", files=files)
    assert res.status_code == 503
    assert "Probá de nuevo" in res.json()["detail"]
    gate.set()
    for job_id in ids:
        assert _wait(client, job_id)["status"] == "done"
    # Con la cola libre vuelve a aceptar.
    assert client.post("/api/jobs", files=files).status_code == 202


def test_trabajo_inexistente_404(client):
    res = client.get("/api/jobs/no-existe/musicxml")
    assert res.status_code == 404
    assert "No encuentro ese trabajo" in res.json()["detail"]


def test_trabajos_vencidos_se_borran(client, use_engine):
    manager = use_engine(FakeEngine())
    files = {"file": ("foto.png", make_png(), "image/png")}
    job_id = client.post("/api/jobs", files=files).json()["id"]
    _wait(client, job_id)
    manager.get(job_id).finished_at -= 2 * 60 * 60
    client.post("/api/jobs", files=files)
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_trabajo_en_espera_dice_que_espera_turno(client, use_engine):
    gate = threading.Event()
    use_engine(FakeEngine(gate=gate))
    files = {"file": ("foto.png", make_png(), "image/png")}
    first = client.post("/api/jobs", files=files).json()["id"]
    second = client.post("/api/jobs", files=files).json()
    assert second["status"] == "queued"
    assert second["message"] == "En la fila, esperando turno…"
    assert client.get(f"/api/jobs/{second['id']}").json()["message"] == "En la fila, esperando turno…"
    gate.set()
    for job_id in (first, second["id"]):
        assert _wait(client, job_id)["status"] == "done"


def test_imagen_gigante_termina_en_error_sin_llamar_al_motor(client, use_engine):
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": ("foto.png", png_head(30000, 20000), "image/png")})
    assert res.status_code == 202
    job = _wait(client, res.json()["id"])
    assert job["status"] == "error"
    assert "demasiado grande" in job["error"]
    assert engine.seen == []


def _spy_preprocess(monkeypatch, result=False, fail=False):
    import app.jobs as jobs_module

    calls: list[Path] = []

    def fake(src: Path, dst: Path, **kwargs) -> bool:
        calls.append(src)
        if fail:
            raise RuntimeError("se rompió el preprocesado")
        if result:
            dst.write_bytes(src.read_bytes())
        return result

    monkeypatch.setattr(jobs_module, "preprocess_file", fake)
    return calls


def test_foto_pasa_por_el_preprocesado(client, use_engine, monkeypatch):
    calls = _spy_preprocess(monkeypatch, result=True)
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": ("foto.jpg", make_jpeg(), "image/jpeg")})
    assert _wait(client, res.json()["id"])["status"] == "done"
    assert [p.name for p in calls] == ["upload.jpg"]
    # El motor lee la foto enderezada, no la original.
    assert engine.seen[0].name == "photo_preprocessed.png"


def test_pdf_no_pasa_por_el_preprocesado(client, use_engine, monkeypatch):
    calls = _spy_preprocess(monkeypatch, result=True)
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": ("vals.pdf", make_pdf(2), "application/pdf")})
    assert _wait(client, res.json()["id"])["status"] == "done"
    assert calls == []
    assert [p.name for p in engine.seen] == ["page_01.png", "page_02.png"]


def test_si_el_preprocesado_falla_sigue_con_la_original(client, use_engine, monkeypatch, caplog):
    _spy_preprocess(monkeypatch, fail=True)
    engine = FakeEngine()
    use_engine(engine)
    res = client.post("/api/jobs", files={"file": ("foto.png", make_png(), "image/png")})
    job = _wait(client, res.json()["id"])
    assert job["status"] == "done", job
    assert engine.seen[0].name == "upload.png"
    assert "falló el preprocesado" in caplog.text


def test_mensaje_enderezando_la_foto(client, use_engine, monkeypatch):
    import app.jobs as jobs_module

    seen_messages: list[str] = []
    manager = use_engine(FakeEngine())

    def fake(src: Path, dst: Path, **kwargs) -> bool:
        seen_messages.extend(j.message for j in manager._jobs.values())
        return False

    monkeypatch.setattr(jobs_module, "preprocess_file", fake)
    res = client.post("/api/jobs", files={"file": ("foto.png", make_png(), "image/png")})
    _wait(client, res.json()["id"])
    assert seen_messages == ["Enderezando la foto"]


def test_copia_de_desarrollo_solo_con_variable(client, use_engine, tmp_path, monkeypatch):
    use_engine(FakeEngine())
    monkeypatch.delenv("KEEP_UPLOADS_DIR", raising=False)
    res = client.post("/api/jobs", files={"file": ("a.pdf", make_pdf(1), "application/pdf")})
    _wait(client, res.json()["id"])
    assert not any(tmp_path.iterdir())

    monkeypatch.setenv("KEEP_UPLOADS_DIR", str(tmp_path / "copias"))
    res = client.post("/api/jobs", files={"file": ("b.pdf", make_pdf(1), "application/pdf")})
    _wait(client, res.json()["id"])
    copias = list((tmp_path / "copias").iterdir())
    assert len(copias) == 1 and copias[0].suffix == ".pdf"
