# Arquitectura

```
Navegador (PWA, React)                         Backend (FastAPI, Python)
┌────────────────────────────┐   POST /api/jobs   ┌──────────────────────────────┐
│ Subida PDF / foto          │ ─────────────────▶ │ pages.py  PDF → PNG (300 ppp) │
│                            │   GET /api/jobs/id │ omr/      Audiveris → oemer   │
│ OSMD dibuja el MusicXML    │ ◀───────────────── │ merge.py  une páginas (music21)│
│ Tone.js lo toca            │   GET …/musicxml   │ jobs.py   cola en segundo plano│
└────────────────────────────┘                    └──────────────────────────────┘
```

El formato central es **MusicXML**. El backend solo convierte la entrada en MusicXML. El MusicXML que devuelve no trae título (el OMR no lo lee); el frontend muestra el nombre del archivo. Ver, tocar, teclado, práctica y demás pasa en el navegador.

## Contrato de la API

Todas las rutas empiezan con `/api`. Los errores vienen como `{"detail": "<mensaje en español>"}`.

| Método y ruta | Qué hace | Respuesta |
| --- | --- | --- |
| `GET /api/health` | Comprueba que el backend está vivo y qué lector usa | `{"ok": true, "engine": "audiveris+oemer"}` (Audiveris con oemer de respaldo), o `"oemer"` si Audiveris no está instalado |
| `POST /api/jobs` | Sube un archivo (`multipart`, campo `file`). PDF, PNG, JPG o WEBP, hasta 20 MB y 10 páginas | `202` con el trabajo |
| `GET /api/jobs/{id}` | Estado del trabajo | el trabajo |
| `GET /api/jobs/{id}/musicxml` | Resultado | MusicXML (`409` si no está listo) |

Trabajo (recién creado viene con `status: "queued"` y `message: "En la fila, esperando turno…"`):

```json
{
  "id": "…", "filename": "vals.pdf",
  "status": "queued | running | done | error",
  "message": "Leyendo página 2 de 3",
  "page": 2, "pages": 3,
  "warnings": [], "error": null, "has_result": false
}
```

Errores:

| Código | Cuándo |
| --- | --- |
| `415` | Formato no soportado, o los primeros bytes no son de un PDF/PNG/JPG/WEBP (o no coinciden con el tipo declarado) |
| `413` | Archivo de más de 20 MB. La subida se corta apenas pasa el límite, sin leerla entera |
| `400` | Archivo vacío, o falta el campo `file` |
| `503` | Cola llena: ya hay 5 trabajos esperando o leyéndose. Reintentar en unos minutos |
| `404` | Trabajo inexistente o vencido (se borran a la hora) |
| `409` | `GET …/musicxml` cuando el trabajo todavía no terminó o terminó con error |

`warnings` trae avisos para el usuario: por ejemplo, si una página se salteó o si la lectura rápida (Audiveris) no funcionó y se usó el lector lento (oemer): "La lectura rápida no funcionó con esta foto; se leyó con el lector lento.". Mientras lee con el lector lento, `message` dice "La lectura rápida no funcionó con esta foto; usé el lector lento, puede tardar unos minutos".

Los errores al leer (PDF dañado o con contraseña, más de 10 páginas, imagen de más de 60 megapíxeles o con encabezado ilegible, el motor no pudo leer) no son códigos HTTP: el trabajo queda en `status: "error"` con el mensaje en `error`. Los mensajes siempre son en español; el detalle técnico queda solo en el log del backend.

## Desarrollo

- Frontend en :5173, backend en :8000. Vite redirige `/api` al backend.
- En producción, `VITE_API_URL` apunta al backend y `ALLOWED_ORIGINS` (backend) lista los dominios del frontend.
- El hosting de producción no está definido.
