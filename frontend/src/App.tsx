import type { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'
import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ChangeEvent,
  type ReactNode,
} from 'react'
import Player, { PianoCredits } from './components/Player'
import { getHealth, readScore, type JobStatus } from './lib/api'

// OSMD pesa bastante: se baja recién cuando hay una partitura para mostrar.
const ScoreView = lazy(() => import('./components/ScoreView'))

const SAMPLE_URL = '/samples/oda-a-la-alegria.musicxml'
const MAX_UPLOAD_MB = 20
/** Zoom del usuario sobre el automático (ver ScoreView). */
const ZOOM_LEVELS = [0.7, 0.85, 1, 1.2, 1.45, 1.75]

// Pantalla táctil (celular, tablet): ahí "Sacar una foto" es la acción principal.
// En la compu la cámara no aplica y se ofrece elegir un archivo.
const COARSE = '(pointer: coarse)'
function subscribeCoarse(onChange: () => void) {
  const mq = window.matchMedia(COARSE)
  mq.addEventListener('change', onChange)
  return () => mq.removeEventListener('change', onChange)
}
function useTouch(): boolean {
  return useSyncExternalStore(subscribeCoarse, () => window.matchMedia(COARSE).matches)
}

type Backend = 'checking' | 'ok' | 'down'

type Screen =
  | { name: 'home' }
  | { name: 'reading'; filename: string; job: JobStatus | null }
  | { name: 'score'; musicxml: string; filename: string; warnings: string[] }

function isMusicXml(text: string): boolean {
  return /<score-(partwise|timewise)[\s>]/.test(text)
}

function stripExtension(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

export default function App() {
  const [backend, setBackend] = useState<Backend>('checking')
  const [screen, setScreen] = useState<Screen>({ name: 'home' })
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // Instancia de OSMD de la partitura en pantalla; la usa el reproductor.
  const [osmd, setOsmd] = useState<OpenSheetMusicDisplay | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [zoom, setZoom] = useState(1)
  const touch = useTouch()

  useEffect(() => {
    let alive = true
    getHealth()
      .then(() => alive && setBackend('ok'))
      .catch(() => alive && setBackend('down'))
    return () => {
      alive = false
    }
  }, [])

  // Si la app se cierra en medio de una lectura, cortar la espera.
  useEffect(() => () => abortRef.current?.abort(), [])

  function resetMessages() {
    setError(null)
    setNotice(null)
  }

  async function handleScan(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // para poder elegir el mismo archivo otra vez
    if (!file) return
    resetMessages()

    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(`El archivo pesa más de ${MAX_UPLOAD_MB} MB. Probá con uno más liviano o con menos páginas.`)
      return
    }

    const controller = new AbortController()
    abortRef.current = controller
    setScreen({ name: 'reading', filename: file.name, job: null })
    try {
      const result = await readScore(
        file,
        (job) => {
          if (!controller.signal.aborted) setScreen({ name: 'reading', filename: file.name, job })
        },
        controller.signal,
      )
      setScreen({ name: 'score', musicxml: result.musicxml, filename: file.name, warnings: result.warnings })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setNotice('Cancelaste la lectura.')
      } else {
        setError(err instanceof Error ? err.message : 'No se pudo leer la partitura. Probá de nuevo.')
      }
      setScreen({ name: 'home' })
    } finally {
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  async function handleMusicXml(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    resetMessages()

    if (/\.mxl$/i.test(file.name)) {
      setError('Los MusicXML comprimidos (.mxl) todavía no se pueden abrir. Exportalo como .musicxml sin comprimir.')
      return
    }
    let text: string
    try {
      text = await file.text()
    } catch {
      setError('No pude leer el archivo. Probá elegirlo de nuevo.')
      return
    }
    if (!isMusicXml(text)) {
      setError('Ese archivo no parece un MusicXML. Elegí un archivo .musicxml o .xml exportado de un editor de partituras.')
      return
    }
    setScreen({ name: 'score', musicxml: text, filename: file.name, warnings: [] })
  }

  async function handleSample() {
    resetMessages()
    try {
      const res = await fetch(SAMPLE_URL)
      if (!res.ok) throw new Error()
      const text = await res.text()
      if (!isMusicXml(text)) throw new Error()
      setScreen({ name: 'score', musicxml: text, filename: 'Oda a la alegría', warnings: [] })
    } catch {
      setError('No pude abrir el ejemplo. Revisá tu conexión y probá de nuevo.')
    }
  }

  function handleCancel() {
    abortRef.current?.abort()
  }

  function handleShowError(message: string) {
    setError(message)
    setScreen({ name: 'home' })
  }

  function goHome() {
    resetMessages()
    setZoom(1)
    setScreen({ name: 'home' })
  }

  function changeZoom(step: number) {
    setZoom((z) => {
      const i = ZOOM_LEVELS.indexOf(z)
      return ZOOM_LEVELS[Math.min(ZOOM_LEVELS.length - 1, Math.max(0, i + step))] ?? 1
    })
  }

  if (screen.name === 'reading') {
    return <Progress filename={screen.filename} job={screen.job} onCancel={handleCancel} />
  }

  if (screen.name === 'score') {
    const title = osmd?.Sheet?.TitleString?.trim() || stripExtension(screen.filename) || 'Partitura sin título'
    const composer = osmd?.Sheet?.ComposerString?.trim() ?? ''
    const zoomIndex = ZOOM_LEVELS.indexOf(zoom)
    return (
      <div className="score-screen">
        <header className="topbar">
          <div className="topbar-inner">
            <button type="button" className="icon-btn" onClick={goHome} aria-label="Volver y abrir otra partitura">
              <BackIcon />
            </button>
            <div className="topbar-title">
              <h1>{title}</h1>
              {composer && <p>{composer}</p>}
            </div>
            <div className="zoom" role="group" aria-label="Tamaño de la partitura">
              <button
                type="button"
                className="icon-btn"
                onClick={() => changeZoom(-1)}
                disabled={zoomIndex <= 0}
                aria-label="Achicar la partitura"
              >
                <ZoomOutIcon />
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={() => changeZoom(1)}
                disabled={zoomIndex >= ZOOM_LEVELS.length - 1}
                aria-label="Agrandar la partitura"
              >
                <ZoomInIcon />
              </button>
            </div>
          </div>
        </header>

        <main className="score-main">
          {screen.warnings.length > 0 && (
            <details className="alert alert-warn warnings">
              <summary>Revisala: la lectura puede tener errores ({screen.warnings.length})</summary>
              <ul>
                {screen.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          )}

          <Suspense
            fallback={
              <p className="score-loading" role="status">
                <span className="spinner" aria-hidden="true" />
                Preparando el visor…
              </p>
            }
          >
            <ScoreView musicxml={screen.musicxml} zoom={zoom} onOsmdChange={setOsmd} onError={handleShowError} />
          </Suspense>

          <PianoCredits />
        </main>

        <section className="player-bar" aria-label="Reproducción">
          <Player osmd={osmd} />
        </section>
      </div>
    )
  }

  return (
    <main className="home">
      <header className="home-brand">
        <img src="/favicon.svg" alt="" width={28} height={28} />
        <span>Partituras</span>
      </header>

      <section className="home-hero">
        <StaffArt />
        <h1>Sacale una foto a la partitura y escuchala</h1>
        <p>La leemos, te la mostramos y la tocamos con sonido de piano.</p>
      </section>

      <section className="home-actions" aria-label="Abrir una partitura">
        {error && (
          <p className="alert alert-error" role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p className="alert" role="status">
            {notice}
          </p>
        )}
        {backend === 'down' && (
          <p className="alert alert-warn" role="status">
            Ahora no se pueden leer fotos ni PDF: el servidor no responde. Probá más tarde, o abrí el ejemplo.
          </p>
        )}

        {touch && (
          <label className="btn btn-primary btn-xl">
            <input
              type="file"
              className="visually-hidden"
              accept="image/*"
              capture="environment"
              onChange={handleScan}
            />
            <CameraIcon />
            Sacar una foto
          </label>
        )}
        <label className={touch ? 'btn btn-secondary btn-lg' : 'btn btn-primary btn-xl'}>
          <input
            type="file"
            className="visually-hidden"
            accept="application/pdf,.pdf,image/png,image/jpeg,image/webp"
            onChange={handleScan}
          />
          <FileIcon />
          {touch ? 'Elegir foto o PDF' : 'Elegir una foto o un PDF'}
        </label>
        <p className="home-fineprint">Hasta {MAX_UPLOAD_MB} MB y 10 páginas.</p>

        <div className="home-more">
          <label className="link-btn">
            <input
              type="file"
              className="visually-hidden"
              accept=".musicxml,.xml,application/vnd.recordare.musicxml+xml,application/xml,text/xml"
              onChange={handleMusicXml}
            />
            Abrir MusicXML
          </label>
          <span aria-hidden="true">·</span>
          <button type="button" className="link-btn" onClick={handleSample}>
            Probar un ejemplo
          </button>
        </div>
      </section>
    </main>
  )
}

function Progress({ filename, job, onCancel }: { filename: string; job: JobStatus | null; onCancel: () => void }) {
  const known = job !== null && job.pages > 1
  // Mientras lee la página N, cuenta las N-1 anteriores como hechas.
  const percent = known ? Math.round((Math.max(job.page - 1, 0) / job.pages) * 100) : null
  const step = !job
    ? 'Subiendo el archivo…'
    : job.status === 'queued'
      ? 'Esperando turno…'
      : known
        ? `Página ${Math.max(job.page, 1)} de ${job.pages}`
        : job.message || 'Leyendo…'

  return (
    <main className="reading" aria-live="polite">
      <div className="reading-card">
        <StaffArt animated />
        <h1>Leyendo la partitura…</h1>
        <p className="reading-sub">Suele tardar uno o dos minutos.</p>
        <div
          className={`bar${percent === null ? ' bar-indeterminate' : ''}`}
          role="progressbar"
          aria-label="Progreso de la lectura"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? undefined}
        >
          <span style={percent === null ? undefined : { width: `${Math.max(percent, 4)}%` }} />
        </div>
        <p className="reading-step">{step}</p>
        <p className="reading-file">{filename}</p>
        <button type="button" className="btn btn-secondary btn-lg reading-cancel" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </main>
  )
}

/** Dibujo propio: un pentagrama con cuatro notas (sin derechos de terceros). */
function StaffArt({ animated = false }: { animated?: boolean }) {
  const notes = [
    { x: 38, y: 40 },
    { x: 70, y: 32 },
    { x: 102, y: 24 },
    { x: 134, y: 36 },
  ]
  return (
    <svg className={`staff-art${animated ? ' is-animated' : ''}`} viewBox="0 0 160 56" aria-hidden="true">
      {[12, 20, 28, 36, 44].map((y) => (
        <line key={y} x1="4" x2="156" y1={y} y2={y} />
      ))}
      {notes.map(({ x, y }, i) => (
        <g key={x} className="staff-note" style={{ animationDelay: `${i * 0.25}s` }}>
          <ellipse cx={x} cy={y} rx="6" ry="4.5" transform={`rotate(-20 ${x} ${y})`} />
          <rect x={x + 4.6} y={y - 26} width="2" height="25" rx="1" />
        </g>
      ))}
    </svg>
  )
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

function CameraIcon() {
  return (
    <Icon>
      <path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.6l1.2-1.8a1.5 1.5 0 0 1 1.2-.7h3a1.5 1.5 0 0 1 1.2.7L15.9 6h1.6A2.5 2.5 0 0 1 20 8.5v8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5Z" />
      <circle cx="12" cy="12.5" r="3.5" />
    </Icon>
  )
}

function FileIcon() {
  return (
    <Icon>
      <path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8Z" />
      <path d="M14 3.5V8h4.5" />
    </Icon>
  )
}

function BackIcon() {
  return (
    <Icon>
      <path d="M15 5l-7 7 7 7" />
    </Icon>
  )
}

function ZoomOutIcon() {
  return (
    <Icon>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M8 11h6M16 16l4 4" />
    </Icon>
  )
}

function ZoomInIcon() {
  return (
    <Icon>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M8 11h6M11 8v6M16 16l4 4" />
    </Icon>
  )
}
