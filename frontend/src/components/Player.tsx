import type { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'
import type { Sampler } from 'tone'
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { audioSessionType, isAppleMobile, unlockAppleAudio } from '../lib/audioUnlock'
import { extractScore, SALAMANDER_BASE_URL, salamanderUrls, type PlayScore } from '../lib/playback'

type ToneModule = typeof import('tone')

type Phase = 'stopped' | 'loading' | 'playing' | 'paused'
type SamplesState = 'sin pedir' | 'cargando' | 'cargados' | 'error'

const MIN_SPEED = 50
const MAX_SPEED = 150
/** Si el AudioContext no arranca en este tiempo, se avisa (iOS a veces deja el resume() colgado). */
const START_TIMEOUT_MS = 3000

const LOAD_ERROR =
  'No pude cargar el sonido del piano. Revisá tu conexión a internet y tocá "Reproducir" de nuevo.'
const START_ERROR = isAppleMobile()
  ? 'No pude activar el sonido. Si tenés el iPhone en silencio, sacalo y probá de nuevo.'
  : 'No pude activar el sonido. Revisá que el volumen esté alto y tocá "Reproducir" de nuevo.'

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
  const [toneReady, setToneReady] = useState(false)
  // Se tocó "Reproducir" antes de que Tone.js terminara de bajar: hay que pedir otro toque.
  const [waitingTone, setWaitingTone] = useState(false)
  // Para el diagnóstico de desarrollo.
  const [contextState, setContextState] = useState('sin crear')
  const [samplesState, setSamplesState] = useState<SamplesState>('sin pedir')
  const [lastError, setLastError] = useState<string | null>(null)

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
        if (mountedRef.current) setToneReady(true)
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

  // Sigue el estado del AudioContext. Si iOS lo corta mientras suena (bloqueo de pantalla,
  // llamada, cambio de app), queda en pausa para que "Seguir" lo retome con un toque.
  useEffect(() => {
    if (!toneReady || !toneRef.current) return
    const tone = toneRef.current
    const context = tone.getContext()
    const onStateChange = () => {
      const state = String(context.state)
      setContextState(state)
      const transport = tone.getTransport()
      if (state !== 'running' && transport.state === 'started') {
        transport.pause()
        samplerRef.current?.releaseAll()
        setPhase('paused')
      }
    }
    onStateChange()
    context.on('statechange', onStateChange)
    return () => {
      context.off('statechange', onStateChange)
    }
  }, [toneReady])

  function fail(message: string, e: unknown) {
    console.error(message, e)
    setLastError(e instanceof Error ? `${e.name}: ${e.message}` : String(e))
  }

  async function getSampler(tone: ToneModule): Promise<Sampler> {
    if (samplerRef.current?.loaded) return samplerRef.current
    samplerRef.current?.dispose()
    samplerRef.current = null
    setSamplesState('cargando')
    let sampler: Sampler
    try {
      sampler = await new Promise<Sampler>((resolve, reject) => {
        let failed = false
        const s: Sampler = new tone.Sampler({
          urls: salamanderUrls(),
          baseUrl: SALAMANDER_BASE_URL,
          release: 1,
          onload: () => resolve(s),
          // Se llama una vez por cada archivo que falla.
          onerror: (e) => {
            if (failed) return
            failed = true
            s.dispose()
            reject(e)
          },
        }).toDestination()
      })
    } catch (e) {
      if (mountedRef.current) setSamplesState('error')
      throw e
    }
    if (!mountedRef.current) {
      sampler.dispose()
      throw new Error('desmontado')
    }
    setSamplesState('cargados')
    samplerRef.current = sampler
    return sampler
  }

  function handlePlay() {
    if (!osmd) return
    setError(null)

    const tone = toneRef.current
    if (!tone) {
      // Sin Tone.js no se puede arrancar el audio dentro de este toque: se baja y se pide otro.
      setWaitingTone(true)
      loadTone()
        .then((t) => {
          toneRef.current = t
          if (mountedRef.current) setToneReady(true)
        })
        .catch((e: unknown) => {
          if (!mountedRef.current) return
          fail('No se pudo cargar Tone.js', e)
          setWaitingTone(false)
          setError(LOAD_ERROR)
        })
      return
    }
    setWaitingTone(false)

    // Todo esto tiene que pasar en el toque, antes de cualquier espera.
    unlockAppleAudio()
    const running = ensureRunning(tone)

    if (phase === 'paused') {
      setPhase('loading')
      running.then(
        () => {
          if (!mountedRef.current) return
          tone.getTransport().start()
          setPhase('playing')
        },
        (e: unknown) => {
          if (!mountedRef.current) return
          fail('No arrancó el audio', e)
          setError(START_ERROR)
          setPhase('paused')
        },
      )
      return
    }

    setPhase('loading')
    void prepareAndPlay(tone, osmd, running)
  }

  async function prepareAndPlay(tone: ToneModule, current: OpenSheetMusicDisplay, running: Promise<void>) {
    try {
      await running
    } catch (e) {
      if (!mountedRef.current) return
      fail('No arrancó el audio', e)
      setError(START_ERROR)
      setPhase('stopped')
      return
    }
    let sampler: Sampler
    try {
      sampler = await getSampler(tone)
    } catch (e) {
      if (!mountedRef.current) return
      fail('No se pudieron cargar los samples del piano', e)
      setError(LOAD_ERROR)
      setPhase('stopped')
      return
    }
    // Mientras cargaba, pudo haber cambiado la partitura o haberse ido de la pantalla.
    if (!mountedRef.current || osmdRef.current !== current) return

    if (scoreRef.current?.osmd !== current) {
      scoreRef.current = { osmd: current, score: extractScore(current) }
    }
    const { score } = scoreRef.current
    if (score.steps.every((s) => s.notes.length === 0)) {
      setError('Esta partitura no tiene notas para tocar.')
      setPhase('stopped')
      return
    }

    schedule(tone, sampler, current, score)
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
        {!ready
          ? 'Preparando la partitura…'
          : busy
            ? 'Cargando piano…'
            : waitingTone
              ? toneReady
                ? 'Listo. Tocá "Reproducir" otra vez.'
                : 'Cargando… En un momento tocá "Reproducir" otra vez.'
              : ''}
      </p>
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
      {import.meta.env.DEV && (
        <p className="player-debug">
          [dev] Tone: {toneReady ? 'cargado' : 'sin cargar'} · contexto: {contextState} · samples: {samplesState} ·
          sesión iOS: {audioSessionType() ?? 'no hay'} · iPhone/iPad: {isAppleMobile() ? 'sí' : 'no'}
          {lastError && <> · último error: {lastError}</>}
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

/**
 * Arranca (o retoma) el AudioContext. Hay que llamarla dentro del toque, sin `await` antes:
 * el `resume()` sale en el momento. Sirve también para "interrupted" (iOS después de bloquear
 * la pantalla o cambiar de app). Falla si no queda en "running" a los pocos segundos.
 */
function ensureRunning(tone: ToneModule): Promise<void> {
  const context = tone.getContext()
  if (context.state === 'running') return Promise.resolve()
  const resumed = tone.start()
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`el AudioContext quedó en "${String(context.state)}"`))
    }, START_TIMEOUT_MS)
    resumed.then(
      () => {
        clearTimeout(timer)
        if (context.state === 'running') resolve()
        else reject(new Error(`el AudioContext quedó en "${String(context.state)}"`))
      },
      (e: unknown) => {
        clearTimeout(timer)
        reject(e instanceof Error ? e : new Error(String(e)))
      },
    )
  })
}

/** Frena el Transport, borra lo programado y corta las notas que suenan. */
function stopAudio(tone: ToneModule, sampler: Sampler | null) {
  const transport = tone.getTransport()
  transport.stop()
  transport.cancel()
  tone.getDraw().cancel()
  sampler?.releaseAll()
}
