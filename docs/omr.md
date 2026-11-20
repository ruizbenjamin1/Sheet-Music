# Backend y lectura (OMR)

FastAPI en `backend/`, Python 3.12, entorno virtual en `backend/.venv`.

## Comandos

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
.\.venv\Scripts\python -m pytest -q
```

## Módulos

| Archivo | Qué hace |
| --- | --- |
| `app/main.py` | Rutas de la API (ver `docs/arquitectura.md`) |
| `app/pages.py` | Valida el tipo y convierte PDF a PNG en gris a 300 ppp (PyMuPDF). Máximo 10 páginas |
| `app/omr/base.py` | Interfaz `OmrEngine.recognize(image_path, work_dir) -> str` y `OmrError` |
| `app/omr/oemer_engine.py` | Corre el comando `oemer <img> -o <dir>` y lee el `.musicxml` que deja |
| `app/jobs.py` | Cola en memoria con un solo worker; borra trabajos terminados a la hora |
| `app/merge.py` | Une el MusicXML de varias páginas con music21 y renumera compases |

## oemer

- Versión 0.1.8. Opciones: `-o` carpeta de salida, `-d` sin enderezar (no usar con fotos), `--save-cache`.
- La primera vez descarga sus modelos (cientos de MB).
- En CPU tarda del orden de minutos por página: por eso los trabajos van en segundo plano.
- Al instalarse trajo `onnxruntime` y `onnxruntime-gpu` juntos; revisar en E1-03.

## Cambiar de motor

Crear otra clase con `name` y `recognize(...)` en `app/omr/` y cambiarla en `main.py`. Candidatos: homr (mejor en algunos casos, se instala desde git) y Audiveris (Java 17+, el más maduro).

## Reglas

- Mensajes de error en español, pensados para el usuario final.
- Nunca guardar en disco lo que sube el usuario más allá del trabajo: la carpeta temporal se borra al terminar.
- Las pruebas no corren el OMR real ni usan partituras con copyright: las de la API solo tocan rutas que no llaman al motor, y las de la Etapa 1 deben usar un motor falso.
