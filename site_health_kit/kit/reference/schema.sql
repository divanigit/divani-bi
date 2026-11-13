-- Site Health: tables, indexes, privileges.
-- Plain PostgreSQL 15+, no extensions. Safe to run again: nothing here drops or rewrites data.
-- Apply this file first, then functions.sql. Nothing but the sh_* functions touches these tables.
--
-- The file also upgrades a database that an earlier version of it made. "create table if not
-- exists" leaves an existing table as it is, so a column that came after the first version is
-- not in its table's "create table": it is added right below it, with "add column if not exists".

create table if not exists sh_settings (
  key   text primary key,
  value jsonb not null
);

-- The configured pages, replaced as a whole by sh_setup. History in sh_probe / sh_speed
-- carries its own page name and url, so it survives a page leaving the configuration.
create table if not exists sh_pages (
  name     text primary key,
  url      text not null,
  is_probe boolean not null default false,
  is_core  boolean not null default false,
  is_home  boolean not null default false,
  sort     int not null,
  expect   text
);

-- One availability check. About 1,440 full rounds a day per probe page: 576,000 rows
-- (about 100 MB, index included) for 4 pages over the 100 days that are kept by default. The primary
-- key serves every time-window read (rows arrive in time order), so there is no second full-size index.
create table if not exists sh_probe (
  round_at timestamptz not null,
  kind     text not null check (kind in ('full', 'light')),
  page     text not null,
  url      text not null,
  ok       boolean not null,
  status   int,
  ms       int,
  fail     text check (fail in ('timeout', 'http', 'connect', 'content')),
  err      text,
  primary key (round_at, kind, page),
  check (ok = (fail is null)),
  check (fail <> 'http' or status is not null)
);
-- Two small partial indexes. Failed checks are rare, and the drill-downs read only them.
-- Light rounds live for a week, and the nightly cleanup must find the old ones without reading
-- months of full rounds.
create index if not exists sh_probe_failed on sh_probe (round_at) where not ok;
create index if not exists sh_probe_light on sh_probe (round_at) where kind = 'light';

-- One lab speed run: 1.3 KB with its index, most of it the opps list. About 600 runs of core
-- pages a day are kept as long as the probes, and about 580 rotation runs a day for 45 days:
-- some 86,000 rows, about 110 MB.
-- The primary key makes a repeated insert harmless and serves "the runs of one page".
create table if not exists sh_speed (
  at            timestamptz not null default now(),
  url           text not null,
  page          text,
  strategy      text not null check (strategy in ('mobile', 'desktop')),
  source        text not null check (source in ('core', 'rotation')),
  ok            boolean not null,
  err           text,
  score         int,
  lcp_ms        int,
  cls           numeric(6, 3),
  ttfb_ms       int,
  bytes         bigint,
  crux_category text,
  crux_lcp_ms   int,
  opps          jsonb,
  primary key (url, strategy, at)
);
-- the Lighthouse version that measured, for explaining a sudden change in the numbers
alter table sh_speed add column if not exists lh_version text;
create index if not exists sh_speed_at on sh_speed (at);

create table if not exists sh_site_pages (
  url              text primary key,
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now(),
  last_measured_at timestamptz
);

-- One real-user page view. Measured on Postgres 16 with its index: about 120 bytes for a path of
-- 40 characters, and at most 296 (a site name of 100 characters, a path of 120). No IP, no
-- cookie and no user agent are stored, and no query string; the path is cut at 120 characters,
-- and the ingest drops a path that looks as if it carries an e-mail address or a token (spec
-- §7.7). sh_rum_add stops storing once the last 24 hours hold 30,000 rows, so a flood of forged
-- views cannot fill the database.
create table if not exists sh_rum (
  created_at timestamptz not null default now(),
  site       text not null,
  path       text not null,
  lcp_ms     int not null,
  is_test    boolean not null default false
);
create index if not exists sh_rum_created_at on sh_rum (created_at);

-- The certificate fields hold the last successful check; ok / err / checked_at the last check.
create table if not exists sh_cert (
  host       text primary key,
  issuer     text,
  not_before timestamptz,
  not_after  timestamptz,
  days_left  int,
  ok         boolean not null,
  err        text,
  checked_at timestamptz not null
);

create table if not exists sh_product_issues (
  snap_date  date not null,
  product_id text not null,
  issue      text not null,
  name       text,
  url        text,
  primary key (snap_date, product_id, issue)
);

-- kind is free text: other parts of the owner's system may add their own alert kinds.
create table if not exists sh_alerts (
  id        bigint generated always as identity primary key,
  key       text not null,
  kind      text not null,
  title     text not null,
  body      text,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  acked_at  timestamptz,
  acked_by  text
);
-- At most one open alert per key. Partial, so it cannot be the target of an upsert over REST:
-- sh_alerts_check looks for an open row and inserts when there is none.
create unique index if not exists sh_alerts_open_key on sh_alerts (key) where closed_at is null;

-- status: the HTTP status of the push once it is final (0: pushing is not configured); null
-- while the push is still owed. attempts: how many sends were tried.
create table if not exists sh_messages (
  id       bigint generated always as identity primary key,
  at       timestamptz not null default now(),
  alert_id bigint references sh_alerts (id),
  event    text not null,
  kind     text not null,
  title    text not null,
  msg      text,
  priority int not null default 3,
  click    text,
  status   int,
  attempts int not null default 0
);
-- when sh_alerts_check last handed the push to a sender; for two minutes no other sender gets it
alter table sh_messages add column if not exists claimed_at timestamptz;
create index if not exists sh_messages_at on sh_messages (at);

create table if not exists sh_flows (
  flow_name    text primary key,
  sort         int not null,
  cadence      text not null,
  warn_minutes int not null,
  late_minutes int not null,
  note         text,
  enabled      boolean not null default true,
  last_at      timestamptz
);
-- alerts: whether the flow's silence opens an alert. sh_setup seeds it and never changes it again.
do $$
declare
  v_new boolean := not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'sh_flows' and column_name = 'alerts');
begin
  alter table sh_flows add column if not exists alerts boolean not null default true;
  -- The flag came with a new rule for the real-user flow: its silence opens no alert, and it
  -- counts as late after 6 hours and as silent after 24. sh_setup seeds a new flow that way and
  -- leaves the flag of an existing one alone, so the flow of a database from before the flag is
  -- brought in line here, once.
  if v_new then
    update sh_flows set alerts = false, warn_minutes = 360, late_minutes = 1440
    where flow_name = 'מהירות אצל לקוחות';
  end if;
end $$;

create table if not exists sh_jobs (
  job text not null,
  day date not null,
  primary key (job, day)
);

create table if not exists sh_login_log (
  at  timestamptz not null default now(),
  ip  text,
  ok  boolean not null,
  who text,
  ua  text
);

-- ---------------------------------------------------------------- privileges
-- Private tables. Row level security without policies shuts out every role but the owner of the
-- tables and roles that bypass it (on Supabase: the service role), and on Supabase the two public
-- API roles lose what the platform's default privileges gave them, the identity sequences included.
-- The service role (the secret key the server and the collectors use) is granted the tables by
-- name: a Supabase project does not always hand out table grants on its own, and without this
-- grant every sh_* function fails with "permission denied" on the first table it touches.
-- sh_deadman_push (deadman.sql) is left to its owner: only the database's own job uses it.
do $$
declare
  t text;
  r text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' and tablename like 'sh\_%' loop
    execute format('alter table public.%I enable row level security', t);
    foreach r in array array['anon', 'authenticated'] loop
      if exists (select 1 from pg_roles where rolname = r) then
        execute format('revoke all on table public.%I from %I', t, r);
      end if;
    end loop;
    if t <> 'sh_deadman_push' and exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant select, insert, update, delete on table public.%I to service_role', t);
    end if;
  end loop;
  for t in select sequencename from pg_sequences where schemaname = 'public' and sequencename like 'sh\_%' loop
    foreach r in array array['anon', 'authenticated'] loop
      if exists (select 1 from pg_roles where rolname = r) then
        execute format('revoke all on sequence public.%I from %I', t, r);
      end if;
    end loop;
  end loop;
end $$;
