import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'
import { useEffect, useRef, useState } from 'react'

export type ScoreViewProps = {
  /** MusicXML (sin comprimir) como texto. */
  musicxml: string
  /** Título a mostrar si la partitura no trae uno (por ejemplo, el nombre del archivo). */
  fallbackTitle?: string
  /**
   * Avisa cuándo la instancia de OSMD está lista para usar (cargada y dibujada)
   * y cuándo deja de servir (`null`: se desmontó o cambió la partitura).
   * El reproductor (E1-08) usa esta instancia para el cursor.
   */
  onOsmdChange?: (osmd: OpenSheetMusicDisplay | null) => void
  /** Si OSMD no puede dibujar la partitura. Recibe un mensaje para mostrar. */
  onError?: (message: string) => void
}

type State = { phase: 'loading' } | { phase: 'ready'; title: string; composer: string } | { phase: 'error' }

/** Dibuja una partitura MusicXML con OSMD, adaptada al ancho del contenedor. */
export default function ScoreView({ musicxml, fallbackTitle, onOsmdChange, onError }: ScoreViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<State>({ phase: 'loading' })

  // Guardamos los callbacks en refs para que el efecto dependa solo del MusicXML
  // y no vuelva a dibujar cada vez que el padre crea funciones nuevas.
  const onOsmdChangeRef = useRef(onOsmdChange)
  const onErrorRef = useRef(onError)
  useEffect(() => {
    onOsmdChangeRef.current = onOsmdChange
    onErrorRef.current = onError
  })

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    // Con StrictMode el efecto se monta, se desmonta y se vuelve a montar:
    // `cancelled` evita que la primera carga (ya descartada) toque el estado.
    let cancelled = false
    setState({ phase: 'loading' })

    const osmd = new OpenSheetMusicDisplay(container, {
      autoResize: true,
      backend: 'svg',
      followCursor: true,
      // Título y compositor van en el encabezado de la pantalla, no dentro del dibujo.
      drawTitle: false,
      drawSubtitle: false,
      drawComposer: false,
    })

    osmd
      .load(musicxml)
      .then(() => {
        if (cancelled) return
        osmd.render()
        setState({
          phase: 'ready',
          title: osmd.Sheet?.TitleString?.trim() ?? '',
          composer: osmd.Sheet?.ComposerString?.trim() ?? '',
        })
        onOsmdChangeRef.current?.(osmd)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        console.error('OSMD no pudo dibujar la partitura', e)
        setState({ phase: 'error' })
        onErrorRef.current?.(
          'No pude dibujar la partitura: el MusicXML parece estar dañado o incompleto. Probá con otro archivo.',
        )
      })

    return () => {
      cancelled = true
      onOsmdChangeRef.current?.(null)
      try {
        osmd.dispose()
        osmd.clear()
      } catch {
        /* si la carga no había terminado, no hay nada que limpiar */
      }
      container.innerHTML = ''
    }
  }, [musicxml])

  const title = state.phase === 'ready' ? state.title || fallbackTitle || 'Partitura sin título' : fallbackTitle

  return (
    <section className="score" aria-busy={state.phase === 'loading'}>
      <header className="score-head">
        {title && <h2 className="score-title">{title}</h2>}
        {state.phase === 'ready' && state.composer && <p className="score-composer">{state.composer}</p>}
      </header>
      {state.phase === 'loading' && <p className="score-loading">Dibujando la partitura…</p>}
      <div className="score-paper" hidden={state.phase === 'error'}>
        <div ref={containerRef} />
      </div>
    </section>
  )
}
