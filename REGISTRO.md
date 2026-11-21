# REGISTRO

Una entrada por tarea terminada, **la más nueva arriba de todo**. Formato:

```
### E1-03 — <título>  (AAAA-MM-DD)
- Qué se hizo.
- Archivos tocados.
- Pendiente para la próxima tarea (si hay).
```

## Cierres de etapa

| Etapa | Fecha | Pruebas | Auditoría | Correcciones | PR |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-20 | OK: pytest 140/140, lint, build, humo, manual a 360/390/1280 px claro y oscuro; lectura real con IA 16/16 compases | Aprobada: 0 bloqueantes; 1 de seguridad a corregir (lectura de archivos de la IA) | E1-14 a E1-16, E1-26, E1-27 | Sin PR: fusión local en `main` |
| 0 | 2026-11-20 | OK (pytest 3/3, lint, build, humo, 360 px) | Aprobada: 0 bloqueantes, 2 a corregir | E0-09, E0-10 | Sin PR: fusión local en `main` |

---

### E1-26 y E1-27 — Correcciones de la auditoría final  (2026-11-20)
- E1-26: el CLI de Claude corre con `--restricted`, `--tools Read`, `--add-dir` y `dontAsk`, sin regla allow amplia. Verificado: lee el archivo de la carpeta del trabajo y rechaza uno de afuera. Rechaza CLI `.cmd`/`.bat`. Pedido endurecido: el texto de la imagen son datos, no instrucciones; título recortado a 120 caracteres.
- E1-27: `DELETE /api/jobs/{id}` (en cola: se saca; leyendo: se mata el proceso y sus hijos; terminado: 200 sin cambios). El frontend lo manda al tocar Cancelar.
- pytest 140/140, lint y build OK.

### E1-24 y E1-25 — Pruebas y auditoría finales de la Etapa 1  (2026-11-20)
- Pruebas: pytest 127/127, lint, build, npm audit sin altas; manual a 360, 390 y 1280 px, claro y oscuro (reproducir, pausa, velocidad, zoom, volver); caminos de error en español.
- Auditoría: aprobada. A corregir: lectura de archivos de la IA sin acotar (→ E1-26). Sugerencias: rechazar CLI `.cmd` (→ E1-26), Cancelar real (→ E1-27), texto de tiempo y docs (corregidos).

### E1-23 — Lector con IA (Claude Code CLI, solo desarrollo)  (2026-11-20)
- `ClaudeEngine` + `claude_score.py`: Claude lee la foto y devuelve un JSON compacto (compases, pentagramas, voces, tresillos) que music21 pasa a MusicXML. Motor `claude+audiveris+oemer` con `OMR_USE_CLAUDE=1`.
- Prueba real con la foto de la pieza 26: 16/16 compases en 62 s (directo) y 112 s por la API. En los 6 primeros: mano izquierda 5/6 exactos; mano derecha con el ritmo de tresillos bien, 1 nota mal y sin la voz del bajo sostenido (se ajustó el pedido).
- Usa la cuenta de Claude de Benjamin; para publicar hay que pasar a la API. El CLI se lanza sin las variables CLAUDE*/ANTHROPIC* que hereda de la app de escritorio.
- pytest 127/127.

### E1-22 — Diseño para celular  (2026-11-20)
- Inicio con "Sacar una foto" grande abajo; lectura con progreso simple; partitura con encabezado fijo, zoom automático al ancho y lupas; reproductor fijo abajo con Reproducir/Pausa, Detener y Velocidad; créditos del piano abajo de la partitura; diagnóstico `[dev]` plegado.
- Probado con capturas a 360, 375, 390 y 1280 px, claro y oscuro. Lint y build OK.

### E1-21 — Sonido en el celular  (2026-11-20)
- `frontend/src/lib/audioUnlock.ts`: en iPhone/iPad, sesión de audio en "playback" y audio de silencio en el primer toque. `Player.tsx` arranca el audio dentro del toque, avisa si no se activa y retoma si iOS lo interrumpe. Línea `[dev]` de diagnóstico solo en desarrollo.
- Probado en Chromium simulando iPhone; falta el iPhone real.
- Además: la foto ya no se achica antes de leer (Audiveris confundía los pentagramas del piano con dos instrumentos).

### E1-20 — Audiveris como lector principal  (2026-11-20)
- `AudiverisEngine` (gris, luz normalizada, binarizado, ancho mínimo 2500 px; une los movimientos) y `FallbackEngine` (si Audiveris falla, oemer, con aviso al usuario). Motor por defecto: `audiveris+oemer`; sin Audiveris instalado, solo oemer.
- Real por la API: Oda limpia 11 s, 8/8 compases y notas correctas; foto de Benjamin en resolución completa 34 s, 15 de 16 compases. Antes ~5 min cada una.
- pytest 99/99. Falta probar el respaldo real y la precisión nota por nota de la foto.
- Una foto de WhatsApp (baja resolución) no le sirve a Audiveris: cae a oemer.

### E1-19 (parte) — Audiveris comparado  (2026-11-20)
- Audiveris 5.11.0 (AGPL-3.0, trae su Java) en `%LOCALAPPDATA%\partituras-tools\audiveris\`, sin instalar nada en el sistema.
- ~10 s por página contra ~5 min de oemer. Oda limpia 100 % (oemer 54 %), Oda tipo foto 87 % (oemer 77 %). Con las fotos de WhatsApp de Benjamin desarma la partitura (resolución baja: interlínea 7–8 px).
- Propuesta a Benjamin: Audiveris principal y oemer de respaldo; falta probar con una foto en resolución completa. Detalle en `docs/omr.md`.

### E1-18 y parte de E1-19 — Fotos: recorte y error de oemer  (2026-11-20)
- `backend/app/preprocess.py`: detecta la hoja, corrige perspectiva, saca fondo y sombra. Conectado en `jobs.py` solo para fotos ("Enderezando la foto").
- Causa del error: bug de oemer en `Measure.has_key` (lista vacía). Parche en memoria en `backend/app/omr/oemer_runner.py`, sin tocar site-packages.
- Con las 2 fotos de Benjamin: sin recorte, oemer se caía; recortadas, leen (16 compases reales → 19 y 16 leídos). Tiempo igual: ~5 min por página. Lectura real por la API OK en 297 s.
- Siguen saliendo errores: los bordes de una cinta de color se leen como barras de compás, y quedan restos del anillado.
- pytest 73/73.
- E1-17 (placa de video) cancelada por pedido de Benjamin.

### E1-14 a E1-16 — Correcciones de la auditoría  (2026-11-20)
- E1-14: se borran título y compositor inventados por oemer y music21; `ScoreView` carga con título vacío para usar el nombre del archivo.
- E1-15: PDF con lado mayor tope de 5000 px (una A4 no cambia); imágenes de más de 60 megapíxeles se rechazan leyendo solo el encabezado.
- E1-16: compases renumerados siempre; mensaje inicial "En la fila, esperando turno…".
- pytest 56/56, lint y build OK.
- Verificado con una lectura real por la API (backend reiniciado): el MusicXML sale sin título ni compositor inventados y con compases 1 a 8. Nota: `--reload` no tomó los cambios; hay que reiniciar el backend a mano (anotado en README).

### E1-12 — Auditoría de la Etapa 1  (2026-11-20)
- Aprobada con observaciones, sin bloqueantes. A corregir: título "Upload"/"Transcribed by Oemer" (→ E1-14) y sin tope de píxeles (→ E1-15). Sugerencias: renumerar con una página y mensaje de cola (→ E1-16); cancelar no frena el trabajo en el backend (queda para más adelante: `DELETE /api/jobs/{id}`).
- Revisado y bien: corte de subida, concurrencia y limpieza de trabajos, liberación del reproductor, caché de la PWA, sin contenido con copyright, docs al día.

### E1-11 — Pruebas de la Etapa 1  (2026-11-20)
- pytest 43/43, lint y build OK, npm audit sin altas. Ejemplo: se dibuja, suena, pausa, sigue, detiene. 360 px oscuro OK.
- Errores de subida en español (400, 413, 415, 404); CORS cerrado a orígenes ajenos.
- Lectura real de la imagen generada: 308 s, OSMD la dibuja y se toca. Unión de 3 páginas: se dibuja y se toca entera.
- Falta la prueba con partituras reales de Benjamin (E1-01, E1-10).

### E1-03 — oemer funcionando  (2026-11-20)
- Probado con la Oda a la alegría rasterizada (limpia y "tipo foto") y un PDF de 2 páginas por la API. Sin muestras reales todavía.
- Modelos: 218 MB, se bajan la primera vez (~20 s) dentro del paquete en el venv.
- Tiempo: ~5 min por página en CPU; PDF de 2 páginas ~10 min.
- Precisión: 54 % (limpia), 77 % (tipo foto), 65 % el PDF unido. Falla sobre todo con redondas en clave de fa.
- Fijados `onnxruntime`/`onnxruntime-gpu` 1.27.0 (1.28+ rechaza el modelo) y `opencv-python-headless` 4.x (OpenCV 5 rompe oemer).
- Arreglo en `merge.py`: music21 reacomodaba compases incompletos (salían 17 en vez de 16). 43 pruebas OK.
- Pendientes: 5 min por página es mucho (la GPU no se usa, falta CUDA); descarga de modelos cortada deja oemer roto.

### E1-09 — PWA  (2026-11-20)
- Íconos PNG 192, 512, maskable 512 y apple-touch-icon 180 en `frontend/public/`. Precaché de 14 entradas (incluye OSMD, Tone y el ejemplo). Samples del piano con CacheFirst en la caché `piano-samples`.
- Probado con build + preview en Chromium: instalable sin errores, y sin conexión abre, dibuja y toca el ejemplo (si antes se tocó con conexión).
- Pendiente: probar la instalación en un celular real.

### E1-08 — Tocar la partitura  (2026-11-20)
- `frontend/src/components/Player.tsx` y `src/lib/playback.ts`: Reproducir/Seguir, Pausa, Detener, velocidad 50–150 % (se puede cambiar mientras suena), cursor sincronizado con `Tone.getDraw`, créditos de Salamander visibles.
- Tone se carga aparte, al entrar a la partitura. Se evitó un doble disparo intermitente de Tone 15.
- Probado sin ventana: 30 pasos correctos del ejemplo, tempo, pausa, detener, cambio de ancho, error de carga, 360 px. El sonido falta confirmarlo de oído.
- Pendientes: al pausar el cursor puede avanzar un paso; sin cambios de tempo en el medio ni dinámicas.

### E1-05 — Unir páginas  (2026-11-20)
- `merge.py`: error si no hay páginas; aviso si una página sale con otra cantidad de pentagramas (se saltea). Pruebas con MusicXML generado.
- Pendientes: las ligaduras entre páginas se pierden; decidir si saltear la página es lo que queremos.

### E1-04 — Trabajos en segundo plano y API  (2026-11-20)
- Sufijo temporal según el formato real, cola de 5 (503), corte de subida a 20 MB por middleware (`upload_limit.py`), 400 en español si falta el archivo, errores técnicos solo al log (también los de oemer).
- `api.ts`: si el backend manda un mensaje (por ejemplo 503 cola llena) se muestra ese; 502/503/504 sin mensaje = sin conexión.
- Pruebas con motor falso: camino completo y todos los códigos de error.

### E1-02 — PDF o imagen a páginas  (2026-11-20)
- `pages.py` revisa los primeros bytes (PDF, PNG, JPEG, WEBP), rechaza PDF con contraseña y páginas que no se pueden convertir.
- Pruebas con PDF de 1, 3, 10 y 11 páginas, roto, truncado y con contraseña. `pytest`: 37/37.

### E1-07 — Partitura en pantalla  (2026-11-20)
- `frontend/src/components/ScoreView.tsx`: OSMD con autoResize, título y compositor en HTML, fondo blanco también en modo oscuro, carga diferida de OSMD. Expone la instancia con `onOsmdChange`.
- Probado a 360 px y 1200 px, claro y oscuro; sin SVG duplicados con StrictMode.
- Pendiente para E1-08: confirmar el cursor tras redibujar por cambio de ancho.

### E1-06 — Pantalla de subida  (2026-11-20)
- `frontend/src/App.tsx`: elegir PDF o imagen, sacar foto, abrir MusicXML directo, ejemplo, progreso con cancelar, errores y avisos del backend. `api.ts` pasa la señal de cancelación a `fetch`.
- Pendientes: cancelar no frena el trabajo en el backend (no hay ruta); `.mxl` comprimido no soportado; el estado del backend se consulta una sola vez.

### E0-07 — Benjamin confirma que anda  (2026-11-20)
- En su navegador, http://localhost:5173 muestra "Servidor de lectura conectado". Etapa 0 cerrada.

### E0-10 — Correcciones de documentación  (2026-11-20)
- `README.md`: Node 20.19+ o 22.12+. `docs/omr.md`: aclarado qué prueban las pruebas de la API.

### E0-09 — Sin conexión con el backend  (2026-11-20)
- `frontend/src/lib/api.ts`: 502/503/504 se muestran como "No me pude conectar con el servidor de lectura".
- Lint, build, pytest y prueba de humo vuelven a pasar.

### E0-06 — Auditoría de la Etapa 0  (2026-11-20)
- Hecha por el revisor sobre todo el repo. Aprobada, sin bloqueantes.
- A corregir: mensaje con el backend apagado (→ E0-09) y PyMuPDF con licencia AGPL (→ decisión E1-13).
- Sugerencias: versión de Node y nota de pruebas (→ E0-10); `package.json` con rangos `^` (las versiones quedan fijas en `package-lock.json`).
- `npm audit`: 4 moderadas en workbox-build (solo al compilar, no llegan al navegador). El arreglo automático baja vite-plugin-pwa de versión; no se aplica.
- Licencias OK para publicar: fastapi, oemer y tone MIT; uvicorn, music21 y OSMD BSD-3; python-multipart Apache-2.0. Samples Salamander CC-BY 3.0 (mostrar créditos).
- Hallazgos del borrador de la Etapa 1, sumados a E1-04.

### E0-05 — Pruebas de la Etapa 0  (2026-11-20)
- `pytest`: 3/3. `npm run lint` y `npm run build`: OK.
- Humo: `/api/health` responde por el proxy, la página muestra "Servidor de lectura conectado", sin errores de consola, sin barra horizontal a 360 px. CORS rechaza dominios ajenos.

### E0-04 — Conectar frontend y backend  (2026-11-20)
- Proxy `/api` → `http://127.0.0.1:8000` en `frontend/vite.config.ts`.
- Pantalla de estado en `frontend/src/App.tsx` que llama a `/api/health`.
- Cliente de la API en `frontend/src/lib/api.ts` (incluye ya las llamadas de la Etapa 1).

### E0-03 — Esqueleto del backend  (2026-11-20)
- FastAPI en `backend/app/main.py`, dependencias en `backend/requirements.txt` y `requirements-dev.txt`.
- Interfaz `OmrEngine` y motor oemer en `backend/app/omr/`.
- Borrador de la Etapa 1 (páginas, trabajos, unir páginas), sin probar con partituras reales.

### E0-02 — Esqueleto del frontend  (2026-11-20)
- React 19 + Vite 8 + TypeScript, con `opensheetmusicdisplay`, `tone` y `vite-plugin-pwa`.
- Partitura de ejemplo de dominio público en `frontend/public/samples/oda-a-la-alegria.musicxml` (Beethoven, arreglo simple).

### E0-01 — Base del repo  (2026-11-20)
- `CLAUDE.md`, `TAREAS.md`, `REGISTRO.md`, `README.md`, `docs/`, `.claude/agents/`, `.gitignore`.
- Decisiones: React + Vite en vez de Next.js; oemer como primer motor OMR.
