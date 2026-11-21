"""Lector con IA: le pide a Claude Code CLI (instalado en la PC, con la cuenta del usuario) que lea la imagen.

SOLO PARA DESARROLLO. Usa la cuenta de Claude de quien corre el backend, sin clave de API.
Para publicar la app hay que pasar a la API de Anthropic (ver docs/omr.md).

Se corre en modo no interactivo, con una sola herramienta (`Read`, para abrir la imagen) y
salida estructurada:
    claude -p --output-format json --json-schema <schema> --tools Read --allowedTools Read
           --add-dir <carpeta de la imagen> --permission-mode dontAsk ...
El pedido (prompt) va por stdin. La respuesta es un JSON con el formato intermedio de
`claude_score.py` (no MusicXML), que acá se convierte a MusicXML con music21.

- Ruta del CLI: `CLAUDE_CLI`; si no está, `claude` del PATH o `~/.local/bin/claude(.exe)`.
- Modelo: `CLAUDE_OMR_MODEL`; si no está, el que use el CLI por defecto.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .base import OmrError, report_progress
from .claude_score import SCORE_SCHEMA, ScoreFormatError, to_musicxml

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5 * 60
PROGRESS = "Leyendo con IA… puede tardar un par de minutos"
READ_FAILED = "La lectura con IA no funcionó. Probá con una imagen más nítida, derecha y con buena luz."

SYSTEM_PROMPT = (
    "You are an expert music engraver who transcribes piano sheet music from images into a compact JSON "
    "format. You only read the image you are given with the Read tool and answer with the requested JSON."
)

PROMPT = """Read the image at this path with the Read tool: {image}

It is a page (or a photo of a page) of piano sheet music. Transcribe EXACTLY what is printed, measure by measure,
into the JSON format of the schema. Rules:

- Ignore fingering numbers, pencil marks, handwritten notes, lyrics, dynamics and pedal marks.
- "title": the printed title if you can read one, else null. Do not make one up.
- "time": the time signature (C = 4/4 with symbol "common", cut time = 2/2 with symbol "cut").
- "fifths": the key signature (sharps positive, flats negative, 0 for none).
- "clefs": the clef at the start of each staff of the piano system, top to bottom (usually ["treble", "bass"]).
- "measures": every measure of the piece in order, across all systems of the page. For each measure, one entry per
  staff (top to bottom, same count as "clefs"), and for each staff a list of voices.
- Use a separate voice when one hand plays independent rhythms at the same time (for example triplet eighths
  with stems up and a held quarter note with stems down on the same staff). Notes that start together and have
  the same length go in ONE event as a chord ("pitches" with several notes).
- Each event: "pitches" with the sounding pitches (letter, accidental # or b, octave; middle C = C4). Apply the key
  signature and any accidental earlier in the same measure. Empty list = rest.
  "duration" in quarter notes as a fraction: "4" whole, "2" half, "1" quarter, "1/2" eighth, "1/4" sixteenth,
  "3/2" dotted quarter, "3/4" dotted eighth, "1/3" triplet eighth, "2/3" triplet quarter, "1/6" triplet sixteenth.
  "tie": true if the note is tied to the next note of the same voice.
- Every voice of every staff must add up to exactly the length of the measure (4 quarters in 4/4, 3 in 3/4,
  3 in 6/8...). Fill with rests where a voice is silent. If you are unsure about something, still give your best
  reading and keep the measure complete.
- Do not skip measures and do not invent measures that are not printed.
"""


def default_cli() -> Path | None:
    """`claude` del PATH o, si no está, la instalación por defecto en `~/.local/bin`."""
    found = shutil.which("claude")
    if found:
        return Path(found)
    home = Path.home() / ".local" / "bin"
    for name in ("claude.exe", "claude"):
        if (home / name).is_file():
            return home / name
    return None


def find_claude_cli() -> Path | None:
    configured = os.environ.get("CLAUDE_CLI", "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        found = shutil.which(configured)
        if found:
            return Path(found)
        log.warning("CLAUDE_CLI apunta a %s, que no existe; no se usa el lector con IA", configured)
        return None
    return default_cli()


def claude_enabled() -> bool:
    """El lector con IA solo se usa si se pide a propósito (`OMR_USE_CLAUDE=1`)."""
    return os.environ.get("OMR_USE_CLAUDE", "").strip() == "1"


def build_command(cli: Path, image_path: Path, model: str | None) -> list[str]:
    cmd = [
        str(cli),
        "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(SCORE_SCHEMA, separators=(",", ":")),
        "--tools", "Read",
        "--allowedTools", "Read",
        "--add-dir", str(image_path.parent),
        "--permission-mode", "dontAsk",
        "--system-prompt", SYSTEM_PROMPT,
        "--strict-mcp-config",
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    if model:
        cmd += ["--model", model]
    return cmd


def child_env() -> dict[str, str]:
    """Entorno para el CLI sin las variables de una sesión de Claude Code que lo haya lanzado.

    Si el backend se levanta desde Claude Code, hereda variables (`CLAUDECODE`, `CLAUDE_CODE_*`…) que
    hacen que el CLI crea que es una sub-sesión y no use su propio inicio de sesión.
    """
    keep = {"CLAUDE_CONFIG_DIR"}
    return {
        k: v
        for k, v in os.environ.items()
        if k in keep or not (k.upper().startswith("CLAUDE") or k.upper() == "AI_AGENT")
    }


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_cli_output(stdout: str) -> dict[str, Any]:
    """Saca el formato intermedio de la salida `--output-format json` del CLI.

    La salida es un objeto con `type: "result"`, `is_error`, `result` (texto) y, con `--json-schema`,
    `structured_output` (el objeto). Si no viene `structured_output`, se intenta leer `result` como JSON.
    Lanza ValueError si no hay nada usable.
    """
    text = (stdout or "").strip()
    if not text:
        raise ValueError("el CLI no devolvió nada")
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        # Por si viene más de una línea (por ejemplo avisos antes del JSON): la última que sea JSON.
        out = None
        for line in reversed(text.splitlines()):
            try:
                out = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if out is None:
            raise ValueError("la salida del CLI no es JSON")
    if isinstance(out, list):  # formato de lista de mensajes: el último "result"
        results = [m for m in out if isinstance(m, dict) and m.get("type") == "result"]
        if not results:
            raise ValueError("la salida del CLI no trae resultado")
        out = results[-1]
    if not isinstance(out, dict):
        raise ValueError("la salida del CLI no es un objeto")
    if out.get("is_error"):
        raise ValueError(f"el CLI devolvió un error: {str(out.get('result'))[:300]}")
    structured = out.get("structured_output")
    if isinstance(structured, dict):
        return structured
    result = out.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        body = result.strip()
        m = _FENCE.match(body)
        if m:
            body = m.group(1)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("el resultado del CLI no es JSON") from exc
        if isinstance(data, dict):
            return data
    raise ValueError("el CLI no devolvió la partitura")


class ClaudeEngine:
    name = "claude"

    def __init__(self, cli: Path, model: str | None = None, timeout: float = TIMEOUT_SECONDS):
        self.cli = Path(cli)
        self.model = model if model is not None else (os.environ.get("CLAUDE_OMR_MODEL", "").strip() or None)
        self.timeout = timeout

    def recognize(self, image_path: Path, work_dir: Path) -> str:
        image_path = Path(image_path).resolve()
        report_progress(PROGRESS)
        cmd = build_command(self.cli, image_path, self.model)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                input=PROMPT.format(image=image_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                cwd=str(work_dir),
                env=child_env(),
            )
        except subprocess.TimeoutExpired as exc:
            log.warning("Claude CLI superó %s s con %s", self.timeout, image_path)
            raise OmrError("La lectura con IA tardó demasiado y se canceló.") from exc
        except OSError as exc:
            log.error("No se pudo ejecutar Claude CLI (%s): %s", self.cli, exc)
            raise OmrError("El lector con IA no está disponible en el servidor.") from exc
        elapsed = time.monotonic() - start

        try:
            data = parse_cli_output(proc.stdout)
        except ValueError as exc:
            log.error(
                "Claude CLI no devolvió una lectura (código %s, %.0f s) con %s: %s\nstderr: %s\nstdout: %s",
                proc.returncode, elapsed, image_path, exc,
                (proc.stderr or "")[-1500:], (proc.stdout or "")[-1500:],
            )
            raise OmrError(READ_FAILED) from exc

        try:
            xml = to_musicxml(data)
        except (ScoreFormatError, ValueError, TypeError, KeyError) as exc:
            log.error("No pude armar la partitura con la lectura de la IA (%s): %s", image_path, exc)
            raise OmrError(READ_FAILED) from exc
        except Exception as exc:  # music21 puede fallar de formas variadas con datos raros
            log.exception("music21 falló con la lectura de la IA (%s)", image_path)
            raise OmrError(READ_FAILED) from exc
        log.info("Claude CLI leyó %s en %.0f s (%s compases)", image_path.name, elapsed, len(data.get("measures", [])))
        return xml
