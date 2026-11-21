// Cliente del backend de lectura (OMR). En desarrollo, Vite redirige /api al
// servidor de Python (ver vite.config.ts). En producción se puede apuntar a
// otro dominio con la variable VITE_API_URL.

const API = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export type JobStatus = {
  id: string
  filename: string
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  message: string
  page: number
  pages: number
  warnings: string[]
  error: string | null
  has_result: boolean
}

async function errorDetail(res: Response): Promise<string | null> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    /* sin cuerpo JSON */
  }
  return null
}

function abortError(): DOMException {
  return new DOMException('Cancelado', 'AbortError')
}

/** Espera `ms` milisegundos; corta antes si se cancela la señal. */
function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError())
    const done = () => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }
    const onAbort = () => {
      clearTimeout(timer)
      reject(abortError())
    }
    const timer = setTimeout(done, ms)
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

const NO_CONNECTION = 'No me pude conectar con el servidor de lectura. ¿Está corriendo el backend?'

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API}${path}`, init)
  } catch (e) {
    // Si se canceló a propósito, que el error siga siendo un AbortError.
    if (init?.signal?.aborted) throw abortError()
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new Error(NO_CONNECTION)
  }
  if (!res.ok) {
    // Si el backend mandó un mensaje propio (por ejemplo 503 "cola llena"), mostrar ese.
    const detail = await errorDetail(res)
    if (detail) throw new Error(detail)
    // Con el backend apagado, el proxy de Vite (o uno de producción) responde 502/503/504 sin mensaje.
    if ([502, 503, 504].includes(res.status)) throw new Error(NO_CONNECTION)
    throw new Error(`El servidor respondió ${res.status}.`)
  }
  return res
}

export async function getHealth(): Promise<{ ok: boolean; engine: string }> {
  const res = await request('/api/health')
  return res.json()
}

export async function uploadScore(file: File, signal?: AbortSignal): Promise<JobStatus> {
  const form = new FormData()
  form.append('file', file)
  const res = await request('/api/jobs', { method: 'POST', body: form, signal })
  return res.json()
}

export async function getJob(id: string, signal?: AbortSignal): Promise<JobStatus> {
  const res = await request(`/api/jobs/${id}`, { signal })
  return res.json()
}

export async function getMusicXml(id: string, signal?: AbortSignal): Promise<string> {
  const res = await request(`/api/jobs/${id}/musicxml`, { signal })
  return res.text()
}

/**
 * Le pide al backend que corte la lectura (DELETE /api/jobs/{id}). No espera la
 * respuesta ni falla si no anda: si no llega, el trabajo vence solo.
 */
export function cancelJob(id: string): void {
  fetch(`${API}/api/jobs/${id}`, { method: 'DELETE', keepalive: true }).catch(() => {
    /* sin conexión: no hay nada más que hacer */
  })
}

/**
 * Sube el archivo y espera a que el OMR termine, avisando el progreso.
 * Si se cancela `signal`, corta la subida o la espera, le pide al backend que
 * corte la lectura (`cancelJob`) y rechaza con un DOMException de nombre 'AbortError'.
 */
export async function readScore(
  file: File,
  onProgress: (job: JobStatus) => void,
  signal?: AbortSignal,
): Promise<{ musicxml: string; warnings: string[] }> {
  let job = await uploadScore(file, signal)
  try {
    onProgress(job)
    while (job.status === 'queued' || job.status === 'running') {
      await wait(1500, signal)
      job = await getJob(job.id, signal)
      onProgress(job)
    }
  } catch (e) {
    if (signal?.aborted) cancelJob(job.id)
    throw e
  }
  if (job.status === 'cancelled') throw new Error(job.message)
  if (job.status === 'error') throw new Error(job.error ?? 'No se pudo leer la partitura.')
  return { musicxml: await getMusicXml(job.id, signal), warnings: job.warnings }
}
