"""Cancelar una lectura (E1-27) con motores falsos. El proceso "lento" es un Python que duerme."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.jobs import CANCELLED, JobManager
from app.main import app
from app.omr import FallbackEngine, OmrCancelled
from app.omr.base import CancelToken, cancellable, run_process
from tests.helpers import make_png, page_xml

SLEEP = [sys.executable, "-c", "import time; time.sleep(60)"]


# --- run_process ---


def test_run_process_devuelve_la_salida(tmp_path):
    proc = run_process(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper()); print('ñ', file=sys.stderr)"],
        input="hola",
        timeout=30,
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "HOLA" and proc.stderr.strip() == "ñ"


def test_run_process_tiempo_agotado_mata_el_proceso():
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_process(SLEEP, timeout=0.5)
    assert time.monotonic() - start < 20


def test_run_process_cancelado_mata_el_proceso():
    token = CancelToken()
    threading.Timer(0.5, token.cancel).start()
    start = time.monotonic()
    with cancellable(token), pytest.raises(OmrCancelled):
        run_process(SLEEP, timeout=60)
    assert time.monotonic() - start < 20


def test_run_process_ya_cancelado_no_arranca(monkeypatch):
    token = CancelToken()
    token.cancel()

    def popen(*args, **kwargs):
        raise AssertionError("no tenía que arrancar el proceso")

    monkeypatch.setattr(subprocess, "Popen", popen)
    with cancellable(token), pytest.raises(OmrCancelled):
        run_process(SLEEP, timeout=60)


# --- Motores ---


class SlowEngine:
    """Motor falso que corre un proceso de verdad (que duerme) con run_process, como los reales."""

    name = "lento"

    def __init__(self):
        self.started = threading.Event()
        self.calls = 0

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        self.calls += 1
        self.started.set()
        run_process(SLEEP, timeout=60)
        return page_xml(2, 1)


class QuickEngine:
    name = "rapido"

    def __init__(self):
        self.calls = 0

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        self.calls += 1
        return page_xml(2, 1)


def test_cancelar_no_pasa_al_respaldo(tmp_path):
    primary, fallback = SlowEngine(), QuickEngine()
    token = CancelToken()
    threading.Timer(0.5, token.cancel).start()
    with cancellable(token), pytest.raises(OmrCancelled):
        FallbackEngine(primary, fallback).recognize(tmp_path / "a.png", tmp_path)
    assert fallback.calls == 0


# --- API ---


@pytest.fixture
def client():
    original = app.state.jobs
    yield TestClient(app)
    app.state.jobs = original


def _install(engine) -> JobManager:
    manager = JobManager(engine)
    app.state.jobs = manager
    return manager


def _wait_status(client, job_id, statuses, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"el trabajo no llegó a {statuses}")


def _upload(client):
    res = client.post("/api/jobs", files={"file": ("foto.png", make_png(), "image/png")})
    assert res.status_code == 202
    return res.json()["id"]


def test_cancelar_mientras_lee_mata_el_motor(client, monkeypatch):
    monkeypatch.setattr("app.jobs.preprocess_file", lambda src, dst, resize=False: False)
    fallback = QuickEngine()
    slow = SlowEngine()
    manager = _install(FallbackEngine(slow, fallback))
    try:
        job_id = _upload(client)
        assert slow.started.wait(10)
        start = time.monotonic()
        res = client.delete(f"/api/jobs/{job_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "cancelled" and body["message"] == CANCELLED == "Cancelaste la lectura."
        assert body["error"] is None and body["has_result"] is False
        # El worker queda libre enseguida (se mató el proceso) y no se usó el respaldo.
        manager.shutdown(wait=True)
        assert time.monotonic() - start < 20
        assert fallback.calls == 0
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "cancelled" and job["message"] == CANCELLED
        assert client.get(f"/api/jobs/{job_id}/musicxml").status_code == 409
    finally:
        manager.shutdown(wait=True)


def test_cancelar_en_cola_lo_saca(client, monkeypatch):
    monkeypatch.setattr("app.jobs.preprocess_file", lambda src, dst, resize=False: False)
    gate = threading.Event()
    seen: list[Path] = []

    class Gated:
        name = "falso"

        def recognize(self, image_path, work_dir):
            seen.append(image_path)
            gate.wait(10)
            return page_xml(2, 1)

    manager = _install(Gated())
    try:
        first = _upload(client)
        _wait_status(client, first, ("running",))
        second = _upload(client)
        assert client.get(f"/api/jobs/{second}").json()["status"] == "queued"
        res = client.delete(f"/api/jobs/{second}")
        assert res.status_code == 200 and res.json()["status"] == "cancelled"
        gate.set()
        assert _wait_status(client, first, ("done",))["status"] == "done"
        manager.shutdown(wait=True)
        assert len(seen) == 1  # el segundo nunca llegó al motor
        job = client.get(f"/api/jobs/{second}").json()
        assert job["status"] == "cancelled" and job["message"] == CANCELLED
    finally:
        gate.set()
        manager.shutdown(wait=True)


def test_cancelar_uno_terminado_no_cambia_nada(client, monkeypatch):
    monkeypatch.setattr("app.jobs.preprocess_file", lambda src, dst, resize=False: False)
    manager = _install(QuickEngine())
    try:
        job_id = _upload(client)
        _wait_status(client, job_id, ("done",))
        res = client.delete(f"/api/jobs/{job_id}")
        assert res.status_code == 200 and res.json()["status"] == "done"
        assert client.get(f"/api/jobs/{job_id}/musicxml").status_code == 200
    finally:
        manager.shutdown(wait=True)


def test_cancelar_inexistente_da_404(client):
    manager = _install(QuickEngine())
    res = client.delete("/api/jobs/no-existe")
    assert res.status_code == 404
    assert "No encuentro ese trabajo" in res.json()["detail"]
    manager.shutdown(wait=True)
