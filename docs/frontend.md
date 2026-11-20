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

- `src/App.tsx`: la app. Tres pantallas en un estado `screen`: `home` (subir), `reading` (progreso) y `score` (encabezado + partitura + barra del reproductor). Si el backend no responde muestra un aviso, pero igual se puede abrir un MusicXML o el ejemplo. Diseño de cada pantalla: ver "Pantallas (celular primero)".
- `src/components/ScoreView.tsx`: dibuja un MusicXML con OSMD y expone la instancia (ver abajo). Se carga con `React.lazy` para no bajar OSMD hasta que hace falta.
- `src/components/Player.tsx`: reproductor (reproducir / pausa / detener / velocidad) con el cursor de OSMD. Detalle en `docs/audio.md`. Exporta también `PianoCredits` (créditos de los samples).
- `src/lib/playback.ts`: saca las notas de la partitura con el cursor de OSMD y arma la lista de samples del piano.
- `src/lib/audioUnlock.ts`: en iPhone / iPad, hace que el audio suene aunque el teléfono esté en silencio (ver `docs/audio.md`).
- `src/lib/api.ts`: cliente del backend. `readScore(file, onProgress, signal)` sube, sondea cada 1,5 s y devuelve `{ musicxml, warnings }`. La señal se pasa a cada `fetch` y corta también la espera; al cancelar rechaza con un `DOMException` `AbortError` (el trabajo sigue en el backend hasta vencer).
- `public/samples/`: partituras de ejemplo **de dominio público** para probar sin backend.
- `vite.config.ts`: proxy `/api` y configuración de la PWA.

## OpenSheetMusicDisplay (OSMD)

- `new OpenSheetMusicDisplay(div, { autoResize: false, backend: 'svg', followCursor: true })`, `await osmd.load(xml)`, `osmd.render()`.
- **Zoom**: `autoResize` está apagado; un `ResizeObserver` sobre `.score-paper` (con 150 ms de espera) pone `osmd.zoom` y llama `render()` cuando cambia el ancho. Zoom = automático × el del usuario. Automático = `ancho / 640`, entre 0,55 y 1 (a 375 px queda ~0,59 y entran 3–4 compases por renglón; desde 640 px es 1). El del usuario son las lupas del encabezado: 0,7 / 0,85 / 1 / 1,2 / 1,45 / 1,75 (vuelve a 1 al abrir otra partitura). Si no cambian ni el ancho ni el zoom, no se redibuja. `render()` deja el cursor donde estaba, también mientras suena.
- El cursor (`osmd.cursor`) recorre la partitura: `reset()`, `next()`, `show()`, `hide()`, `Iterator.EndReached`.
- Con `StrictMode` el efecto se monta dos veces: limpiar el contenedor al desmontar (`dispose()`, `clear()`, vaciar el div).
- Título y compositor se muestran en el encabezado de la pantalla (`App.tsx` los lee de `osmd.Sheet.TitleString` / `ComposerString`; si no hay título, el nombre del archivo). En el dibujo están apagados (`drawTitle`, `drawSubtitle` y `drawComposer` en `false`).
- La partitura se dibuja siempre sobre fondo blanco (`.score-paper`), también en modo oscuro.

### ScoreView (para el reproductor)

```tsx
<ScoreView
  musicxml={string}                 // MusicXML sin comprimir
  zoom?={number}                    // zoom del usuario (1 = normal), se multiplica por el automático
  onOsmdChange?={(osmd: OpenSheetMusicDisplay | null) => void}
  onError?={(mensaje: string) => void}
/>
```

`onOsmdChange` recibe la instancia ya cargada y dibujada, y `null` cuando se desmonta o cambia la partitura. `App.tsx` la guarda en el estado `osmd`; los controles de reproducción van en la barra fija de abajo (`<section className="player-bar">`).

## Subida

- PDF o imagen (PNG, JPG, WEBP), hasta 20 MB (se chequea antes de subir). "Sacar una foto" es un `<input type="file" accept="image/*" capture="environment">`; se muestra solo con pantalla táctil (`(pointer: coarse)`), donde es la acción principal. En la compu el botón principal es "Elegir una foto o un PDF".
- MusicXML (`.musicxml`, `.xml`) se lee con `file.text()` sin pasar por el backend; se valida que tenga `<score-partwise` o `<score-timewise`. `.mxl` comprimido todavía no.
- Los `warnings` del backend se muestran arriba de la partitura, plegados (`<details>`) con la cantidad.

## Pantallas (celular primero)

Se diseña para el celular (360–430 px) y se agranda para la compu. Probado con capturas a 375 × 812, 390 × 844 (iPhone emulado) y 1280 × 800, en claro y oscuro.

- **Inicio** (`.home`, ocupa el alto de la pantalla, máx. 480 px de ancho): marca chica arriba, dibujo propio de un pentagrama (SVG en `App.tsx`), título "Sacale una foto a la partitura y escuchala" y, abajo (zona del pulgar), "Sacar una foto" grande (64 px), "Elegir foto o PDF" y, discretos, "Abrir MusicXML · Probar un ejemplo". Los avisos (error, cancelado, servidor caído) van justo arriba de los botones. En la compu (`min-width: 720px` y mouse) queda centrado.
- **Leyendo** (`Progress`): centrado, pentagrama animado, "Leyendo la partitura…", "Suele tardar menos de un minuto.", barra (indeterminada hasta saber el total; con varias páginas avanza por página y dice "Página N de M"), nombre del archivo y "Cancelar".
- **Partitura**: encabezado fijo arriba (`.topbar`, sticky) con volver (abre otra), título y compositor recortados con "…", y lupas −/+. La partitura va de borde a borde en el celular (en la compu, papel con bordes redondeados). Abajo, los créditos del piano en letra chica. El reproductor es una barra fija abajo (`.player-bar`): Detener (círculo), Reproducir / Pausa / Seguir (grande, en el medio) y Velocidad (muestra el %; al tocarla se despliega arriba un control −, slider, + y "Normal"). Los mensajes del reproductor (cargando, errores) aparecen dentro de la barra, arriba de los botones. En desarrollo, el diagnóstico `[dev]` es una pestañita "dev" arriba a la derecha de la barra que se abre al tocarla.

### Detalles de app nativa

- `index.html`: `viewport-fit=cover`, `theme-color` claro (`#faf9f6`) y oscuro (`#141317`), `apple-mobile-web-app-capable`, `color-scheme`.
- Zonas seguras del iPhone con `env(safe-area-inset-*)` (variables `--safe-*` en `index.css`): arriba en el inicio, la lectura y el encabezado; abajo en el inicio y la barra del reproductor; a los costados en todo.
- Alto con `100dvh` (y `100vh` de respaldo).
- Sin resaltado gris al tocar (`-webkit-tap-highlight-color`), `touch-action: manipulation` en botones (sin espera por doble toque), botones de al menos 44 px (los principales 52–64 px), inputs con letra de 16 px o más (el iPhone no hace zoom), hover solo con `(hover: hover) and (pointer: fine)` y efecto al apretar (`:active`).
- `scroll-padding` arriba y abajo para que `followCursor` no deje el cursor debajo de las barras.
- Animaciones cortadas con `prefers-reduced-motion`.
- Modo claro y oscuro con variables CSS; la partitura siempre sobre papel blanco.

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
