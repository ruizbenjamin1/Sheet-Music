/**
 * iPhone / iPad: con el interruptor de silencio activado, Web Audio no suena
 * (la sesión de audio de la página queda como "ambient"). Dos arreglos, los dos
 * dentro del clic del usuario:
 *  - Safari 17+: `navigator.audioSession.type = 'playback'`.
 *  - Antes: reproducir un <audio> HTML corto en silencio; eso pasa la sesión a
 *    "playback" y desde ahí Web Audio suena aunque el teléfono esté en silencio.
 * En los demás navegadores no hace nada.
 */

type AudioSessionNavigator = Navigator & { audioSession?: { type: string } }

let unlocked = false

/** iPhone, iPod o iPad (el iPad moderno dice ser una Mac, pero tiene pantalla táctil). */
export function isAppleMobile(): boolean {
  const ua = navigator.userAgent
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes('Macintosh') && navigator.maxTouchPoints > 1)
}

/** Tipo de sesión de audio de Safari 17+ (`undefined` si el navegador no la tiene). */
export function audioSessionType(): string | undefined {
  return (navigator as AudioSessionNavigator).audioSession?.type
}

/** Llamar en el mismo clic que `Tone.start()`, antes de cualquier `await`. Solo actúa la primera vez. */
export function unlockAppleAudio(): void {
  if (unlocked || !isAppleMobile()) return
  unlocked = true

  const session = (navigator as AudioSessionNavigator).audioSession
  if (session) {
    try {
      session.type = 'playback'
    } catch (e) {
      console.warn('No se pudo poner la sesión de audio en "playback"', e)
    }
  }

  const el = document.createElement('audio')
  el.setAttribute('playsinline', '')
  el.setAttribute('x-webkit-airplay', 'deny')
  el.preload = 'auto'
  el.loop = false
  el.src = silentWavDataUri()
  el.play().catch((e: unknown) => {
    console.warn('No se pudo reproducir el audio de silencio', e)
  })
}

/** WAV de 0,1 s de silencio (8 kHz, mono, 8 bits), armado en el momento. */
function silentWavDataUri(): string {
  const samples = 800
  const bytes = new Uint8Array(44 + samples)
  const view = new DataView(bytes.buffer)
  const text = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) bytes[offset + i] = s.charCodeAt(i)
  }
  text(0, 'RIFF')
  view.setUint32(4, 36 + samples, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true) // tamaño del bloque fmt
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, 8000, true) // muestras por segundo
  view.setUint32(28, 8000, true) // bytes por segundo
  view.setUint16(32, 1, true) // bytes por muestra
  view.setUint16(34, 8, true) // bits por muestra
  text(36, 'data')
  view.setUint32(40, samples, true)
  bytes.fill(128, 44) // 8 bits sin signo: 128 es silencio
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return `data:audio/wav;base64,${btoa(binary)}`
}
