"""Motor OMR basado en oemer (https://github.com/BreezeWhite/oemer).

Se corre como proceso aparte (`python -m app.omr.oemer_runner`, que aplica nuestra
corrección de E1-18 y llama a `oemer.ete.main()`), que deja un archivo .musicxml en
la carpeta de salida. La primera vez descarga sus modelos
(unos 218 MB), así que esa primera lectura tarda más.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
from pathlib import Path

from .base import OmrError

log = logging.getLogger(__name__)

# Una página en CPU tardó unos 5 minutos en la PC de desarrollo (E1-03); dejamos margen.
TIMEOUT_SECONDS = 15 * 60


# Carpeta `backend/`: desde ahí se encuentra el paquete `app` al correr el runner.
BACKEND_DIR = Path(__file__).resolve().parents[2]
RUNNER_MODULE = "app.omr.oemer_runner"


def _check_oemer_installed() -> None:
    if importlib.util.find_spec("oemer") is None:
        log.error("No está instalado oemer. ¿Se instaló requirements.txt en el entorno virtual?")
        raise OmrError("El lector de partituras no está disponible en el servidor. Avisale a quien lo administra.")


def build_command(image_path: Path, out_dir: Path) -> list[str]:
    # Mismo Python que el backend (el del venv), así usa el oemer instalado ahí.
    return [sys.executable, "-m", RUNNER_MODULE, str(image_path), "-o", str(out_dir)]


def _runner_env() -> dict[str, str]:
    env = dict(os.environ)
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(BACKEND_DIR) + (os.pathsep + old if old else "")
    return env


class OemerEngine:
    name = "oemer"

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        out_dir = work_dir / f"oemer_{image_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        _check_oemer_installed()
        cmd = build_command(image_path, out_dir)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SECONDS,
                cwd=str(BACKEND_DIR),
                env=_runner_env(),
            )
        except subprocess.TimeoutExpired as exc:
            log.warning("oemer superó %s s con %s", TIMEOUT_SECONDS, image_path)
            raise OmrError("La lectura tardó demasiado y se canceló.") from exc

        # Import acá y no arriba: si no, `python -m app.omr.oemer_runner` lo carga dos veces (aviso de runpy).
        from .oemer_runner import PATCH_FAILED_MARK

        for line in (proc.stderr or "").splitlines():
            if line.startswith(PATCH_FAILED_MARK):
                log.warning("oemer corrió sin la corrección de has_key (E1-18): %s", line)

        results = sorted(out_dir.glob("*.musicxml"))
        if proc.returncode != 0 or not results:
            # El detalle técnico (en inglés) va al log; el usuario ve un mensaje en español.
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-20:]
            log.error("oemer falló (código %s) con %s:\n%s", proc.returncode, image_path, "\n".join(tail))
            raise OmrError(
                "No pude leer la página. Probá con una imagen más nítida, derecha y con buena luz."
            )
        return results[0].read_text(encoding="utf-8")
