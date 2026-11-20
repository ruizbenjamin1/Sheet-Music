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
| `app/merge.py` | Une el MusicXML de varias páginas con music21 y renumera compases. Si una página tiene otra cantidad de pentagramas que la primera, la saltea y deja un aviso en `warnings`. Exporta sin `makeNotation`: si no, music21 "arregla" los compases que no cierran (oemer deja muchos), mueve notas entre compases y agrega compases vacíos |

Los errores inesperados se registran con `logging` (con el detalle técnico) y al usuario le llega un mensaje genérico en español.

## oemer

- Versión 0.1.8 (licencia MIT). Opciones: `-o` carpeta de salida, `-d` sin enderezar (no usar con fotos), `--save-cache`.
- Deja `<nombre>.musicxml` y `<nombre>_teaser.png` en la carpeta de salida.

### Modelos (descarga la primera vez)

- La primera corrida, si no existe `checkpoints/unet_big/model.onnx`, baja 4 archivos de
  `https://github.com/BreezeWhite/oemer/releases/download/checkpoints/` (`1st_model.onnx`, `1st_weights.h5`,
  `2nd_model.onnx`, `2nd_weights.h5`): **unos 218 MB** en total (70,8 + 71,0 + 38,4 + 38,6 MB).
- Quedan **dentro del paquete instalado**: `backend/.venv/Lib/site-packages/oemer/checkpoints/unet_big/` y `.../seg_net/`.
  Si se borra o recrea el venv, se vuelven a bajar.
- En E1-03 la descarga tardó unos 20 s. No hay que hacer nada a mano.
- Ojo: oemer solo mira si existe `unet_big/model.onnx`. Si la descarga se corta a la mitad, queda un archivo
  incompleto y todas las lecturas fallan: borrar las carpetas `checkpoints/*/model.onnx` y `weights.h5` y volver a correr.

### Tiempos (medido en E1-03, PC de desarrollo, solo CPU)

| Qué | Tiempo |
| --- | --- |
| `oemer` directo, imagen limpia (3000×1704), modelos ya bajados | 291 s (~5 min) |
| `oemer` directo, imagen "tipo foto" (rotada 2°, ruido, luz despareja) | 283 s (~5 min) |
| Por la API, PDF de 2 páginas (subida, conversión a 300 ppp, 2 lecturas y unión) | 596 s y 631 s (~10 min, ~5 min por página) |
| Primera corrida con descarga de modelos | lo de arriba + ~20 s |

Casi todo el tiempo es la inferencia de los dos modelos (~1,5–2 min y ~3 min). oemer achica cada página a un
tamaño fijo antes de leerla, así que el tiempo por página no depende mucho de la resolución. Por eso los trabajos
van en segundo plano y el límite por página es de 15 min (`TIMEOUT_SECONDS`).

### Precisión (E1-03, "Oda a la alegría" generada con OSMD, 8 compases, 2 pentagramas, 39 notas)

Se comparó compás por compás (altura + duración, alineación óptima) contra el MusicXML original:

| Imagen | Compases | Notas correctas | Solo altura | Notas de más |
| --- | --- | --- | --- | --- |
| Limpia (PNG) | 8 de 8 | 21/39 (54 %) | 62 % | 4 |
| Tipo foto (JPG) | 8 de 8 | 30/39 (77 %) | 90 % | 6 |
| PDF de 2 páginas (limpia + tipo foto) unido | 16 de 16 | 51/78 (65 %) | 76 % | 10 |

- Lo que más falla: las **redondas** (nota entera, sin plica) de la clave de fa casi no las ve (las escribe como
  silencios de compás), y en la
  limpia se saltea varias notas del pentagrama de arriba (sobre todo F4). Las corcheas con puntillo a veces
  salen como negras. En la limpia leyó armadura de Sol mayor (un sostenido) en vez de Do: por eso aparece algún F#.
- oemer no escribe `<time>` (compás 4/4), repite números de compás y deja compases que no suman lo que deberían.
- En esta prueba (una corrida de cada una) la imagen tipo foto salió mejor que la limpia. oemer se entrenó con fotos y
  escaneos; una imagen generada, perfecta y con mucho blanco parece confundirlo más.

### Dependencias que hubo que fijar (E1-03)

- **onnxruntime 1.27.0.** Desde 1.28 onnxruntime rechaza el modelo `unet_big` de oemer
  (`ConvTranspose ... pads must not contain negative values`) y toda lectura falla. Se probaron 1.20 a 1.32:
  1.27.0 es la última que anda.
- **`onnxruntime` y `onnxruntime-gpu` juntos, en la misma versión.** oemer pide `onnxruntime-gpu` y pymupdf 2.x
  pide `onnxruntime`; pip no deja excluir una dependencia, así que `pip install -r` instala los dos. Los dos
  paquetes escriben la misma carpeta `onnxruntime/`: con la misma versión el resultado anda (comprobado), con
  versiones distintas queda una mezcla. **No desinstalar uno solo**: borra archivos que usa el otro; si hace
  falta, desinstalar los dos y reinstalar con `pip install -r requirements.txt`.
  En esta PC quedó activo el de CPU (`['AzureExecutionProvider', 'CPUExecutionProvider']`), sin avisos de CUDA.
  Si queda activo el de GPU y no hay CUDA, oemer igual anda en CPU pero deja en el log un error
  `TryGetProviderInfo_CUDA` por cada modelo (no afecta al usuario).
  Alternativa solo CPU (por ejemplo en un servidor): instalar todo menos oemer y después
  `pip install --no-deps oemer==0.1.8`; no se hizo porque rompe el `pip install -r requirements.txt` de un solo paso.
- **opencv-python-headless 4.14.0.94.** Con OpenCV 5, `HoughLinesP` devuelve otra forma y oemer se cae con
  `IndexError: invalid index to scalar variable` en `bbox.find_lines`.
- Avisos que se pueden ignorar en el log: `InconsistentVersionWarning` de scikit-learn (oemer trae modelos
  guardados con 1.2.0) y `RuntimeWarning: overflow` en `build_system.py`.

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
| `tests/test_oemer_engine.py` | `OemerEngine` con el proceso reemplazado por uno falso: lee el `.musicxml`, error de oemer y sin salida (mensaje en español, detalle al log), tiempo agotado, comando ausente |
| `tests/test_merge.py` | Unir dos páginas de piano (2 pentagramas), el caso de distinta cantidad de pentagramas, y que una página "tipo oemer" (compases que no cierran) no se reacomode al unir |
