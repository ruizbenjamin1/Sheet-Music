# Audio y reproducción

Todo en el navegador con Tone.js (`tone` 15).

## Piano

- `Tone.Sampler` con los samples **Salamander Grand Piano** (CC-BY 3.0, Alexander Holm) desde `https://tonejs.github.io/audio/salamander/`. Archivos `A0.mp3`, `C1.mp3`, `Ds1.mp3`, `Fs1.mp3`, `A1.mp3` … `C8.mp3` (el `#` va como `s` en el nombre del archivo).
- `await Tone.start()` tiene que llamarse desde un clic del usuario (política de audio de los navegadores).
- Créditos de los samples: mostrarlos en la app (pantalla "Acerca de").

## De OSMD a notas

Recorrer la partitura con el cursor de OSMD, un paso por posición:

- `cursor.Iterator.currentTimeStamp.RealValue`: momento del paso, en redondas (1 = una redonda).
- `cursor.Iterator.CurrentVoiceEntries` → cada `VoiceEntry.Notes` → `Note`.
- Saltar `VoiceEntry.IsGrace` y `note.isRest()`.
- Altura MIDI = `note.halfTone + 12`.
- Duración = `note.Length.RealValue` redondas. Ligaduras: si `note.NoteTie` existe y la nota no es `NoteTie.StartNote`, saltarla; si es la primera, sumar el largo de todas las de `NoteTie.Notes`.
- Tempo: `osmd.Sheet.DefaultStartTempoInBpm` (si no hay, 100). Segundos por redonda = `240 / bpm`.

## Reproducir

- Programar cada paso con el `Transport` de Tone y mover el cursor con `Tone.getDraw().schedule(...)` en el mismo tiempo, así lo que se ve coincide con lo que suena.
- Pausa: `transport.pause()`. Detener: `transport.stop()`, `transport.cancel()`, `cursor.reset()`.
- Velocidad: recalcular los tiempos con el multiplicador (deshabilitar el control mientras suena, o reprogramar).

## Más adelante

- Etapa 4: Web MIDI (`navigator.requestMIDIAccess()`) para escuchar el teclado. El Casio CT-670 sale por DIN de 5 pines: necesita adaptador USB-MIDI.
