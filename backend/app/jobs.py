"""Cola de trabajos en memoria: el OMR tarda minutos, así que corre en segundo plano.

Alcanza para la etapa 1 (un solo proceso, un usuario). Más adelante se puede
cambiar por una cola real (Redis, Supabase, etc.) sin tocar la API.
"""

from __future__ import annotations

import logging
import os
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
from .omr.base import Notifier, notifying
from .pages import SUFFIXES, InputError, kind_of_format, to_page_images
from .preprocess import preprocess_file

log = logging.getLogger(__name__)

# Los trabajos terminados se borran de memoria después de este tiempo.
JOB_TTL_SECONDS = 60 * 60
# Máximo de trabajos esperando o corriendo a la vez. Cada uno tarda minutos.
MAX_PENDING_JOBS = 5
MAX_FILENAME_CHARS = 200

UNEXPECTED_ERROR = "Hubo un error inesperado al leer la partitura. Probá de nuevo o con otro archivo."


def _keep_copy_for_dev(job: "Job", data: bytes, fmt: str) -> None:
    """Solo en desarrollo: si está la variable KEEP_UPLOADS_DIR, guarda una copia de lo subido
    (para medir lectores con fotos reales). En producción no se define y no se guarda nada."""
    target = os.environ.get("KEEP_UPLOADS_DIR")
    if not target:
        return
    try:
        folder = Path(target)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        (folder / f"subida-{stamp}-{job.id[:8]}{SUFFIXES[fmt]}").write_bytes(data)
    except OSError:
        log.exception("No pude guardar la copia de desarrollo de %s", job.id)


class QueueFullError(RuntimeError):
    """Hay demasiados trabajos esperando."""


@dataclass
class Job:
    id: str
    filename: str
    status: str = "queued"  # queued | running | done | error
    message: str = "En la fila, esperando turno…"
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


def _clean_filename(filename: str) -> str:
    # Solo para mostrar: sin carpetas y con un largo razonable. Nunca se usa para escribir en disco.
    name = Path((filename or "").replace("\\", "/")).name.strip()
    return name[:MAX_FILENAME_CHARS] or "partitura"


def _straighten_photo(src: Path, work_dir: Path, job_id: str) -> Path:
    """Recorta y endereza la hoja de una foto. Si no hace falta o falla, devuelve la original."""
    dst = work_dir / "photo_preprocessed.png"
    try:
        # Sin achicar: Audiveris necesita la resolución completa (achicada, confunde los
        # pentagramas del piano con dos instrumentos). oemer achica por su cuenta.
        if preprocess_file(src, dst, resize=False):
            log.info("Trabajo %s: foto recortada y enderezada", job_id)
            return dst
        log.info("Trabajo %s: no se encontró una hoja para recortar; se usa la foto original", job_id)
    except Exception:  # el preprocesado nunca debe cortar la lectura
        log.exception("Trabajo %s: falló el preprocesado; se usa la foto original", job_id)
    return src


class JobManager:
    def __init__(self, engine: OmrEngine, workers: int = 1, max_pending: int = MAX_PENDING_JOBS):
        self.engine = engine
        self.max_pending = max_pending
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # Un solo worker: el OMR usa mucha CPU y memoria.
        self._pool = ThreadPoolExecutor(max_workers=workers)

    def is_full(self) -> bool:
        with self._lock:
            return self._pending() >= self.max_pending

    def _pending(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))

    def submit(self, data: bytes, filename: str, fmt: str) -> Job:
        """fmt es el formato real del archivo: "pdf", "png", "jpeg" o "webp"."""
        if fmt not in SUFFIXES:
            raise ValueError(f"formato desconocido: {fmt}")
        self._cleanup()
        job = Job(id=uuid.uuid4().hex, filename=_clean_filename(filename))
        with self._lock:
            if self._pending() >= self.max_pending:
                raise QueueFullError()
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, data, fmt)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)

    def _run(self, job: Job, data: bytes, fmt: str) -> None:
        work_dir = Path(tempfile.mkdtemp(prefix="partitura_"))
        try:
            job.status, job.message = "running", "Preparando páginas"
            src = work_dir / f"upload{SUFFIXES[fmt]}"
            src.write_bytes(data)
            _keep_copy_for_dev(job, data, fmt)

            kind = kind_of_format(fmt)
            images = to_page_images(src, kind, work_dir / "pages")
            if kind == "image":
                # Solo fotos subidas: las páginas de un PDF ya vienen derechas y limpias.
                job.message = "Enderezando la foto"
                images = [_straighten_photo(images[0], work_dir, job.id)]
            job.pages = len(images)

            pages_xml = []
            engine_warnings: list[str] = []
            for i, image in enumerate(images, start=1):
                job.page = i
                job.message = f"Leyendo página {i} de {len(images)}"
                with notifying(self._notifier(job, kind, i, len(images), engine_warnings)):
                    pages_xml.append(self.engine.recognize(image, work_dir))

            job.message = "Armando la partitura"
            job.musicxml, merge_warnings = merge_pages(pages_xml)
            job.warnings = engine_warnings + merge_warnings
            job.status, job.message = "done", "Listo"
        except (InputError, OmrError) as exc:
            log.info("Trabajo %s falló: %s", job.id, exc)
            job.status, job.error, job.message = "error", str(exc), "Error"
        except Exception:  # el detalle técnico va al log; el usuario ve un mensaje en español
            log.exception("Error inesperado en el trabajo %s", job.id)
            job.status, job.error, job.message = "error", UNEXPECTED_ERROR, "Error"
        finally:
            job.finished_at = time.time()
            shutil.rmtree(work_dir, ignore_errors=True)

    @staticmethod
    def _notifier(job: Job, kind: str, page: int, pages: int, warnings: list[str]) -> Notifier:
        """Conecta los avisos del motor (ver `omr/base.py`) con el trabajo."""
        if kind == "image":
            subject = "esta foto"
        elif pages == 1:
            subject = "esta página"
        else:
            subject = f"la página {page}"

        def progress(text: str) -> None:
            job.message = text

        def warning(text: str) -> None:
            if text not in warnings:
                warnings.append(text)

        return Notifier(progress=progress, warning=warning, subject=subject)

    def _cleanup(self) -> None:
        now = time.time()
        with self._lock:
            old = [k for k, j in self._jobs.items() if j.finished_at and now - j.finished_at > JOB_TTL_SECONDS]
            for k in old:
                del self._jobs[k]
