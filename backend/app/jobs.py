"""Cola de trabajos en memoria: el OMR tarda minutos, así que corre en segundo plano.

Alcanza para la etapa 1 (un solo proceso, un usuario). Más adelante se puede
cambiar por una cola real (Redis, Supabase, etc.) sin tocar la API.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .merge import merge_pages
from .omr import OmrEngine, OmrError
from .pages import InputError, to_page_images

# Los trabajos terminados se borran de memoria después de este tiempo.
JOB_TTL_SECONDS = 60 * 60


@dataclass
class Job:
    id: str
    filename: str
    status: str = "queued"  # queued | running | done | error
    message: str = "En cola"
    page: int = 0
    pages: int = 0
    musicxml: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    finished_at: float | None = None

    def public(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "message": self.message,
            "page": self.page,
            "pages": self.pages,
            "warnings": self.warnings,
            "error": self.error,
            "has_result": self.musicxml is not None,
        }


class JobManager:
    def __init__(self, engine: OmrEngine, workers: int = 1):
        self.engine = engine
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # Un solo worker: el OMR usa mucha CPU y memoria.
        self._pool = ThreadPoolExecutor(max_workers=workers)

    def submit(self, data: bytes, filename: str, kind: str) -> Job:
        self._cleanup()
        job = Job(id=uuid.uuid4().hex, filename=filename)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, data, kind)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job: Job, data: bytes, kind: str) -> None:
        work_dir = Path(tempfile.mkdtemp(prefix="partitura_"))
        try:
            job.status, job.message = "running", "Preparando páginas"
            suffix = Path(job.filename).suffix.lower() or (".pdf" if kind == "pdf" else ".png")
            src = work_dir / f"upload{suffix}"
            src.write_bytes(data)

            images = to_page_images(src, kind, work_dir / "pages")
            job.pages = len(images)

            pages_xml = []
            for i, image in enumerate(images, start=1):
                job.page = i
                job.message = f"Leyendo página {i} de {len(images)}"
                pages_xml.append(self.engine.recognize(image, work_dir))

            job.message = "Armando la partitura"
            job.musicxml, job.warnings = merge_pages(pages_xml)
            job.status, job.message = "done", "Listo"
        except (InputError, OmrError) as exc:
            job.status, job.error, job.message = "error", str(exc), "Error"
        except Exception as exc:  # cualquier otra cosa: que el usuario vea algo útil
            job.status, job.message = "error", "Error"
            job.error = f"Error inesperado al leer la partitura: {exc}"
        finally:
            job.finished_at = time.time()
            shutil.rmtree(work_dir, ignore_errors=True)

    def _cleanup(self) -> None:
        now = time.time()
        with self._lock:
            old = [k for k, j in self._jobs.items() if j.finished_at and now - j.finished_at > JOB_TTL_SECONDS]
            for k in old:
                del self._jobs[k]
