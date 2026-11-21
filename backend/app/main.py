"""API del backend: recibe un PDF o una foto de partitura y devuelve MusicXML.

Flujo:
  POST /api/jobs           -> sube el archivo, devuelve el id del trabajo
  GET  /api/jobs/{id}      -> estado y progreso
  GET  /api/jobs/{id}/musicxml -> resultado cuando está listo
  DELETE /api/jobs/{id}    -> cancela la lectura (en cola o leyendo)
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .jobs import JobManager, QueueFullError
from .omr import default_engine
from .pages import InputError, check_upload, kind_of
from .upload_limit import UploadLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MAX_UPLOAD_MB = 20
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CHUNK_BYTES = 1024 * 1024

TOO_BIG = f"El archivo pesa más de {MAX_UPLOAD_MB} MB."
QUEUE_FULL = "Hay muchas partituras leyéndose en este momento. Probá de nuevo en unos minutos."

app = FastAPI(title="Partituras API", version="0.1.0")

# Corta la subida apenas pasa el límite, antes de que se lea todo el cuerpo.
# Margen de 1 MB para las cabeceras del multipart. Va antes que CORS para que
# CORS quede por fuera y el 413 llegue al navegador con sus cabeceras.
app.add_middleware(
    UploadLimitMiddleware, path="/api/jobs", max_bytes=MAX_UPLOAD_BYTES + 1024 * 1024, detail=TOO_BIG
)

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Audiveris (rápido) con oemer de respaldo; si Audiveris no está instalado, solo oemer.
app.state.jobs = JobManager(default_engine())
logging.getLogger(__name__).info("Motor de lectura: %s", app.state.jobs.engine.name)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Los errores de validación de FastAPI vienen en inglés: al usuario le damos uno en español.
    logging.getLogger(__name__).info("Solicitud inválida en %s: %s", request.url.path, exc.errors())
    return JSONResponse(status_code=400, content={"detail": "Falta el archivo o la solicitud está mal armada."})


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "engine": app.state.jobs.engine.name}


async def _read_limited(file: UploadFile) -> bytes:
    """Lee el archivo por partes y corta apenas pasa el límite."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=TOO_BIG)
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/api/jobs", status_code=202)
async def create_job(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "partitura"
    try:
        kind_of(filename, file.content_type)
    except InputError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    jobs: JobManager = app.state.jobs
    if jobs.is_full():
        raise HTTPException(status_code=503, detail=QUEUE_FULL)

    data = await _read_limited(file)
    if not data:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    try:
        fmt = check_upload(filename, file.content_type, data)
    except InputError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    try:
        job = jobs.submit(data, filename, fmt)
    except QueueFullError as exc:
        raise HTTPException(status_code=503, detail=QUEUE_FULL) from exc
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


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    """En cola: se saca. Leyendo: se corta el motor. Ya terminado: queda como estaba."""
    job = app.state.jobs.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No encuentro ese trabajo (puede haber vencido).")
    return job.public()
