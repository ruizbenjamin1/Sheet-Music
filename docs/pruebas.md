# Pruebas y auditoría

Cada etapa se cierra con **pruebas** y **auditoría**. Las dos las hace el subagente `revisor`.

## 1. Pruebas automáticas (siempre)

```powershell
cd backend;  .\.venv\Scripts\python -m pytest -q
cd frontend; npm run lint; npm run build
```

Todas tienen que pasar. Una prueba que falla no se borra ni se saltea: se arregla el código o se crea una tarea de corrección.

## 2. Prueba de humo (siempre)

1. Levantar backend (`uvicorn app.main:app --port 8000`) y frontend (`npm run dev`).
2. `GET http://localhost:5173/api/health` devuelve `{"ok": true, ...}`.
3. Abrir http://localhost:5173 y revisar que no haya errores en la consola del navegador.

## 3. Prueba manual de la etapa

La define la última tarea de pruebas de cada etapa. Para la Etapa 1: subir cada partitura de `muestras/`, esperar la lectura, ver la partitura y tocarla de principio a fin; y lo mismo con el ejemplo incluido.

## 4. Auditoría (lista)

Revisar **todo lo que cambió en la etapa** (`git diff main...HEAD`):

- **Errores:** casos borde, valores vacíos, archivos rotos, carreras entre pedidos.
- **Seguridad:** validar tamaño y tipo de lo que sube el usuario; nada de rutas armadas con datos del usuario; nada de secretos en el código; CORS solo para los dominios propios.
- **Manejo de errores:** todo error que ve el usuario está en español y dice qué hacer.
- **Dependencias:** versiones fijadas; licencias compatibles con publicar la app (anotar cualquier GPL/AGPL); `npm audit` sin vulnerabilidades altas.
- **Contenido:** nada con copyright en el repo (partituras, samples, imágenes).
- **Código muerto o duplicado**, nombres claros, comentarios útiles.
- **Coherencia con `docs/`:** si el código cambió algo documentado, actualizar el doc.
- **Celular:** la pantalla se usa bien a 360 px de ancho.

## Resultado

El `revisor` devuelve: qué pruebas pasaron, qué falló, y una lista de hallazgos con gravedad (bloqueante / a corregir / sugerencia). Los bloqueantes y "a corregir" se vuelven tareas de corrección de la misma etapa.
