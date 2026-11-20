# CLAUDE.md — App de partituras para piano

Este archivo manda. Leelo entero antes de hacer cualquier cosa en este repo.

## Qué es

Una web app instalable (PWA) que lee partituras de piano desde un PDF o una foto, las muestra, las toca con sonido de piano y, en etapas siguientes, enseña a tocarlas (teclado animado, modo práctica con MIDI, explicaciones con IA, catálogo libre).

Plan completo: [App de partituras para piano — Plan del proyecto](https://claude.ai/artifact/NmNWy2K3u4fz384zE1femb).

- Dueño del proyecto: Benjamin. Hablale en español rioplatense, con palabras simples.
- Se piensa publicar: **solo contenido con licencia libre** en el catálogo. Lo que sube cada usuario es privado.
- Su teclado: Casio CT-670. Tiene MIDI por DIN de 5 pines, no USB: para el modo práctica necesita un adaptador USB-MIDI.

## Stack (decidido)

| Capa | Tecnología | Por qué |
| --- | --- | --- |
| Front | React + Vite + TypeScript, PWA con `vite-plugin-pwa` | Todo corre en el navegador; no hace falta el servidor de Next.js |
| Partitura | OpenSheetMusicDisplay (OSMD) | Dibuja MusicXML |
| Sonido | Tone.js + samples Salamander Grand (CC-BY 3.0) | Piano realista en el navegador |
| Back | FastAPI (Python 3.12) | API de lectura |
| OMR | oemer (primero), detrás de la interfaz `OmrEngine` | Se instala con pip, sin Java. Se puede cambiar por homr o Audiveris |
| PDF → imagen | PyMuPDF | |
| Unir páginas / análisis | music21 | |

Sin definir todavía (no inventar, preguntar cuando haga falta): hosting del backend, qué LLM usar y su presupuesto, nombre de la app.

Idea para el hosting (2026-11-20, sin decidir): la lectura corre en el servidor, no en la compu del usuario. Benjamin prefiere una solución general en la nube; la opción más barata para empezar es GPU por segundo de uso (Modal, RunPod, Replicate), y se decide al llegar a publicar.

## Estructura

```
frontend/          React + Vite (npm run dev → http://localhost:5173)
backend/           FastAPI (uvicorn app.main:app → http://localhost:8000)
  app/omr/         motores OMR (interfaz común en base.py)
docs/              detalle técnico para cada área (lo leen los subagentes)
.claude/agents/    un subagente por área
TAREAS.md          tareas por etapa y tabla de Progreso
REGISTRO.md        registro de tareas terminadas y cierres de etapa
muestras/          partituras de prueba de Benjamin (NO se suben a git)
```

Cómo levantar todo: ver `README.md`.

## Reglas del proyecto

1. **Una etapa por vez**, en el orden de `TAREAS.md`. No se empieza una etapa hasta cerrar la anterior.
2. **Si algo no está definido, frenar y preguntar** a Benjamin en vez de inventar.
3. **Git:** nunca push a `main`. Cada etapa va en una rama y un PR. Nada destructivo sin preguntar.
4. **Derechos de autor:** nada de partituras con copyright en el repo ni en el catálogo. Las de prueba de Benjamin van en `muestras/`, que está en `.gitignore`.
5. **El formato central es MusicXML.** El backend convierte cualquier entrada a MusicXML; el resto se hace en el navegador.
6. Textos de la interfaz en español rioplatense.
7. Antes de dar algo por terminado, correr las pruebas de `docs/pruebas.md` que correspondan.

## Forma de trabajo

El **coordinador** (la sesión principal de Claude) **no programa**: organiza, delega y registra.

### Etiquetas y subagentes

| Etiqueta | Quién la hace | Archivo |
| --- | --- | --- |
| `[ui]` | subagente `ui` (frontend, pantallas, PWA) | `.claude/agents/ui.md` |
| `[omr]` | subagente `omr` (backend, lectura de partituras) | `.claude/agents/omr.md` |
| `[audio]` | subagente `audio` (reproducción, MIDI, sonido) | `.claude/agents/audio.md` |
| `[test]` | subagente `revisor` (pruebas y revisión) | `.claude/agents/revisor.md` |
| `[coord]` | el coordinador (docs, TAREAS, REGISTRO, git) | — |
| `[yo]` | **Benjamin**. Avisarle qué tiene que hacer y esperar que confirme | — |

### Cómo se hace una tarea

1. Tomar la primera tarea sin marcar de la etapa abierta en `TAREAS.md`.
2. Delegarla al subagente de su etiqueta. Pasarle **solo**: el ID y el texto de la tarea, los archivos o docs que necesita, y lo que quedó pendiente de la tarea anterior.
3. Si es `[yo]`: decirle a Benjamin exactamente qué hacer y esperar su confirmación.
4. Al terminar:
   - marcar `[x]` en `TAREAS.md` y actualizar la tabla de Progreso;
   - agregar una entrada **arriba de todo** en `REGISTRO.md`;
   - avisar con una línea: `✔ E1-03 <título> — <resultado>`.

### Cómo se cierra una etapa

Ninguna etapa se cierra sin **auditoría y pruebas**. Las dos son tareas `[test]` al final de cada etapa en `TAREAS.md`.

1. **Pruebas:** el `revisor` corre todas las pruebas de `docs/pruebas.md` (automáticas y la prueba manual de la etapa) y anota qué pasó y qué falló.
2. **Auditoría:** el `revisor` lee todo el código que cambió en la etapa con la lista de `docs/pruebas.md` (errores, seguridad, manejo de errores, dependencias y sus licencias, código muerto, coherencia con `docs/`).
3. Si encuentra errores, se crean tareas de corrección con los IDs siguientes (por ejemplo E1-14, E1-15), se hacen, y se vuelven a correr las pruebas.
4. Anotar el cierre en la tabla "Cierres de etapa" de `REGISTRO.md`, con el resultado de pruebas y auditoría.
5. Commit, push de la rama y PR.
6. **Frenar** y mostrarle a Benjamin un resumen de 5 líneas. No seguir sin su OK.

## Prompts útiles

**Retomar en una sesión nueva:**

> Leé CLAUDE.md, la tabla de Progreso de TAREAS.md y las últimas 3 entradas de REGISTRO.md. Decime en qué etapa estamos, qué se hizo último y cuál es la próxima tarea. Después seguí con la forma de trabajo de CLAUDE.md.

**Informe final:**

> Leé TAREAS.md y REGISTRO.md completos y armá un informe: qué hace hoy la app, qué etapas están cerradas, qué quedó pendiente o con errores conocidos, y qué decisiones siguen abiertas.
