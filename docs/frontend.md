# Frontend

React 19 + Vite + TypeScript en `frontend/`. Sin framework de estilos: CSS propio en `src/index.css` con variables y modo oscuro.

## Comandos

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # chequea tipos y arma dist/
npm run lint     # oxlint
```

## Organización

- `src/App.tsx`: pantalla principal.
- `src/lib/api.ts`: cliente del backend (`readScore` sube y espera el resultado).
- `public/samples/`: partituras de ejemplo **de dominio público** para probar sin backend.
- `vite.config.ts`: proxy `/api` y configuración de la PWA.

## OpenSheetMusicDisplay (OSMD)

- `new OpenSheetMusicDisplay(div, { autoResize: true, backend: 'svg', followCursor: true })`, `await osmd.load(xml)`, `osmd.render()`.
- El cursor (`osmd.cursor`) recorre la partitura: `reset()`, `next()`, `show()`, `hide()`, `Iterator.EndReached`.
- Con `StrictMode` el efecto se monta dos veces: limpiar el contenedor al desmontar.

## PWA

- `vite-plugin-pwa` con `registerType: 'autoUpdate'`. Las rutas `/api` no se cachean.
- OSMD pesa más de 2 MB: `maximumFileSizeToCacheInBytes` está en 5 MB.
- Pendiente (E1-09): íconos PNG 192/512 y caché de los samples de piano.

## Reglas

- Textos en español rioplatense.
- Tiene que andar en el celular (ancho de 360 px) y en la compu.
- Mensajes de error que digan qué pasó y qué hacer.
