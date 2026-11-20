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
| 0 | 2026-11-20 | OK (pytest 3/3, lint, build, humo, 360 px) | Aprobada: 0 bloqueantes, 2 a corregir | E0-09, E0-10 | Sin PR: fusión local en `main` |

---

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
