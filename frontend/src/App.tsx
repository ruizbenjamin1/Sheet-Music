import { useEffect, useState } from 'react'
import { getHealth } from './lib/api'

type Backend = { state: 'checking' } | { state: 'ok'; engine: string } | { state: 'down'; error: string }

// Etapa 0: pantalla mínima que confirma que el frontend arranca y que se
// conecta con el backend. La pantalla real (subir, ver y tocar) es la Etapa 1.
export default function App() {
  const [backend, setBackend] = useState<Backend>({ state: 'checking' })

  useEffect(() => {
    getHealth()
      .then((h) => setBackend({ state: 'ok', engine: h.engine }))
      .catch((e: Error) => setBackend({ state: 'down', error: e.message }))
  }, [])

  return (
    <main className="shell">
      <h1>Partituras</h1>
      <p className="lead">Subí una partitura, mirala y escuchala. En construcción.</p>
      <section className="card" aria-live="polite">
        <h2>Estado</h2>
        <ul className="status">
          <li className="ok">App web funcionando</li>
          {backend.state === 'checking' && <li>Buscando el servidor de lectura…</li>}
          {backend.state === 'ok' && <li className="ok">Servidor de lectura conectado (motor: {backend.engine})</li>}
          {backend.state === 'down' && <li className="bad">{backend.error}</li>}
        </ul>
      </section>
    </main>
  )
}
