from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True, "engine": "oemer"}


def test_rejects_unsupported_file():
    client = TestClient(app)
    res = client.post("/api/jobs", files={"file": ("notas.txt", b"hola", "text/plain")})
    assert res.status_code == 415


def test_unknown_job_is_404():
    client = TestClient(app)
    assert client.get("/api/jobs/no-existe").status_code == 404
