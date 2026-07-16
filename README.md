# Divani BI — agents performance dashboard

Mobile-first, auth-gated dashboard over ERP order data.
FastAPI + Supabase. All credentials come from environment variables — none in this repo.

## Deploy (Render)
Web service, python. Build: `pip install -r requirements.txt`.
Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`. Health: `/health`.
Required env vars: `DASH_PASS`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
`PRI_USER`, `PRI_PASS`, `PRI_BASE`, `REFRESH_MINUTES`.
