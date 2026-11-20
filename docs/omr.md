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
| `app/main.py` | Rutas de la API (ver `docs/arquitectura.md`). Lee la subida por partes y revisa los primeros bytes |
| `app/upload_limit.py` | Middleware que corta `POST /api/jobs` apenas pasa los 20 MB (por `Content-Length` o contando bytes) |
| `app/pages.py` | Valida el tipo (nombre/content-type y primeros bytes: `%PDF`, PNG, JPEG, WEBP) y convierte PDF a PNG en gris a 300 ppp (PyMuPDF). Máximo 10 páginas. Rechaza PDF dañados o con contraseña |
| `app/omr/base.py` | Interfaz `OmrEngine.recognize(image_path, work_dir) -> str` y `OmrError` |
| `app/omr/oemer_engine.py` | Corre el comando `oemer <img> -o <dir>` y lee el `.musicxml` que deja. La salida de oemer va al log, no al usuario |
| `app/jobs.py` | Cola en memoria con un solo worker y hasta 5 trabajos pendientes (si no, 503). El archivo temporal se llama `upload.pdf/.png/.jpg/.webp` según el formato real, nunca según el nombre del usuario. Borra trabajos terminados a la hora |
| `app/merge.py` | Une el MusicXML de varias páginas con music21 y renumera compases. Si una página tiene otra cantidad de pentagramas que la primera, la saltea y deja un aviso en `warnings` |

Los errores inesperados se registran con `logging` (con el detalle técnico) y al usuario le llega un mensaje genérico en español.

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

## Pruebas

| Archivo | Qué prueba |
| --- | --- |
| `tests/helpers.py` | Genera PDF, PNG, JPEG y MusicXML mínimos dentro de la prueba |
| `tests/test_pages.py` | PDF de 1 y de varias páginas, límite de 10, PDF roto, truncado y con contraseña, detección por bytes |
| `tests/test_jobs_api.py` | API completa con un motor falso puesto en `app.state.jobs`: estados, sufijo, 415/413/400/503/404/409, errores en español |
| `tests/test_merge.py` | Unir dos páginas de piano (2 pentagramas) y el caso de distinta cantidad de pentagramas |
