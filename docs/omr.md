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
| `app/pages.py` | Valida el tipo (nombre/content-type y primeros bytes: `%PDF`, PNG, JPEG, WEBP) y convierte PDF a PNG en gris a 300 ppp (PyMuPDF), bajando los ppp si la página es tan grande que el lado mayor pasaría de 5000 px (`PDF_MAX_SIDE_PX`). Máximo 10 páginas. Rechaza PDF dañados o con contraseña. Las imágenes se revisan leyendo solo el encabezado (PNG, JPEG, WEBP), sin decodificarlas: más de 60 megapíxeles (`MAX_IMAGE_PIXELS`) o tamaño ilegible es error. Ver "Tope de píxeles" |
| `app/omr/base.py` | Interfaz `OmrEngine.recognize(image_path, work_dir) -> str` y `OmrError` |
| `app/omr/oemer_engine.py` | Corre `python -m app.omr.oemer_runner <img> -o <dir>` con el mismo Python del backend (`sys.executable`), con `cwd` en `backend/` y `backend/` al principio de `PYTHONPATH`, y lee el `.musicxml` que deja. La salida de oemer va al log, no al usuario. Si el runner avisa que no pudo aplicar el parche, lo deja en el log como advertencia |
| `app/omr/oemer_runner.py` | Aplica en memoria la corrección de `Measure.has_key` de oemer (ver "Parche de oemer (E1-18)") y llama a `oemer.ete.main()`, que lee los mismos argumentos que el comando `oemer`. No toca `site-packages` |
| `app/jobs.py` | Cola en memoria con un solo worker y hasta 5 trabajos pendientes (si no, 503). El archivo temporal se llama `upload.pdf/.png/.jpg/.webp` según el formato real, nunca según el nombre del usuario. Borra trabajos terminados a la hora. Un trabajo nuevo arranca con el mensaje "En la fila, esperando turno…". Si se subió una imagen (foto), antes del OMR la pasa por `preprocess_file` con el mensaje "Enderezando la foto" y le da al motor `photo_preprocessed.png`; si no encontró hoja o el preprocesado falla, sigue con la imagen original y lo deja en el log. Las páginas que vienen de un PDF no se preprocesan |
| `app/preprocess.py` | Se usa solo con fotos subidas (ver `jobs.py`). Prepara una foto para el OMR: busca la hoja (zona clara respecto del fondo y de lo que la rodea, que deja afuera anillado y teclado), corrige la perspectiva, recorta un 1,5 % de borde, normaliza la luz dividiendo por el fondo (sin binarizar, para no perder líneas finas) y la lleva a ~3,7 MP. Si no encuentra una hoja clara (escaneo, sin contraste), devuelve la imagen original sin tocar |
| `app/merge.py` | Une el MusicXML de las páginas con music21 y renumera los compases siempre, aunque sea una sola página (oemer repite números). Saca el título y el compositor inventados (ver abajo). Si una página tiene otra cantidad de pentagramas que la primera, la saltea y deja un aviso en `warnings`. Exporta sin `makeNotation`: si no, music21 "arregla" los compases que no cierran (oemer deja muchos), mueve notas entre compases y agrega compases vacíos |

### Título y compositor

oemer escribe como título (`<work-title>`) el nombre de la imagen temporal (`Upload`, `Page_01`) y como compositor
`Transcribed by Oemer`; al exportar, music21 pone `<movement-title>` con lo mismo (o `Music21 Fragment` y `Music21`
si no hay nada). Ninguno es real: el OMR no lee títulos. `merge.py` borra `<work>`, `<movement-title>`,
`<movement-number>` y los `<creator>` con esos compositores inventados. Sin título, el frontend muestra el nombre del
archivo (`fallbackTitle` en `ScoreView.tsx`, que carga con `osmd.load(xml, '')` para que OSMD no ponga "Untitled Score").

### Tope de píxeles (E1-15)

- **PDF:** cada página se rasteriza a 300 ppp, salvo que el lado mayor pase de 5000 px; ahí se bajan los ppp para que
  quede en 5000 px (una A4 a 300 ppp da 3508 px, así que las hojas normales no cambian). Una página vacía de 3 × 2 m
  ya no ocupa GB de memoria.
- **Imágenes:** se lee el ancho y alto del encabezado (PNG `IHDR`, JPEG `SOFn`, WEBP `VP8`/`VP8L`/`VP8X`) antes de que
  nadie la decodifique. Más de 60 megapíxeles: el trabajo termina en error con "La imagen es demasiado grande (…). El
  máximo es de 60 megapíxeles: achicala o sacá la foto con menos resolución." Se eligió rechazar y no achicar porque
  achicar obliga a decodificarla entera en el backend (justo lo que se quiere evitar), y 60 MP deja pasar las fotos de
  celular de 48–50 MP. Por debajo del tope no se achica nada: oemer ya lleva cada imagen a unos 3,7 MP antes de leerla.
- Si el encabezado no se entiende, el trabajo termina en error con "No pude leer la imagen. ¿Está dañada?".

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

### Preprocesado de fotos

Las fotos de celular traen fondo (mesa, teclado, anillado), perspectiva y luz despareja. oemer las endereza un poco,
pero con las fotos de Benjamin se caía (E1-18) o leía mal. `preprocess.py` recorta la hoja, corrige la perspectiva y
normaliza la luz antes de pasársela a oemer. Solo se aplica a imágenes subidas: un PDF ya viene derecho y limpio, y
el preprocesado no le agregaría nada (y podría recortar mal una página con mucho blanco). Si no encuentra una hoja
clara, o falla por cualquier motivo, se usa la imagen original: nunca corta la lectura.

### Parche de oemer (E1-18)

oemer 0.1.8 tiene un bug en `build_system.Measure.has_key()`: toma los símbolos donde debería estar la armadura y
hace `all(isinstance(s, Sfn) for s in syms)`. Si el compás tiene menos símbolos que pentagramas, la lista queda vacía,
`all([])` da `True`, oemer cree que hay armadura y `get_key()` hace `sfns_cands[0]` con una lista vacía:
`IndexError` y se pierde la lectura de toda la página. Pasaba con fotos reales.

La corrección (en `app/omr/oemer_runner.py`) exige que haya exactamente tantos símbolos como pentagramas y que todos
sean alteraciones. Se aplica **en memoria** en el proceso que corre oemer (no se modifica `site-packages`, así que un
`pip install` no la pisa ni hace falta un fork). Antes de aplicarla, el runner revisa que existan
`Measure.has_key`, `get_total_track_nums` y `Sfn`; si oemer cambió y no están, corre sin el parche y escribe
`PARCHE_OEMER_NO_APLICADO: …` en stderr, que `OemerEngine` pasa al log como advertencia. Si se actualiza oemer,
revisar si el bug sigue y si el parche todavía hace falta.

## Comparación con Audiveris (E1-19)

Se probó **Audiveris 5.11.0** (licencia **AGPL-3.0**), la última release estable a 2026-11-20. No está conectado al
backend: solo se midió.

- Instalación (fuera del repo, sin tocar el sistema): `Audiveris-5.11.0-windowsConsole-x86_64.msi` (85 MB) extraído
  en `%LOCALAPPDATA%\partituras-tools\audiveris\app\Audiveris\` (163 MB). Trae su propio Java (OpenJDK 25.0.3) y
  Tesseract 5.5.2; no usa el Java 8 del PATH ni cambia `JAVA_HOME`. `msiexec /a` falló en esta PC (código 1622), así
  que el `.msi` se abrió con `msilib` + `olefile` y `expand.exe` de Windows.
- Comando: `Audiveris.exe -batch -export -output <carpeta> -- <imagen>` deja `<nombre>.mxl` (MusicXML comprimido).
- Tiempo por página (CPU, Ryzen 5 3600): **10–14 s** con imágenes de ~2000 px y **19–22 s** escaladas a ~3000 px,
  contra ~300 s de oemer. Arrancar Java cuesta ~1,5–2 s de eso (`-version` tarda 1,5 s); el resto es la lectura.
- Necesita interlínea de unos 20 px: las fotos de WhatsApp sin recortar (interlínea 7–8 px) las rechaza
  ("too low interline value"). Escaladas ×2,6 a ×2,9 tampoco anduvieron bien (una sin pentagramas, otra mal armada).

| Imagen | oemer | Audiveris |
| --- | --- | --- |
| Oda limpia (verdad conocida, 39 notas) | ~290 s, 8/8 compases, 54 % | 10–12 s, 8/8 compases, **100 %** |
| Oda tipo foto | ~285 s, 8/8, 77 % | 11 s, 7/8 (pierde el último compás), **87 %** |
| Foto 1 de Benjamin recortada (16 compases) | 295 s, 19 compases, con errores | 13 s, 13 compases en 3 partes; compases mezclados |
| Foto 2 de Benjamin recortada (16 compases) | 301 s, 16 compases, con errores | 12 s, 8 compases en 3 partes y 6 sistemas (son 4) |
| Fotos recortadas escaladas ×1,5 (interlínea ~20 px) | — | 20–21 s; igual que arriba |
| Ídem binarizadas (Otsu) | — | 19–22 s; foto 1: 14 compases y 5 sistemas bien; foto 2 igual de mal |
| Fotos originales sin recortar | ~300–312 s, 21 compases cada una, con errores | rechazadas por resolución |

En las fotos reales Audiveris reconoce bien muchas alturas (por ejemplo los compases 1 a 3 de la mano derecha de la
foto 2), pero no encuentra las barras de compás ni arma bien la llave del piano: separa los pentagramas en partes
distintas y junta varios compases en uno. Con imágenes limpias (lo que da un PDF) es mucho mejor y ~25 veces más rápido
que oemer. Conclusión de E1-19: no reemplaza a oemer para fotos; para PDF sí convendría. Lo decide Benjamin.

## Cambiar de motor

Crear otra clase con `name` y `recognize(...)` en `app/omr/` y cambiarla en `main.py`. Candidatos: homr (mejor en algunos casos, se instala desde git) y Audiveris (Java 17+, el más maduro).

## Reglas

- Mensajes de error en español, pensados para el usuario final.
- Nunca guardar en disco lo que sube el usuario más allá del trabajo: la carpeta temporal se borra al terminar.
- Las pruebas no corren el OMR real ni usan partituras con copyright: las de la API solo tocan rutas que no llaman al motor, y las de la Etapa 1 deben usar un motor falso.

## Pruebas

| Archivo | Qué prueba |
| --- | --- |
| `tests/helpers.py` | Genera PDF, PNG, JPEG, WEBP y MusicXML mínimos dentro de la prueba. `png_head`/`webp_head` arman solo el encabezado con el tamaño que se pida y `make_big_pdf` una página vacía enorme, para probar los topes sin archivos gigantes |
| `tests/test_pages.py` | PDF de 1 y de varias páginas, límite de 10, PDF roto, truncado y con contraseña, detección por bytes, página enorme a menos ppp, tamaño leído del encabezado y tope de 60 MP |
| `tests/test_jobs_api.py` | API completa con un motor falso puesto en `app.state.jobs`: estados, mensaje de espera, sufijo, 415/413/400/503/404/409, imagen gigante, errores en español. Que una foto pasa por el preprocesado (y el motor recibe la enderezada), que un PDF no, que si el preprocesado falla sigue con la original, y el mensaje "Enderezando la foto" |
| `tests/test_oemer_engine.py` | `OemerEngine` con el proceso reemplazado por uno falso: arma el comando del runner (Python del venv, `cwd` y `PYTHONPATH` en `backend/`), lee el `.musicxml`, error de oemer y sin salida (mensaje en español, detalle al log), aviso de parche no aplicado, tiempo agotado, oemer no instalado |
| `tests/test_oemer_runner.py` | El parche de `has_key` sobre un módulo falso (sin importar oemer): lista vacía da `False`, sigue detectando armaduras, y si oemer cambió no se aplica y se avisa |
| `tests/test_preprocess.py` | Preprocesado con fotos sintéticas (hoja con pentagramas en perspectiva sobre fondo oscuro, sombra): encuentra las esquinas, recorta sin fondo, conserva las 15 líneas, saca la sombra, y devuelve la original si no hay hoja o es un escaneo |
| `tests/test_merge.py` | Unir dos páginas de piano (2 pentagramas), el caso de distinta cantidad de pentagramas, que una página "tipo oemer" (compases que no cierran) no se reacomode, renumerar con una sola página y sacar título/compositor inventados |
