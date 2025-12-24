# CareerOS (Initial Skeleton)

A minimal **Next.js + FastAPI** starter that matches the CareerOS direction (Applications / Documents / Assistant).

## Prereqs (Windows)
- Node.js LTS
- Python 3.11+

## Run API (FastAPI)
```powershell
cd CareerOS\api
py -m pip install -r requirements.txt
py -m uvicorn main:app --reload --port 8000
```

Open:
- http://localhost:8000/health
- http://localhost:8000/docs

## Run Web (Next.js)
```powershell
cd CareerOS\web
npm install
npm run dev
```

Open:
- http://localhost:3000

## Next steps
- Implement real persistence (SQLite/Postgres) for applications/documents/tasks
- Add OpenAI calls in `api/app/assistant/service.py`
