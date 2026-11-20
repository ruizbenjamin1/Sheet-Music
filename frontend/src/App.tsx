import type { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'
import { lazy, Suspense, useEffect, useRef, useState, type ChangeEvent } from 'react'
import Player from './components/Player'
import { getHealth, readScore, type JobStatus } from './lib/api'

// OSMD pesa bastante: se baja recién cuando hay una partitura para mostrar.
const ScoreView = lazy(() => import('./components/ScoreView'))

const SAMPLE_URL = '/samples/oda-a-la-alegria.musicxml'
const MAX_UPLOAD_MB = 20

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
    setScreen({ name: 'home' })
  }

  return (
    <main className="shell">
      <header className="app-head">
        <h1>Partituras</h1>
        {screen.name === 'score' && (
          <button type="button" className="btn btn-secondary" onClick={goHome}>
            Abrir otra
          </button>
        )}
      </header>

      {screen.name === 'home' && (
        <>
          <p className="lead">Subí una partitura de piano, mirala y escuchala.</p>

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
              El servidor de lectura no responde, así que por ahora no se pueden leer PDF ni fotos. Igual podés abrir
              un MusicXML o probar el ejemplo.
            </p>
          )}

          <section className="card" aria-labelledby="leer-titulo">
            <h2 id="leer-titulo">Leer una partitura</h2>
            <p className="hint">PDF o imagen (PNG, JPG o WEBP), hasta {MAX_UPLOAD_MB} MB y 10 páginas.</p>
            <div className="actions">
              <label className="btn btn-primary">
                <input
                  type="file"
                  className="visually-hidden"
                  accept="application/pdf,.pdf,image/png,image/jpeg,image/webp"
                  onChange={handleScan}
                />
                Elegir PDF o imagen
              </label>
              <label className="btn btn-secondary">
                <input
                  type="file"
                  className="visually-hidden"
                  accept="image/*"
                  capture="environment"
                  onChange={handleScan}
                />
                Sacar una foto
              </label>
            </div>
          </section>

          <section className="card" aria-labelledby="abrir-titulo">
            <h2 id="abrir-titulo">¿Ya tenés el MusicXML?</h2>
            <p className="hint">Se abre directo en tu dispositivo, sin pasar por el servidor.</p>
            <div className="actions">
              <label className="btn btn-secondary">
                <input
                  type="file"
                  className="visually-hidden"
                  accept=".musicxml,.xml,application/vnd.recordare.musicxml+xml,application/xml,text/xml"
                  onChange={handleMusicXml}
                />
                Abrir MusicXML
              </label>
              <button type="button" className="btn btn-ghost" onClick={handleSample}>
                Probar con un ejemplo
              </button>
            </div>
          </section>
        </>
      )}

      {screen.name === 'reading' && <Progress filename={screen.filename} job={screen.job} onCancel={handleCancel} />}

      {screen.name === 'score' && (
        <>
          {screen.warnings.length > 0 && (
            <div className="alert alert-warn" role="status">
              <p>La partitura se leyó, pero revisala: puede tener errores.</p>
              <ul>
                {screen.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <section className="player" aria-label="Reproducción">
            <Player osmd={osmd} />
          </section>

          <Suspense fallback={<p className="score-loading">Preparando el visor…</p>}>
            <ScoreView
              musicxml={screen.musicxml}
              fallbackTitle={stripExtension(screen.filename)}
              onOsmdChange={setOsmd}
              onError={handleShowError}
            />
          </Suspense>
        </>
      )}
    </main>
  )
}

function Progress({ filename, job, onCancel }: { filename: string; job: JobStatus | null; onCancel: () => void }) {
  const known = job !== null && job.pages > 0
  // Mientras lee la página N, cuenta las N-1 anteriores como hechas.
  const percent = known ? Math.round((Math.max(job.page - 1, 0) / job.pages) * 100) : undefined
  const message = job?.message || (job ? 'En la fila, esperando turno…' : 'Subiendo el archivo…')

  return (
    <section className="card progress-card" aria-live="polite">
      <h2>Leyendo la partitura</h2>
      <p className="hint file-name">{filename}</p>
      <progress className="progress" max={100} value={percent} aria-label="Progreso de la lectura" />
      <p className="progress-msg">{message}</p>
      <p className="hint">Puede tardar unos minutos por página.</p>
      <div className="actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </section>
  )
}
