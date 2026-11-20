# Audio y reproducción

Todo en el navegador con Tone.js (`tone` 15).

## Piano

- `Tone.Sampler` con los samples **Salamander Grand Piano** (CC-BY 3.0, Alexander Holm) desde `https://tonejs.github.io/audio/salamander/`. Archivos `A0.mp3`, `C1.mp3`, `Ds1.mp3`, `Fs1.mp3`, `A1.mp3` … `C8.mp3` (el `#` va como `s` en el nombre del archivo).
- `await Tone.start()` tiene que llamarse desde un clic del usuario (política de audio de los navegadores).
- Créditos de los samples: se muestran en chico abajo de los controles del reproductor ("Sonido de piano: Salamander Grand Piano, de Alexander Holm (CC BY 3.0)", con link a la licencia). Si después hay pantalla "Acerca de", repetirlos ahí.
- Los samples se bajan recién al primer "Reproducir" (mientras tanto se ve "Cargando piano…"; si fallan, un error que pide revisar la conexión). El `Sampler` se libera (`dispose()`) al salir de la pantalla de la partitura.

## De OSMD a notas

Recorrer la partitura con el cursor de OSMD, un paso por posición:

- `cursor.Iterator.currentTimeStamp.RealValue`: momento del paso, en redondas (1 = una redonda).
- `cursor.Iterator.CurrentVoiceEntries` → cada `VoiceEntry.Notes` → `Note`.
- Saltar `VoiceEntry.IsGrace` y `note.isRest()`.
- Altura MIDI = `note.halfTone + 12`.
- Duración = `note.Length.RealValue` redondas. Ligaduras: si `note.NoteTie` existe y la nota no es `NoteTie.StartNote`, saltarla; si es la primera, sumar el largo de todas las de `NoteTie.Notes`.
- Tempo: `osmd.Sheet.DefaultStartTempoInBpm` (si no hay, 100). Segundos por redonda = `240 / bpm`.

Implementado en `src/lib/playback.ts` (`extractScore(osmd)` → pasos `{ time, notes: [{ midi, length }] }`, `totalLength`, `bpm`). Recorre con el mismo cursor (`cursor.next()`), escondido para que no se dibuje ni mueva la pantalla, y lo deja al principio: el paso N del reproductor es la posición N del cursor. Se calcula una vez por partitura, al primer "Reproducir".

## Reproducir

Componente `src/components/Player.tsx` (`<Player osmd={osmd} />`, dentro de `<section className="player">`).

- Tone.js se carga con `import('tone')` cuando se monta el reproductor (pantalla de la partitura), no en la inicial. Así, al hacer clic, `Tone.start()` se llama directo en el clic, antes de cualquier espera.
- Cada paso se programa con `transport.schedule(cb, "<ticks>i")` (redondas × `PPQ` × 4) y el cursor se mueve con `Tone.getDraw().schedule(() => cursor.next(), time)` en el mismo tiempo, así lo que se ve coincide con lo que suena.
- `Draw.expiration` se sube a 3600 s: por defecto Tone descarta los dibujos atrasados más de 0,25 s (pestaña en segundo plano, celular lento) y el cursor quedaría corrido.
- Tone 15 a veces dispara dos veces el mismo evento del Transport (redondeo de ticks): cada paso guarda el último índice tocado y no repite.
- Al final de la pieza hay un evento que frena todo y vuelve el cursor al principio.
- Pausa: `transport.pause()` + `sampler.releaseAll()`. Detener: `transport.stop()`, `transport.cancel()`, `Draw.cancel()`, `releaseAll()`, `cursor.reset()`.
- Velocidad (50 % a 150 %, de a 10): se maneja con el tempo del Transport (`transport.bpm.value = bpm × velocidad`). Como los pasos están en ticks, se puede cambiar mientras suena; la duración de cada nota se calcula con el tempo del momento en que se toca.
- Si la partitura cambia (`osmd` pasa a `null` u otra instancia) o se sale de la pantalla: Transport stop/cancel, `Draw.cancel()`, y los eventos ya programados no tocan el cursor viejo.
- Con `autoResize`, OSMD redibuja al cambiar el ancho y deja el cursor donde estaba (probado: sigue avanzando en el dibujo nuevo).
- En desarrollo, cada paso con notas se loguea con `console.debug('[player] paso', …)` (nivel "Verbose" en la consola); en el build no está.
- Todavía no: repeticiones / saltos más allá de lo que haga el iterador de OSMD, cambios de tempo en el medio, dinámicas (todas las notas con la misma fuerza).

## Más adelante

- Etapa 4: Web MIDI (`navigator.requestMIDIAccess()`) para escuchar el teclado. El Casio CT-670 sale por DIN de 5 pines: necesita adaptador USB-MIDI.
