# Arquitectura

```
Navegador (PWA, React)                         Backend (FastAPI, Python)
┌────────────────────────────┐   POST /api/jobs   ┌──────────────────────────────┐
│ Subida PDF / foto          │ ─────────────────▶ │ pages.py  PDF → PNG (300 ppp) │
│                            │   GET /api/jobs/id │ omr/      motor OMR por página│
│ OSMD dibuja el MusicXML    │ ◀───────────────── │ merge.py  une páginas (music21)│
│ Tone.js lo toca            │   GET …/musicxml   │ jobs.py   cola en segundo plano│
└────────────────────────────┘                    └──────────────────────────────┘
```

El formato central es **MusicXML**. El backend solo convierte la entrada en MusicXML. Ver, tocar, teclado, práctica y demás pasa en el navegador.

## Contrato de la API

Todas las rutas empiezan con `/api`. Los errores vienen como `{"detail": "<mensaje en español>"}`.

| Método y ruta | Qué hace | Respuesta |
| --- | --- | --- |
| `GET /api/health` | Comprueba que el backend está vivo | `{"ok": true, "engine": "oemer"}` |
| `POST /api/jobs` | Sube un archivo (`multipart`, campo `file`). PDF, PNG, JPG o WEBP, hasta 20 MB y 10 páginas | `202` con el trabajo |
| `GET /api/jobs/{id}` | Estado del trabajo | el trabajo |
| `GET /api/jobs/{id}/musicxml` | Resultado | MusicXML (`409` si no está listo) |

Trabajo:

```json
{
  "id": "…", "filename": "vals.pdf",
  "status": "queued | running | done | error",
  "message": "Leyendo página 2 de 3",
  "page": 2, "pages": 3,
  "warnings": [], "error": null, "has_result": false
}
```

Errores: `415` formato no soportado, `413` archivo grande, `400` archivo vacío, `404` trabajo inexistente o vencido (se borran a la hora).

## Desarrollo

- Frontend en :5173, backend en :8000. Vite redirige `/api` al backend.
- En producción, `VITE_API_URL` apunta al backend y `ALLOWED_ORIGINS` (backend) lista los dominios del frontend.
- El hosting de producción no está definido.
