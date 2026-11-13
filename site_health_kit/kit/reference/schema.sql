-- Site Health: tables, indexes, privileges.
-- Plain PostgreSQL 15+, no extensions. Safe to run again: nothing here drops or rewrites data.
-- Apply this file first, then functions.sql. Nothing but the sh_* functions touches these tables.

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

-- One availability check. About 1,440 full rounds a day per probe page: 2.3 million rows
-- (some 340 MB, index included) for 4 pages over the 400 days that are kept. The primary key
-- serves every time-window read (rows arrive in time order), so there is no second full-size index.
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
-- 400 days of full rounds.
create index if not exists sh_probe_failed on sh_probe (round_at) where not ok;
create index if not exists sh_probe_light on sh_probe (round_at) where kind = 'light';

-- One lab speed run. About 1,200 a day: half a million rows over 400 days, and up to 700 MB,
-- nearly all of it the opps lists (about 1 KB when a run carries eight of them).
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
create index if not exists sh_speed_at on sh_speed (at);

create table if not exists sh_site_pages (
  url              text primary key,
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now(),
  last_measured_at timestamptz
);

-- One real-user page view. Nothing here may identify a person: no IP, no cookie, no user agent.
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

-- status: the HTTP status of the push once it is final; null while the push is still owed.
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

-- Private tables: row level security without policies shuts out every role but the owner of
-- the tables and roles that bypass it (on Supabase: the service role), and on Supabase the two
-- public API roles lose their default grants as well.
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
  end loop;
end $$;
