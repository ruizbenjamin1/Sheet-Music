import type { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'

/** Una nota para tocar. Tiempos en redondas (1 = una redonda). */
export type PlayNote = {
  /** Altura MIDI (60 = do central). */
  midi: number
  /** Duración en redondas, con las ligaduras ya sumadas. */
  length: number
}

/** Una posición del cursor de OSMD: el reproductor hace `cursor.next()` una vez por paso. */
export type PlayStep = {
  /** Momento del paso, en redondas desde el principio. */
  time: number
  /** Notas que empiezan en este paso (puede estar vacío: silencios o notas ligadas). */
  notes: PlayNote[]
}

export type PlayScore = {
  steps: PlayStep[]
  /** Largo total de la pieza en redondas. */
  totalLength: number
  /** Tempo inicial de la partitura (negras por minuto). */
  bpm: number
}

const DEFAULT_BPM = 100

/**
 * Recorre la partitura con el cursor de OSMD y arma la lista de pasos.
 * Usa el mismo movimiento que `cursor.next()`, así el paso N del reproductor es la posición N del cursor.
 * Deja el cursor escondido y al principio.
 */
export function extractScore(osmd: OpenSheetMusicDisplay): PlayScore {
  const cursor = osmd.cursor
  // Escondido, el cursor no se dibuja ni mueve la pantalla (followCursor) mientras lo recorremos.
  cursor.hide()
  cursor.reset()

  const steps: PlayStep[] = []
  let totalLength = 0
  // Tope por si el iterador no llega nunca al final (partitura rara).
  for (let guard = 0; !cursor.Iterator.EndReached && guard < 100_000; guard++) {
    const it = cursor.Iterator
    const time = it.currentTimeStamp.RealValue
    const notes: PlayNote[] = []

    for (const entry of it.CurrentVoiceEntries ?? []) {
      if (entry.IsGrace) continue
      for (const note of entry.Notes) {
        const ownLength = note.Length.RealValue
        totalLength = Math.max(totalLength, time + ownLength)
        if (note.isRest()) continue

        let length = ownLength
        const tie = note.NoteTie
        if (tie) {
          // Solo suena la primera nota de la ligadura, con el largo de todas.
          if (tie.StartNote !== note) continue
          length = tie.Notes.reduce((sum, n) => sum + n.Length.RealValue, 0)
        }
        const midi = note.halfTone + 12
        // Si dos voces tocan la misma nota a la vez, queda la más larga.
        const same = notes.find((n) => n.midi === midi)
        if (same) same.length = Math.max(same.length, length)
        else notes.push({ midi, length })
      }
    }

    steps.push({ time, notes })
    cursor.next()
  }

  cursor.reset()

  const sheetBpm = osmd.Sheet?.DefaultStartTempoInBpm
  const bpm = sheetBpm && Number.isFinite(sheetBpm) && sheetBpm > 0 ? sheetBpm : DEFAULT_BPM
  return { steps, totalLength, bpm }
}

/** Samples Salamander Grand Piano (CC-BY 3.0, Alexander Holm): uno cada tercera menor, de A0 a C8. */
export const SALAMANDER_BASE_URL = 'https://tonejs.github.io/audio/salamander/'

export function salamanderUrls(): Record<string, string> {
  const urls: Record<string, string> = { A0: 'A0.mp3' }
  for (let octave = 1; octave <= 7; octave++) {
    for (const name of ['C', 'D#', 'F#', 'A']) {
      urls[`${name}${octave}`] = `${name.replace('#', 's')}${octave}.mp3`
    }
  }
  urls.C8 = 'C8.mp3'
  return urls
}
