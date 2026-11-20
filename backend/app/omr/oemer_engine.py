"""Motor OMR basado en oemer (https://github.com/BreezeWhite/oemer).

Se corre como proceso aparte con su comando `oemer`, que deja un archivo
.musicxml en la carpeta de salida. La primera vez descarga sus modelos
(unos cientos de MB), así que esa primera lectura tarda más.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .base import OmrError

# Una página en CPU suele tardar entre 1 y 3 minutos; dejamos margen.
TIMEOUT_SECONDS = 15 * 60


def _oemer_command() -> str:
    scripts_dir = Path(sys.executable).parent
    found = shutil.which("oemer", path=str(scripts_dir)) or shutil.which("oemer")
    if not found:
        raise OmrError("No encuentro el comando 'oemer'. ¿Instalaste requirements.txt en el entorno virtual?")
    return found


class OemerEngine:
    name = "oemer"

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        out_dir = work_dir / f"oemer_{image_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [_oemer_command(), str(image_path), "-o", str(out_dir)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise OmrError("La lectura tardó demasiado y se canceló.") from exc

        results = sorted(out_dir.glob("*.musicxml"))
        if proc.returncode != 0 or not results:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
            raise OmrError("oemer no pudo leer la página. " + " | ".join(tail))
        return results[0].read_text(encoding="utf-8")
