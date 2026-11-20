// Cliente del backend de lectura (OMR). En desarrollo, Vite redirige /api al
// servidor de Python (ver vite.config.ts). En producción se puede apuntar a
// otro dominio con la variable VITE_API_URL.

const API = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export type JobStatus = {
  id: string
  filename: string
  status: 'queued' | 'running' | 'done' | 'error'
  message: string
  page: number
  pages: number
  warnings: string[]
  error: string | null
  has_result: boolean
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    /* sin cuerpo JSON */
  }
  return `El servidor respondió ${res.status}.`
}

const NO_CONNECTION = 'No me pude conectar con el servidor de lectura. ¿Está corriendo el backend?'

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API}${path}`, init)
  } catch {
    throw new Error(NO_CONNECTION)
  }
  // Con el backend apagado, el proxy de Vite (o uno de producción) responde 502/503/504.
  if ([502, 503, 504].includes(res.status)) throw new Error(NO_CONNECTION)
  if (!res.ok) throw new Error(await errorText(res))
  return res
}

export async function getHealth(): Promise<{ ok: boolean; engine: string }> {
  const res = await request('/api/health')
  return res.json()
}

export async function uploadScore(file: File): Promise<JobStatus> {
  const form = new FormData()
  form.append('file', file)
  const res = await request('/api/jobs', { method: 'POST', body: form })
  return res.json()
}

export async function getJob(id: string): Promise<JobStatus> {
  const res = await request(`/api/jobs/${id}`)
  return res.json()
}

export async function getMusicXml(id: string): Promise<string> {
  const res = await request(`/api/jobs/${id}/musicxml`)
  return res.text()
}

/** Sube el archivo y espera a que el OMR termine, avisando el progreso. */
export async function readScore(
  file: File,
  onProgress: (job: JobStatus) => void,
  signal?: AbortSignal,
): Promise<{ musicxml: string; warnings: string[] }> {
  let job = await uploadScore(file)
  onProgress(job)
  while (job.status === 'queued' || job.status === 'running') {
    await new Promise((r) => setTimeout(r, 1500))
    if (signal?.aborted) throw new DOMException('Cancelado', 'AbortError')
    job = await getJob(job.id)
    onProgress(job)
  }
  if (job.status === 'error') throw new Error(job.error ?? 'No se pudo leer la partitura.')
  return { musicxml: await getMusicXml(job.id), warnings: job.warnings }
}
