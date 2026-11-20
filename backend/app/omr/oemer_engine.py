"""Motor OMR basado en oemer (https://github.com/BreezeWhite/oemer).

Se corre como proceso aparte con su comando `oemer`, que deja un archivo
.musicxml en la carpeta de salida. La primera vez descarga sus modelos
(unos 218 MB), así que esa primera lectura tarda más.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from .base import OmrError

log = logging.getLogger(__name__)

# Una página en CPU tardó unos 5 minutos en la PC de desarrollo (E1-03); dejamos margen.
TIMEOUT_SECONDS = 15 * 60


def _oemer_command() -> str:
    scripts_dir = Path(sys.executable).parent
    found = shutil.which("oemer", path=str(scripts_dir)) or shutil.which("oemer")
    if not found:
        log.error("No se encuentra el comando 'oemer'. ¿Se instaló requirements.txt en el entorno virtual?")
        raise OmrError("El lector de partituras no está disponible en el servidor. Avisale a quien lo administra.")
    return found


class OemerEngine:
    name = "oemer"

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        out_dir = work_dir / f"oemer_{image_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [_oemer_command(), str(image_path), "-o", str(out_dir)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            log.warning("oemer superó %s s con %s", TIMEOUT_SECONDS, image_path)
            raise OmrError("La lectura tardó demasiado y se canceló.") from exc

        results = sorted(out_dir.glob("*.musicxml"))
        if proc.returncode != 0 or not results:
            # El detalle técnico (en inglés) va al log; el usuario ve un mensaje en español.
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-20:]
            log.error("oemer falló (código %s) con %s:\n%s", proc.returncode, image_path, "\n".join(tail))
            raise OmrError(
                "No pude leer la página. Probá con una imagen más nítida, derecha y con buena luz."
            )
        return results[0].read_text(encoding="utf-8")
