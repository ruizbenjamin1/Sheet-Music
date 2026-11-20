import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'
import { useEffect, useRef, useState } from 'react'

export type ScoreViewProps = {
  /** MusicXML (sin comprimir) como texto. */
  musicxml: string
  /**
   * Zoom elegido por el usuario (1 = normal). Se multiplica por el zoom automático
   * según el ancho de la pantalla (ver `autoZoom`).
   */
  zoom?: number
  /**
   * Avisa cuándo la instancia de OSMD está lista para usar (cargada y dibujada)
   * y cuándo deja de servir (`null`: se desmontó o cambió la partitura).
   * El reproductor (E1-08) usa esta instancia para el cursor.
   */
  onOsmdChange?: (osmd: OpenSheetMusicDisplay | null) => void
  /** Si OSMD no puede dibujar la partitura. Recibe un mensaje para mostrar. */
  onError?: (message: string) => void
}

type Phase = 'loading' | 'ready' | 'error'

/** Ancho (en px de CSS) a partir del cual OSMD dibuja a tamaño normal. */
const FULL_SIZE_WIDTH = 640
const MIN_AUTO_ZOOM = 0.55

/**
 * Zoom automático según el ancho disponible. A zoom 1, en un celular (360–430 px) entra
 * un solo compás por renglón; achicando, entran 2–4 y se sigue leyendo bien.
 */
function autoZoom(width: number): number {
  return Math.min(1, Math.max(MIN_AUTO_ZOOM, width / FULL_SIZE_WIDTH))
}

/** Dibuja una partitura MusicXML con OSMD, adaptada al ancho del contenedor. */
export default function ScoreView({ musicxml, zoom = 1, onOsmdChange, onError }: ScoreViewProps) {
  const paperRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  // Instancia lista (cargada y dibujada); la usan el efecto del zoom y el de cambio de ancho.
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null)
  const zoomRef = useRef(zoom)
  // Ancho y zoom con los que se dibujó por última vez: si no cambian, no se redibuja.
  const lastLayoutRef = useRef({ width: 0, zoom: 0 })

  // Guardamos los callbacks en refs para que el efecto dependa solo del MusicXML
  // y no vuelva a dibujar cada vez que el padre crea funciones nuevas.
  const onOsmdChangeRef = useRef(onOsmdChange)
  const onErrorRef = useRef(onError)
  useEffect(() => {
    onOsmdChangeRef.current = onOsmdChange
    onErrorRef.current = onError
  })

  /** Dibuja con el zoom que corresponde al ancho actual. `force`: aunque no haya cambiado nada. */
  function layout(osmd: OpenSheetMusicDisplay, force: boolean) {
    const width = paperRef.current?.clientWidth ?? 0
    if (width === 0) return
    const target = Math.round(autoZoom(width) * zoomRef.current * 100) / 100
    const last = lastLayoutRef.current
    if (!force && last.width === width && last.zoom === target) return
    lastLayoutRef.current = { width, zoom: target }
    osmd.zoom = target
    // render() deja el cursor donde estaba (sigue andando si está sonando).
    osmd.render()
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    // Con StrictMode el efecto se monta, se desmonta y se vuelve a montar:
    // `cancelled` evita que la primera carga (ya descartada) toque el estado.
    let cancelled = false
    setPhase('loading')

    const osmd = new OpenSheetMusicDisplay(container, {
      // El cambio de ancho lo maneja el ResizeObserver de abajo, que además ajusta el zoom.
      autoResize: false,
      backend: 'svg',
      followCursor: true,
      // Título y compositor van en el encabezado de la pantalla, no dentro del dibujo.
      drawTitle: false,
      drawSubtitle: false,
      drawComposer: false,
    })

    osmd
      // Título de repuesto vacío: si el MusicXML no trae título, OSMD pondría "Untitled Score"
      // y la app no usaría el nombre del archivo.
      .load(musicxml, '')
      .then(() => {
        if (cancelled) return
        layout(osmd, true)
        osmdRef.current = osmd
        setPhase('ready')
        onOsmdChangeRef.current?.(osmd)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        console.error('OSMD no pudo dibujar la partitura', e)
        setPhase('error')
        onErrorRef.current?.(
          'No pude dibujar la partitura: el MusicXML parece estar dañado o incompleto. Probá con otro archivo.',
        )
      })

    return () => {
      cancelled = true
      osmdRef.current = null
      lastLayoutRef.current = { width: 0, zoom: 0 }
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

  // Zoom del usuario (+ / −).
  useEffect(() => {
    zoomRef.current = zoom
    if (osmdRef.current) layout(osmdRef.current, false)
  }, [zoom])

  // Cambio de ancho (girar el celular, achicar la ventana): redibujar con el zoom que corresponde.
  useEffect(() => {
    const paper = paperRef.current
    if (!paper) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const observer = new ResizeObserver(() => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        if (osmdRef.current) layout(osmdRef.current, false)
      }, 150)
    })
    observer.observe(paper)
    return () => {
      clearTimeout(timer)
      observer.disconnect()
    }
  }, [])

  return (
    <div className="score" aria-busy={phase === 'loading'}>
      {phase === 'loading' && (
        <p className="score-loading" role="status">
          <span className="spinner" aria-hidden="true" />
          Dibujando la partitura…
        </p>
      )}
      <div className="score-paper" ref={paperRef} hidden={phase === 'error'}>
        <div ref={containerRef} />
      </div>
    </div>
  )
}
