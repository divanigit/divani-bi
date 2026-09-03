# Divani BI — agents performance dashboard

Mobile-first, auth-gated dashboard over ERP order data.
FastAPI + Supabase. All credentials come from environment variables — none in this repo.

## Deploy (Render)
Web service, python. Build: `pip install -r requirements.txt`.
Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`. Health: `/health`.
Required env vars: `DASH_PASS`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
`PRI_USER`, `PRI_PASS`, `PRI_BASE`, `REFRESH_MINUTES`.

## Sofa models report (Excel)
`GET /api/sofas.xlsx?year=2026` (logged in) — one row per sofa model, sorted by
paid units, built from the same `bi_products` query as the products screen.
Second sheet lists which Priority families were counted as sofas.
Same file from a shell: `python sofa_report.py --year 2026` (needs `SUPABASE_URL`,
`SUPABASE_SECRET_KEY`); `--list-fams` prints the family split, `--fam-re` /
`--exclude-re` change it.
