# Partituras

Web app (PWA) que lee partituras de piano desde un PDF o una foto, las muestra y las toca.

Estado y próximas tareas: [`TAREAS.md`](TAREAS.md). Reglas y forma de trabajo: [`CLAUDE.md`](CLAUDE.md).

## Requisitos

- Node.js 20.19 o más nuevo (o 22.12+)
- Python 3.12

## Primera vez

En PowerShell, desde la carpeta del proyecto:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
cd ..\frontend
npm install
```

## Levantar la app

Hacen falta dos terminales.

Terminal 1, el servidor de lectura:

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Terminal 2, la app web:

```powershell
cd frontend
npm run dev
```

Abrí http://localhost:5173. Si dice "Servidor de lectura conectado", está todo bien.

## Pruebas

Ver [`docs/pruebas.md`](docs/pruebas.md).
