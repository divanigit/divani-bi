# Divani BI — ביצועי סוכנים

Mobile-first, auth-gated dashboard for Vittorio Divani agents performance,
built directly over Priority ERP (OData) with Supabase as the history store.

## Architecture
- **Priority OData** (`PRI_BASE`) — source of truth, pulled by the server only.
- **Supabase** (`bi_order_lines`, 2014→today) — full history, RLS-locked
  (service key only; anon key sees nothing).
- **This app (Render)** — FastAPI: branded login (signed cookie),
  `/api/meta`, `/api/range` (line-level ≤92 days, agent aggregates beyond),
  `/api/refresh` (manual, rate-limited 1/min), background refresher
  (today+yesterday every `REFRESH_MINUTES`, nightly 120-day resync at ~03:00
  Israel to catch retroactive cancellations/edits).

## Deploy (Render)
1. New → Blueprint → this repo (render.yaml is auto-detected).
2. Fill env vars when prompted (see render.yaml; values are kept locally in
   `divani_bi\secret\render_env_values.txt` on Doron's PC — delete after paste).

## Local dev
`divani_bi\cloud\run_local.ps1` injects secrets from the local DPAPI store
and runs uvicorn on port 8210.

## Related
- Backfill: `divani_bi\cloud\backfill.py` (+ `run_backfill.ps1`) — monthly
  chunks 2014→today, idempotent via `bi_replace_window` RPC.
- Spec: `OneDrive - Divani\DIVANI\מפרט BI\` files 00–11.
- Formula verification vs old Power BI: file 10 + chat log 16-17.7.26
  (margin 54% exact match; sums within snapshot noise).
