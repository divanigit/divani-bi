# Divani BI — agents performance dashboard

Mobile-first, auth-gated dashboard over ERP order data.
FastAPI + Supabase. All credentials come from environment variables — none in this repo.

## Deploy (Render)
Web service, python. Build: `pip install -r requirements.txt`.
Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`. Health: `/health`.
Required env vars: `DASH_PASS`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
`PRI_USER`, `PRI_PASS`, `PRI_BASE`, `REFRESH_MINUTES`.

## "ספות בלבד" on the products screen
The category filter has a "ספות בלבד" entry (`fam=__sofas__`). The server unions
every Priority family that is a sofa (`sofa_report.merge_products`, one
`bi_products` call per family, one row per model) and the answer names the
families it counted. Same union from a shell as an Excel file:
`python sofa_report.py --year 2026` (needs `SUPABASE_URL`, `SUPABASE_SECRET_KEY`);
`--list-fams` prints the family split, `--fam-re` / `--exclude-re` change it.
