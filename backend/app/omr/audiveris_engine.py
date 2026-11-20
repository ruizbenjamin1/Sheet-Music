"""Motor OMR basado en Audiveris (https://github.com/Audiveris/audiveris, AGPL-3.0).

Audiveris es un programa aparte (Java, trae su propio runtime). No se instala con pip:
se busca el ejecutable en la variable de entorno `AUDIVERIS_EXE` o, si no está, en
`%LOCALAPPDATA%\\partituras-tools\\audiveris\\app\\Audiveris\\Audiveris.exe`.

Se corre en modo batch:
    Audiveris.exe -batch -export -output <carpeta> -- <imagen>
y deja `<nombre>.mxl` (MusicXML comprimido) o, si parte la partitura en movimientos,
`<nombre>.mvt1.mxl`, `<nombre>.mvt2.mxl`… Los movimientos se unen en orden, como si
fueran páginas.

Antes de leer, la imagen se pasa a gris, se normaliza la luz y se binariza (Otsu): con
la foto en color tal cual Audiveris no encuentra los pentagramas. Si es angosta, se
agranda: Audiveris necesita una interlínea de unos 20 px.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from ..merge import merge_pages
from ..preprocess import normalize_light
from .base import OmrError, current_subject, report_warning

log = logging.getLogger(__name__)

# Una página tarda 10–60 s (E1-19/E1-20); si tarda más, algo anda mal y conviene pasar al respaldo.
TIMEOUT_SECONDS = 3 * 60
# Ancho mínimo de la imagen que recibe Audiveris. Una hoja entera a este ancho deja una
# interlínea de ~20 px o más en partituras normales.
MIN_WIDTH_PX = 2500
# No agrandar más que esto (una foto chiquita no se arregla agrandándola mucho).
MAX_UPSCALE = 3.0

READ_FAILED = "No pude leer la página. Probá con una imagen más nítida, derecha y con buena luz."
MOVEMENT_SKIPPED = (
    "Un tramo de {subject} (el {n}) se leyó con {got} en vez de {want}; lo salteé."
)


def default_exe() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / "partituras-tools" / "audiveris" / "app" / "Audiveris" / "Audiveris.exe"


def find_audiveris() -> Path | None:
    """Ruta del ejecutable de Audiveris, o None si no está instalado."""
    configured = os.environ.get("AUDIVERIS_EXE", "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        log.warning("AUDIVERIS_EXE apunta a %s, que no existe; no se usa Audiveris", path)
        return None
    path = default_exe()
    return path if path is not None and path.is_file() else None


def build_command(exe: Path, image_path: Path, out_dir: Path) -> list[str]:
    return [str(exe), "-batch", "-export", "-output", str(out_dir), "--", str(image_path)]


def prepare_image(src: Path, dst: Path) -> Path:
    """Gris + luz normalizada + binarizada (Otsu) y, si es angosta, agrandada. Guarda en `dst`."""
    data = np.fromfile(str(src), dtype=np.uint8)
    gray = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None
    if gray is None:
        raise OmrError("No pude abrir la imagen para leerla. ¿Está dañada?")
    gray = normalize_light(gray)
    h, w = gray.shape[:2]
    ratio = min(MIN_WIDTH_PX / w, MAX_UPSCALE)
    if ratio > 1.05:
        gray = cv2.resize(gray, (round(w * ratio), round(h * ratio)), interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ok, buf = cv2.imencode(".png", binary)
    if not ok:
        raise OmrError(READ_FAILED)
    buf.tofile(str(dst))
    return dst


def read_mxl(path: Path) -> str:
    """Saca el MusicXML de un .mxl (zip con META-INF/container.xml)."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        root_file = None
        if "META-INF/container.xml" in names:
            container = ET.fromstring(z.read("META-INF/container.xml"))
            el = container.find(".//rootfile")
            if el is not None:
                root_file = el.get("full-path")
        if root_file not in names:
            xmls = [n for n in names if n.lower().endswith((".xml", ".musicxml")) and not n.startswith("META-INF/")]
            if not xmls:
                raise ValueError(f"{path.name} no trae MusicXML")
            root_file = xmls[0]
        return z.read(root_file).decode("utf-8")


_MVT = re.compile(r"\.mvt(\d+)\.mxl$", re.IGNORECASE)


def result_files(out_dir: Path) -> list[Path]:
    """Los .mxl que dejó Audiveris, en orden (`x.mxl` o `x.mvt1.mxl`, `x.mvt2.mxl`…, mvt10 después de mvt9)."""

    def key(p: Path) -> tuple[int, str]:
        m = _MVT.search(p.name)
        return (int(m.group(1)) if m else 0, p.name)

    return sorted(out_dir.glob("*.mxl"), key=key)


def staff_count(xml: str) -> int:
    """Pentagramas en total (una parte de piano con `<staves>2</staves>` cuenta 2)."""
    root = ET.fromstring(xml.encode("utf-8"))
    total = 0
    for part in root.findall("part"):
        staves = [int(s.text) for s in part.iter("staves") if (s.text or "").strip().isdigit()]
        total += max(staves, default=1)
    return total


def strip_source_paths(xml: str) -> str:
    """Audiveris escribe la ruta de la imagen en el servidor (`<source>`, `source-file`): se saca."""
    xml = re.sub(r"<source>.*?</source>", "", xml, flags=re.DOTALL)
    return re.sub(r'<miscellaneous-field name="source-[^"]*">.*?</miscellaneous-field>', "", xml, flags=re.DOTALL)


def join_movements(movements: list[str], subject: str = "esta página") -> tuple[str, list[str]]:
    """Une los movimientos en orden. Los que tienen otra cantidad de pentagramas que la mayoría
    (ante empate, gana el primero) se saltean con un aviso."""
    if len(movements) == 1:
        return movements[0], []
    counts = [staff_count(x) for x in movements]
    freq = Counter(counts)
    best = max(freq.values())
    want = next(c for c in counts if freq[c] == best)
    warnings: list[str] = []
    kept: list[str] = []
    for n, (xml, got) in enumerate(zip(movements, counts), start=1):
        if got != want:
            warnings.append(
                MOVEMENT_SKIPPED.format(subject=subject, n=n, got=_staves(got), want=_staves(want))
            )
            continue
        kept.append(xml)
    merged, more = merge_pages(kept, skipped_message=MOVEMENT_SKIPPED.replace("{subject}", subject))
    return merged, warnings + more


def _staves(n: int) -> str:
    return f"{n} pentagrama" if n == 1 else f"{n} pentagramas"


class AudiverisEngine:
    name = "audiveris"

    def __init__(self, exe: Path, timeout: float = TIMEOUT_SECONDS):
        self.exe = Path(exe)
        self.timeout = timeout

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        out_dir = work_dir / f"audiveris_{image_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            prepared = prepare_image(image_path, out_dir / f"{image_path.stem}.png")
        except OmrError:
            raise
        except Exception as exc:  # cv2 u otro error inesperado al preparar
            log.exception("No pude preparar %s para Audiveris", image_path)
            raise OmrError(READ_FAILED) from exc

        cmd = build_command(self.exe, prepared, out_dir)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                cwd=str(out_dir),
            )
        except subprocess.TimeoutExpired as exc:
            log.warning("Audiveris superó %s s con %s", self.timeout, image_path)
            raise OmrError("La lectura tardó demasiado y se canceló.") from exc
        except OSError as exc:
            log.error("No se pudo ejecutar Audiveris (%s): %s", self.exe, exc)
            raise OmrError("El lector de partituras no está disponible en el servidor. Avisale a quien lo administra.") from exc

        files = result_files(out_dir)
        if proc.returncode != 0 or not files:
            # El detalle técnico (en inglés) va al log; el usuario ve un mensaje en español.
            text = (proc.stdout or "") + "\n" + (proc.stderr or "")
            lines = text.strip().splitlines()
            causes = [ln for ln in lines if "Exception" in ln or "WARN" in ln or "ERROR" in ln][-10:]
            log.error(
                "Audiveris falló (código %s) con %s:\n%s",
                proc.returncode,
                image_path,
                "\n".join(causes + lines[-10:]),
            )
            raise OmrError(READ_FAILED)

        try:
            movements = [strip_source_paths(read_mxl(f)) for f in files]
            xml, warnings = join_movements(movements, current_subject())
        except Exception as exc:
            log.exception("No pude abrir el resultado de Audiveris (%s)", [f.name for f in files])
            raise OmrError(READ_FAILED) from exc
        if len(files) > 1:
            log.info("Audiveris partió %s en %s movimientos; se unieron", image_path.name, len(files))
        for w in warnings:
            report_warning(w)
        return xml
