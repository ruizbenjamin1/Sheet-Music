"""API del backend: recibe un PDF o una foto de partitura y devuelve MusicXML.

Flujo:
  POST /api/jobs           -> sube el archivo, devuelve el id del trabajo
  GET  /api/jobs/{id}      -> estado y progreso
  GET  /api/jobs/{id}/musicxml -> resultado cuando está listo
"""

from __future__ import annotations

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .jobs import JobManager
from .omr import OemerEngine
from .pages import InputError, kind_of

MAX_UPLOAD_MB = 20

app = FastAPI(title="Partituras API", version="0.1.0")

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.state.jobs = JobManager(OemerEngine())


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "engine": app.state.jobs.engine.name}


@app.post("/api/jobs", status_code=202)
async def create_job(file: UploadFile = File(...)) -> dict:
    try:
        kind = kind_of(file.filename or "", file.content_type)
    except InputError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    data = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"El archivo pesa más de {MAX_UPLOAD_MB} MB.")
    if not data:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    job = app.state.jobs.submit(data, file.filename or "partitura", kind)
    return job.public()


def _get_job(job_id: str):
    job = app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No encuentro ese trabajo (puede haber vencido).")
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return _get_job(job_id).public()


@app.get("/api/jobs/{job_id}/musicxml")
def job_result(job_id: str) -> Response:
    job = _get_job(job_id)
    if job.musicxml is None:
        raise HTTPException(status_code=409, detail="Todavía no está listo.")
    return Response(content=job.musicxml, media_type="application/vnd.recordare.musicxml+xml")
