# TAREAS

Tareas por etapa. Una etapa por vez, en orden. Forma de trabajo y etiquetas: ver `CLAUDE.md`.

Toda etapa termina con dos tareas `[test]`: **pruebas** y **auditoría** (ver `docs/pruebas.md`). Sin las dos aprobadas, la etapa no se cierra.

## Progreso

| Etapa | Nombre | Tareas | Hechas | Estado |
| --- | --- | --- | --- | --- |
| 0 | Base del proyecto | 10 | 10 | Cerrada |
| 1 | MVP: subir, leer, ver y tocar | 16 | 13 | Falta la prueba de Benjamin |
| 2 | Aprender | — | — | Pendiente |
| 3 | Corregir | — | — | Pendiente |
| 4 | Practicar (MIDI) | — | — | Pendiente |
| 5 | Entender (IA) | — | — | Pendiente |
| 6 | Descubrir (catálogo) | — | — | Pendiente |
| 7 | Simplificar | — | — | Pendiente |
| 8 | Manuscritas | — | — | Pendiente |
| 9 | Escalar | — | — | Pendiente |

Las etapas 2 a 9 se detallan en tareas cuando se abre cada una.

---

## Etapa 0 — Base del proyecto

Objetivo: el repo tiene la forma de trabajo armada y el frontend y el backend arrancan y se hablan en la compu de Benjamin.

- [x] **E0-01** `[coord]` Base del repo: `CLAUDE.md`, `TAREAS.md`, `REGISTRO.md`, `docs/`, `.claude/agents/`, `README.md`, `.gitignore`.
- [x] **E0-02** `[ui]` Esqueleto del frontend: React + Vite + TypeScript, OSMD y Tone.js instalados, PWA configurada (manifest, service worker).
- [x] **E0-03** `[omr]` Esqueleto del backend: FastAPI, entorno virtual en `backend/.venv`, oemer y music21 instalados, `GET /api/health`.
- [x] **E0-04** `[ui]` Conectar frontend y backend: proxy `/api` en Vite y pantalla de estado que muestra si el backend responde.
- [x] **E0-05** `[test]` Pruebas: `pytest` del backend, `npm run build` y `npm run lint` del frontend, y prueba de humo con los dos servidores levantados.
- [x] **E0-06** `[test]` Auditoría de la etapa: revisar todo el código y la configuración nuevos según `docs/pruebas.md`.
- [x] **E0-09** `[ui]` Corrección de auditoría: con el backend apagado, el proxy responde 502 y la app mostraba "El servidor respondió 502." en vez de avisar que no hay conexión.
- [x] **E0-10** `[coord]` Corrección de auditoría: versión de Node en `README.md` (Vite 8 pide 20.19+ o 22.12+) y nota sobre pruebas en `docs/omr.md`.
- [x] **E0-07** `[yo]` Benjamin levanta los dos servidores con los pasos del `README.md` y confirma que en http://localhost:5173 ve "Servidor de lectura conectado".
- [x] **E0-08** `[yo]` Benjamin aprobó la Etapa 0: se fusionó en `main` local y él hace el push (sin PR, porque el repo no tenía `main`).

## Etapa 1 — MVP: subir, leer, ver y tocar

Objetivo: subir un PDF o una foto de una partitura impresa, que se lea a MusicXML, se vea en pantalla y suene con piano.

Nota: en el backend ya hay un borrador de E1-02 a E1-05 (`backend/app/pages.py`, `omr/`, `jobs.py`, `merge.py`, `main.py`), escrito al armar la base y **sin probar con partituras reales**. Las tareas parten de ese borrador.

- [ ] **E1-01** `[yo]` Benjamin junta 3 o 4 partituras impresas propias para probar (al menos un PDF de varias páginas y una foto de celular) y las pone en `muestras/`. No se suben a git.
- [x] **E1-02** `[omr]` PDF o imagen a páginas (`pages.py`): pruebas con un PDF de 1 y de varias páginas, límite de páginas y archivos rotos.
- [x] **E1-03** `[omr]` Motor oemer detrás de `OmrEngine`: correrlo con una muestra, confirmar la descarga de modelos la primera vez y medir cuánto tarda por página. Revisar que no choquen `onnxruntime` y `onnxruntime-gpu`.
- [x] **E1-04** `[omr]` Trabajos en segundo plano y API (`POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/musicxml`): pruebas con un motor falso, errores claros en español. Incluye lo que encontró la auditoría de la Etapa 0: sufijo del archivo temporal fijo según el tipo (no el nombre que manda el usuario), revisar los primeros bytes para confirmar PDF o imagen, no mostrar errores técnicos en inglés, límite de trabajos en cola, cortar la subida al pasar los 20 MB, y pasar la señal de cancelación a `fetch` en `api.ts`.
- [x] **E1-05** `[omr]` Unir páginas en una sola partitura (`merge.py`): pruebas con dos páginas de ejemplo.
- [x] **E1-06** `[ui]` Pantalla de subida: elegir PDF o imagen, sacar foto con el celular, abrir un MusicXML directo, botón "Probar con un ejemplo" (`public/samples/oda-a-la-alegria.musicxml`), barra de progreso con el mensaje del backend.
- [x] **E1-07** `[ui]` Mostrar la partitura con OSMD, que se adapte al ancho de pantalla.
- [x] **E1-08** `[audio]` Tocar la partitura: Tone.js con samples de piano, cursor de OSMD sincronizado, botones reproducir / pausa / detener y control de velocidad.
- [x] **E1-09** `[ui]` PWA: íconos PNG 192 y 512, caché de los samples para usar sin conexión, comprobar que se puede instalar.
- [x] **E1-14** `[omr]` Corrección de auditoría: el título que se ve es "Upload" o "Page_01" y el compositor "Transcribed by Oemer"; sacar esos datos que inventa oemer para que la app use el nombre del archivo.
- [x] **E1-15** `[omr]` Corrección de auditoría: poner un tope de píxeles a las páginas de PDF y a las imágenes (una página enorme puede ocupar GB de memoria).
- [x] **E1-16** `[omr]` Corrección de auditoría: renumerar compases también con una sola página, y que el mensaje de cola sea "En la fila, esperando turno…".
- [ ] **E1-13** `[yo]` Benjamin decide qué hacer con PyMuPDF, que tiene licencia AGPL: si la app se publica como servicio, obliga a compartir el código del backend. Opciones: publicar el código, o cambiarlo por pypdfium2 (Apache/BSD). Se puede decidir hasta antes de publicar.
- [ ] **E1-10** `[test]` Medir la precisión de oemer con las muestras de E1-01 (notas bien leídas sobre el total, a ojo por compás). Si es mala, proponer probar homr.
- [x] **E1-11** `[test]` Pruebas de la etapa (automáticas + prueba manual completa: subir, leer, ver, tocar).
- [x] **E1-12** `[test]` Auditoría de la etapa.

## Etapa 2 — Aprender
Teclado animado con un color por mano, nombres de notas, manos separadas, tempo ajustable.

## Etapa 3 — Corregir
Editor para arreglar notas mal leídas tocando sobre la partitura.

## Etapa 4 — Practicar (MIDI)
Modo práctica con el teclado por Web MIDI: la app espera la nota correcta, marca errores y mide el tempo. El Casio CT-670 necesita un adaptador USB-MIDI (DIN de 5 pines). Se puede adelantar si Benjamin consigue el adaptador.

## Etapa 5 — Entender (IA)
Explicación con IA a partir del MusicXML y digitación sugerida (pianoplayer). Falta definir qué LLM y presupuesto.

## Etapa 6 — Descubrir (catálogo)
Buscador con catálogo libre (IMSLP, PDMX, Mutopia) y filtro por dificultad calculada. Revisar la licencia exacta de cada fuente.

## Etapa 7 — Simplificar
Versión fácil de cualquier pieza con music21.

## Etapa 8 — Manuscritas
Lectura de partituras escritas a mano con un LLM con visión.

## Etapa 9 — Escalar
Cuentas de usuario y progreso guardado (Supabase); después, otros instrumentos.
