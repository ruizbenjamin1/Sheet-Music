"""Interfaz común para los lectores OMR.

Cada motor recibe la ruta de UNA imagen de una página y devuelve el MusicXML
de esa página como texto. Así se puede cambiar oemer por homr o Audiveris
sin tocar el resto del backend.

Los motores pueden avisar cosas al trabajo en curso (mensaje de progreso o un aviso
para el usuario) con `report_progress` y `report_warning`. `jobs.py` los conecta con
`notifying(...)`; si nadie escucha (por ejemplo, en una prueba), no pasa nada.

Cancelar (E1-27): los motores corren sus procesos con `run_process`, que los anota en la
`CancelToken` del trabajo en curso (`cancellable(...)` en `jobs.py`). Al cancelar, se mata el
proceso (con sus hijos) y `run_process` lanza `OmrCancelled`, que no es un `OmrError`: no se
pasa al motor de respaldo.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


class OmrError(RuntimeError):
    """El motor no pudo leer la página."""


class OmrCancelled(Exception):
    """El usuario canceló la lectura. No es un OmrError: no se reintenta con otro motor."""


class OmrEngine(Protocol):
    name: str

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        """Lee la imagen y devuelve MusicXML. Puede usar work_dir para archivos temporales."""
        ...


@dataclass
class Notifier:
    progress: Callable[[str], None]
    warning: Callable[[str], None]
    # Cómo nombrar lo que se está leyendo en los mensajes: "esta foto", "la página 2"…
    subject: str = "esta página"


_current: ContextVar[Notifier | None] = ContextVar("omr_notifier", default=None)


@contextmanager
def notifying(notifier: Notifier) -> Iterator[None]:
    token = _current.set(notifier)
    try:
        yield
    finally:
        _current.reset(token)


def current_subject() -> str:
    n = _current.get()
    return n.subject if n is not None else "esta página"


def report_progress(text: str) -> None:
    n = _current.get()
    if n is not None:
        n.progress(text)


def report_warning(text: str) -> None:
    n = _current.get()
    if n is not None:
        n.warning(text)


# --- Cancelar ---


def kill_tree(proc: subprocess.Popen) -> None:
    """Mata el proceso y sus hijos (el python del venv, Audiveris o el CLI pueden lanzar otros)."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=15,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        log.warning("No pude matar el árbol del proceso %s; mato solo el proceso", proc.pid, exc_info=True)
    try:
        proc.kill()
    except OSError:
        pass


class CancelToken:
    """Marca de cancelación de un trabajo y los procesos que tiene corriendo."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._procs: set[subprocess.Popen] = set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            procs = list(self._procs)
        for proc in procs:
            kill_tree(proc)

    def check(self) -> None:
        if self._cancelled:
            raise OmrCancelled()

    def register(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.add(proc)
            cancelled = self._cancelled
        if cancelled:  # se canceló justo mientras arrancaba
            kill_tree(proc)

    def unregister(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(proc)


_cancel: ContextVar[CancelToken | None] = ContextVar("omr_cancel", default=None)


@contextmanager
def cancellable(token: CancelToken) -> Iterator[None]:
    reset = _cancel.set(token)
    try:
        yield
    finally:
        _cancel.reset(reset)


def check_cancelled() -> None:
    """Lanza OmrCancelled si se canceló el trabajo en curso."""
    token = _cancel.get()
    if token is not None:
        token.check()


def run_process(
    cmd: Sequence[str],
    *,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    input: str | None = None,
) -> subprocess.CompletedProcess:
    """Como `subprocess.run(..., capture_output=True, text=True)` en UTF-8, pero cancelable.

    Si se pasa `timeout`, mata el proceso (con sus hijos) y lanza `subprocess.TimeoutExpired`.
    Si se cancela el trabajo, lo mata y lanza `OmrCancelled`.
    """
    token = _cancel.get()
    if token is not None:
        token.check()
    proc = subprocess.Popen(
        list(cmd),
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        # Fuera de Windows, en su propio grupo, para poder matar también a los hijos.
        start_new_session=os.name != "nt",
    )
    if token is not None:
        token.register(proc)
    try:
        try:
            stdout, stderr = proc.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            try:
                proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                log.warning("El proceso %s no terminó después de matarlo", proc.pid)
            raise
        except BaseException:
            kill_tree(proc)
            raise
    finally:
        if token is not None:
            token.unregister(proc)
    if token is not None:
        token.check()
    return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)
