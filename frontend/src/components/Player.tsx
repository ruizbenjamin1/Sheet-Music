import type { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'
import type { Sampler } from 'tone'
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { extractScore, SALAMANDER_BASE_URL, salamanderUrls, type PlayScore } from '../lib/playback'

type ToneModule = typeof import('tone')

type Phase = 'stopped' | 'loading' | 'playing' | 'paused'

const MIN_SPEED = 50
const MAX_SPEED = 150

const LOAD_ERROR =
  'No pude cargar el sonido del piano. Revisá tu conexión a internet y tocá "Reproducir" de nuevo.'

// Tone.js se baja recién en la pantalla de la partitura, no en la inicial.
let tonePromise: Promise<ToneModule> | null = null
function loadTone(): Promise<ToneModule> {
  tonePromise ??= import('tone').catch((e: unknown) => {
    tonePromise = null // para poder reintentar
    throw e
  })
  return tonePromise
}

/** Controles para tocar la partitura con piano, con el cursor de OSMD siguiendo lo que suena. */
export default function Player({ osmd }: { osmd: OpenSheetMusicDisplay | null }) {
  const [phase, setPhase] = useState<Phase>('stopped')
  const [error, setError] = useState<string | null>(null)
  const [speed, setSpeed] = useState(100)

  const toneRef = useRef<ToneModule | null>(null)
  const samplerRef = useRef<Sampler | null>(null)
  const scoreRef = useRef<{ osmd: OpenSheetMusicDisplay; score: PlayScore } | null>(null)
  // La instancia actual: los eventos ya programados no tocan un cursor viejo.
  const osmdRef = useRef(osmd)
  const speedRef = useRef(speed)
  const mountedRef = useRef(true)

  useEffect(() => {
    speedRef.current = speed
  }, [speed])

  // Precarga Tone.js para que Tone.start() pueda llamarse directo en el clic.
  useEffect(() => {
    mountedRef.current = true
    loadTone()
      .then((tone) => {
        toneRef.current = tone
      })
      .catch(() => {
        /* se reintenta al tocar "Reproducir" */
      })
    return () => {
      mountedRef.current = false
      const tone = toneRef.current
      if (tone) stopAudio(tone, samplerRef.current)
      samplerRef.current?.dispose()
      samplerRef.current = null
    }
  }, [])

  // Si cambia o se va la partitura, frenar todo. El cursor viejo ya no sirve (OSMD lo libera).
  useEffect(() => {
    osmdRef.current = osmd
    return () => {
      osmdRef.current = null
      scoreRef.current = null
      const tone = toneRef.current
      if (tone) stopAudio(tone, samplerRef.current)
      setPhase('stopped')
    }
  }, [osmd])

  async function getSampler(tone: ToneModule): Promise<Sampler> {
    if (samplerRef.current?.loaded) return samplerRef.current
    samplerRef.current?.dispose()
    samplerRef.current = null
    const sampler = await new Promise<Sampler>((resolve, reject) => {
      const s: Sampler = new tone.Sampler({
        urls: salamanderUrls(),
        baseUrl: SALAMANDER_BASE_URL,
        release: 1,
        onload: () => resolve(s),
        onerror: (e) => {
          s.dispose()
          reject(e)
        },
      }).toDestination()
    })
    if (!mountedRef.current) {
      sampler.dispose()
      throw new Error('desmontado')
    }
    samplerRef.current = sampler
    return sampler
  }

  async function handlePlay() {
    if (!osmd) return
    setError(null)

    const tone = toneRef.current
    if (tone && phase === 'paused') {
      void tone.start()
      tone.getTransport().start()
      setPhase('playing')
      return
    }

    // Tone.start() tiene que salir del clic, antes de cualquier espera.
    const started = tone?.start()
    setPhase('loading')
    let sampler: Sampler
    let t: ToneModule
    try {
      t = tone ?? (await loadTone())
      toneRef.current = t
      await (started ?? t.start())
      sampler = await getSampler(t)
    } catch (e) {
      if (!mountedRef.current) return
      console.error('No se pudo preparar el piano', e)
      setError(LOAD_ERROR)
      setPhase('stopped')
      return
    }
    // Mientras cargaba, pudo haber cambiado la partitura o haberse ido de la pantalla.
    if (!mountedRef.current || osmdRef.current !== osmd) return

    if (scoreRef.current?.osmd !== osmd) {
      scoreRef.current = { osmd, score: extractScore(osmd) }
    }
    const { score } = scoreRef.current
    if (score.steps.every((s) => s.notes.length === 0)) {
      setError('Esta partitura no tiene notas para tocar.')
      setPhase('stopped')
      return
    }

    schedule(t, sampler, osmd, score)
    setPhase('playing')
  }

  function schedule(tone: ToneModule, sampler: Sampler, current: OpenSheetMusicDisplay, score: PlayScore) {
    const transport = tone.getTransport()
    const draw = tone.getDraw()
    // Por defecto Draw descarta lo atrasado más de 0,25 s (pestaña en segundo plano, celular lento)
    // y el cursor quedaría corrido: mejor que se ponga al día.
    draw.expiration = 3600
    stopAudio(tone, sampler)
    transport.position = 0
    // La velocidad se maneja con el tempo del Transport: los pasos se programan en ticks.
    transport.bpm.value = score.bpm * (speedRef.current / 100)
    const ticksPerWhole = transport.PPQ * 4
    const toTicks = (wholes: number) => `${Math.round(wholes * ticksPerWhole)}i`

    const cursor = current.cursor
    cursor.reset()
    cursor.show()

    // Tone 15 a veces dispara dos veces el mismo evento (redondeo de ticks entre dos vueltas del reloj):
    // cada paso se toca una sola vez y en orden.
    let lastIndex = -1
    score.steps.forEach((step, index) => {
      transport.schedule((time) => {
        if (index <= lastIndex) return
        lastIndex = index
        // Segundos por redonda con el tempo de ahora (puede cambiar mientras suena).
        const secondsPerWhole = 240 / transport.bpm.value
        for (const note of step.notes) {
          const name = tone.Frequency(note.midi, 'midi').toNote()
          sampler.triggerAttackRelease(name, note.length * secondsPerWhole, time)
        }
        if (import.meta.env.DEV && step.notes.length > 0) {
          console.debug('[player] paso', index, 'redonda', step.time, 'notas', step.notes, 'a los', time)
        }
        // El primer paso es donde el cursor ya está (reset).
        if (index > 0) {
          draw.schedule(() => {
            if (osmdRef.current === current) current.cursor.next()
          }, time)
        }
      }, toTicks(step.time))
    })

    // Al terminar, volver al principio.
    transport.schedule((time) => {
      draw.schedule(() => {
        if (osmdRef.current !== current) return
        stopAudio(tone, null)
        current.cursor.reset()
        if (mountedRef.current) setPhase('stopped')
      }, time)
    }, toTicks(score.totalLength))

    transport.start()
  }

  function handlePause() {
    const tone = toneRef.current
    if (!tone) return
    tone.getTransport().pause()
    samplerRef.current?.releaseAll()
    setPhase('paused')
  }

  function handleStop() {
    const tone = toneRef.current
    if (tone) stopAudio(tone, samplerRef.current)
    if (osmd && osmdRef.current === osmd) osmd.cursor.reset()
    setPhase('stopped')
  }

  function handleSpeed(e: ChangeEvent<HTMLInputElement>) {
    const value = Number(e.target.value)
    setSpeed(value)
    const tone = toneRef.current
    const score = scoreRef.current?.score
    if (tone && score && phase !== 'stopped') tone.getTransport().bpm.value = score.bpm * (value / 100)
  }

  const ready = osmd !== null
  const busy = phase === 'loading'

  return (
    <>
      <div className="player-controls">
        <button
          type="button"
          className="btn btn-primary"
          onClick={handlePlay}
          disabled={!ready || busy || phase === 'playing'}
        >
          {phase === 'paused' ? 'Seguir' : 'Reproducir'}
        </button>
        <button type="button" className="btn btn-secondary" onClick={handlePause} disabled={phase !== 'playing'}>
          Pausa
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleStop}
          disabled={phase !== 'playing' && phase !== 'paused'}
        >
          Detener
        </button>
        <label className="player-speed">
          <span>Velocidad</span>
          <input
            type="range"
            min={MIN_SPEED}
            max={MAX_SPEED}
            step={10}
            value={speed}
            onChange={handleSpeed}
            aria-valuetext={`${speed} %`}
          />
          <output>{speed} %</output>
        </label>
      </div>

      <p className="hint" role="status" aria-live="polite">
        {!ready ? 'Preparando la partitura…' : busy ? 'Cargando piano…' : ''}
      </p>
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}

      <p className="player-credits">
        Sonido de piano: Salamander Grand Piano, de Alexander Holm (
        <a href="https://creativecommons.org/licenses/by/3.0/deed.es" target="_blank" rel="noreferrer">
          CC BY 3.0
        </a>
        ).
      </p>
    </>
  )
}

/** Frena el Transport, borra lo programado y corta las notas que suenan. */
function stopAudio(tone: ToneModule, sampler: Sampler | null) {
  const transport = tone.getTransport()
  transport.stop()
  transport.cancel()
  tone.getDraw().cancel()
  sampler?.releaseAll()
}
