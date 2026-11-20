from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    # Depende de si Audiveris está instalado en esta compu (ver app.omr.default_engine).
    assert res.json() == {"ok": True, "engine": app.state.jobs.engine.name}
    assert app.state.jobs.engine.name in ("oemer", "audiveris+oemer")


def test_rejects_unsupported_file():
    client = TestClient(app)
    res = client.post("/api/jobs", files={"file": ("notas.txt", b"hola", "text/plain")})
    assert res.status_code == 415


def test_unknown_job_is_404():
    client = TestClient(app)
    assert client.get("/api/jobs/no-existe").status_code == 404
