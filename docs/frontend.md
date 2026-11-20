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

- `src/App.tsx`: la app. Tres pantallas en un estado `screen`: `home` (subir), `reading` (progreso) y `score` (partitura + lugar del reproductor). Si el backend no responde muestra un aviso, pero igual se puede abrir un MusicXML o el ejemplo.
- `src/components/ScoreView.tsx`: dibuja un MusicXML con OSMD y expone la instancia (ver abajo). Se carga con `React.lazy` para no bajar OSMD hasta que hace falta.
- `src/components/Player.tsx`: reproductor (reproducir / pausa / detener / velocidad) con el cursor de OSMD. Detalle en `docs/audio.md`.
- `src/lib/playback.ts`: saca las notas de la partitura con el cursor de OSMD y arma la lista de samples del piano.
- `src/lib/api.ts`: cliente del backend. `readScore(file, onProgress, signal)` sube, sondea cada 1,5 s y devuelve `{ musicxml, warnings }`. La señal se pasa a cada `fetch` y corta también la espera; al cancelar rechaza con un `DOMException` `AbortError` (el trabajo sigue en el backend hasta vencer).
- `public/samples/`: partituras de ejemplo **de dominio público** para probar sin backend.
- `vite.config.ts`: proxy `/api` y configuración de la PWA.

## OpenSheetMusicDisplay (OSMD)

- `new OpenSheetMusicDisplay(div, { autoResize: true, backend: 'svg', followCursor: true })`, `await osmd.load(xml)`, `osmd.render()`.
- El cursor (`osmd.cursor`) recorre la partitura: `reset()`, `next()`, `show()`, `hide()`, `Iterator.EndReached`.
- Con `StrictMode` el efecto se monta dos veces: limpiar el contenedor al desmontar (`dispose()`, `clear()`, vaciar el div).
- Título y compositor se muestran en HTML arriba de la partitura (`drawTitle`, `drawSubtitle` y `drawComposer` en `false`).
- La partitura se dibuja siempre sobre fondo blanco (`.score-paper`), también en modo oscuro.

### ScoreView (para el reproductor)

```tsx
<ScoreView
  musicxml={string}                 // MusicXML sin comprimir
  fallbackTitle?={string}           // si la partitura no trae título
  onOsmdChange?={(osmd: OpenSheetMusicDisplay | null) => void}
  onError?={(mensaje: string) => void}
/>
```

`onOsmdChange` recibe la instancia ya cargada y dibujada, y `null` cuando se desmonta o cambia la partitura. `App.tsx` la guarda en el estado `osmd`; los controles de reproducción van en `<section className="player">`, arriba de la partitura.

## Subida

- PDF o imagen (PNG, JPG, WEBP), hasta 20 MB (se chequea antes de subir). "Sacar una foto" es un `<input type="file" accept="image/*" capture="environment">`.
- MusicXML (`.musicxml`, `.xml`) se lee con `file.text()` sin pasar por el backend; se valida que tenga `<score-partwise` o `<score-timewise`. `.mxl` comprimido todavía no.
- Los `warnings` del backend se muestran arriba de la partitura.

## PWA

- `vite-plugin-pwa` con `registerType: 'autoUpdate'` (`generateSW`). Las rutas `/api` no se cachean.
- **Íconos** (en `public/`, hechos a partir de `favicon.svg`, nota blanca sobre `#3b4cca`):
  - `pwa-192x192.png` y `pwa-512x512.png` (`purpose: any`, esquinas redondeadas como el SVG);
  - `maskable-512x512.png` (`purpose: maskable`): fondo lleno y la nota dentro del círculo seguro del 80 %;
  - `apple-touch-icon.png` (180 × 180, fondo lleno, sin transparencia), enlazado en `index.html`;
  - `favicon.svg` sigue como favicon y como ícono `any` del manifest.
  - Para regenerarlos se rasteriza el SVG con un Chromium sin ventana (por ejemplo Playwright) fuera del repo; no hay script ni dependencia en el proyecto.
- **Precaché** (`globPatterns: **/*.{js,css,html,musicxml}` + íconos y manifest que agrega el plugin): entran también los chunks de OSMD (`ScoreView-*.js`) y Tone (`esm-*.js`) que se cargan con import dinámico, y `samples/oda-a-la-alegria.musicxml`. Así la app abre y dibuja el ejemplo sin conexión.
- OSMD pesa más de 2 MB: `maximumFileSizeToCacheInBytes` está en 5 MB.
- **Samples del piano**: `runtimeCaching` `CacheFirst` para `https://tonejs.github.io/audio/salamander/*` en la caché `piano-samples` (respuestas con estado 0 y 200, hasta 60 archivos, 1 año). Se guardan al primer "Reproducir" con conexión; después suena también sin conexión.
- Sin conexión solo falla `/api` (el aviso de backend caído aparece como siempre).
- Prueba: `npm run build` + `npm run preview -- --port 4173`, y en Chromium: manifest con íconos, SW controlando la página, `Page.getInstallabilityErrors` vacío, y con `context.setOffline(true)` recargar, abrir el ejemplo y reproducir.

## Reglas

- Textos en español rioplatense.
- Tiene que andar en el celular (ancho de 360 px) y en la compu.
- Mensajes de error que digan qué pasó y qué hacer.
