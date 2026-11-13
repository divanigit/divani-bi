-- Site Health: every sh_* function. Apply after schema.sql. Safe to run again.
--
-- Conventions
--   * The server and the collectors call these functions and nothing else. Each returns jsonb;
--     a list is never null (an empty list is '[]'). The helpers at the top are for the other
--     functions (and for deadman.sql), not for callers.
--   * Parameters are named p_*. Lists of rows and of ids arrive as jsonb and times as
--     timestamptz, so one call works over PostgREST (/rest/v1/rpc/<fn>) and over a connection.
--   * now() is the start of the transaction: all figures of one call are taken at one instant.
--   * Local time (every *_il string, every bucket, every day boundary) is the time zone stored
--     in sh_settings under 'time_zone'.

-- ---------------------------------------------------------------- helpers

create or replace function sh_tz() returns text
language sql stable set search_path = public as $$
  select coalesce((select value #>> '{}' from sh_settings where key = 'time_zone'), 'UTC')
$$;

-- A moment as the screen prints it: local time, DD.MM HH:MM.
create or replace function sh_il(p_at timestamptz) returns text
language sql stable set search_path = public as $$
  select to_char(p_at at time zone sh_tz(), 'DD.MM HH24:MI')
$$;

-- The to_char format of a bucket. The screen tells the two apart by their length.
create or replace function sh_bucket_fmt(p_hourly boolean) returns text
language sql immutable set search_path = public as $$
  select case when p_hourly then 'YYYY-MM-DD HH24:00' else 'YYYY-MM-DD' end
$$;

-- Why a check failed, in the words of the failures sheet and of the alert body.
create or replace function sh_fail_kind(p_fail text, p_status int) returns text
language sql immutable set search_path = public as $$
  select case p_fail
           when 'timeout' then 'לא ענה בזמן'
           when 'http'    then 'קוד ' || p_status
           when 'connect' then 'שגיאת חיבור'
           when 'content' then 'תוכן לא צפוי'
         end
$$;

-- A length of time as a person says it, for every text that names one: rounded to the nearest
-- minute and never less than one; minutes under two hours, whole hours under two days, whole
-- days from there on. One and two get their own words: דקה, שתי דקות, 5 דקות; שעה (exactly 60
-- minutes), שעתיים, 5 שעות; יום (exactly 24 hours), יומיים, 5 ימים.
create or replace function sh_span(p_minutes numeric) returns text
language sql immutable set search_path = public as $$
  select case when m = 1    then 'דקה'
              when m = 2    then 'שתי דקות'
              when m = 60   then 'שעה'
              when m < 120  then m || ' דקות'
              when m < 180  then 'שעתיים'
              when m = 1440 then 'יום'
              when m < 2880 then m / 60 || ' שעות'
              when m < 4320 then 'יומיים'
              else m / 1440 || ' ימים'
         end
  from (select greatest(round(p_minutes), 1)::bigint as m) x
$$;

-- How long something lasted, in whole minutes: the nearest minute, and never 0. An alert opens
-- and closes at the alert tick, a few milliseconds after the minute, so three rounds are
-- 2:59.99 or 3:00.01 long, and both are three minutes.
create or replace function sh_minutes(p_from timestamptz, p_to timestamptz) returns int
language sql immutable set search_path = public as $$
  select greatest(round(extract(epoch from p_to - p_from) / 60), 1)::int
$$;

-- A page address in the one spelling every comparison uses: scheme and host in lower case, a
-- bare host with its "/", and the rest percent-encoded (UTF-8, capital hex digits). The site's
-- sitemap lists a Hebrew slug as %d7%a2…, a person types it in Hebrew, and both must be the
-- same page: sh_setup and sh_sitemap_set store what this returns. Null for anything that is not
-- an absolute address.
create or replace function sh_url(p_url text) returns text
language sql immutable set search_path = public as $$
  select lower(u[1]) || case when u[2] ~ '^[?#]' then '/' else '' end
         || case when u[2] ~ '^[!-$&-~]+$' then u[2]                      -- nothing to encode: most addresses
                 else coalesce((
                   select string_agg(
                            case when t[1] is not null then upper(t[1])   -- an escape that is already there
                                 when t[2] is not null then t[2]          -- plain characters
                                 when t[3] = '%' then '%'                 -- a stray percent sign stays
                                 else (select string_agg('%' || upper(lpad(to_hex(get_byte(b, i)), 2, '0')), '' order by i)
                                       from (select convert_to(t[3], 'UTF8') as b) c, generate_series(0, length(b) - 1) i)
                            end, '' order by n)
                   from regexp_matches(u[2], '(%[0-9A-Fa-f]{2})|([!-$&-~]+)|(.)', 'g') with ordinality as r(t, n)), '/')
            end
  from regexp_match(btrim(p_url), '^([A-Za-z][A-Za-z0-9+.-]*://[^/?#\s]+)(.*)$') u
$$;

-- The parts of the measuring that are switched off: what the configuration lists under "off",
-- plus what follows from the site itself. Platform "other" has no catalogue to read, and an
-- http:// site has no certificate. Always in the same order.
create or replace function sh_off(p_off jsonb, p_platform text, p_site text) returns jsonb
language sql immutable set search_path = public as $$
  select coalesce(jsonb_agg(part order by n), '[]')
  from unnest(array['sitemap', 'real_users', 'catalogue', 'cert']) with ordinality as x(part, n)
  where coalesce(p_off, '[]') ? part
     or (part = 'catalogue' and p_platform = 'other')
     or (part = 'cert' and p_site ilike 'http://%')
$$;

-- The LCP thresholds, the same ones the screen colors by.
create or replace function sh_verdict(p_lcp_ms int) returns text
language sql immutable set search_path = public as $$
  select case when p_lcp_ms <= 2000 then 'מצוין'
              when p_lcp_ms <= 2500 then 'מהיר'
              when p_lcp_ms <= 4000 then 'בינוני'
              when p_lcp_ms >  4000 then 'איטי'
         end
$$;

-- An alert as the alerts card and the alert sheet show it.
create or replace function sh_alert_row(p_alert sh_alerts) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'id', p_alert.id, 'kind', p_alert.kind, 'title', p_alert.title, 'body', p_alert.body,
    'open', p_alert.closed_at is null,
    'opened_il', sh_il(p_alert.opened_at), 'closed_il', sh_il(p_alert.closed_at),
    'minutes', sh_minutes(p_alert.opened_at, coalesce(p_alert.closed_at, now())))
$$;

-- ---------------------------------------------------------------- configuration

-- The configuration as it was loaded (the keys of site_health.config.json, defaults filled in),
-- the pages in their order, and "screen": the values the server injects into SH_CONFIG.
create or replace function sh_config() returns jsonb
language sql stable set search_path = public as $$
  with s as (
    select coalesce(jsonb_object_agg(key, value), '{}') as v from sh_settings
  ), p as (
    select coalesce(jsonb_agg(jsonb_build_object(
             'name', name, 'url', url, 'probe', is_probe, 'core', is_core, 'home', is_home, 'expect', expect)
             order by sort), '[]') as v,
           count(*) filter (where is_probe) as probes,
           count(*) filter (where is_core) as cores,
           max(name) filter (where is_home) as home
    from sh_pages
  ), o as (
    -- worked out here as well as in sh_setup: a database that was set up before "off" existed
    -- still knows that a site without a catalogue has no catalogue check
    select sh_off(s.v -> 'off', s.v ->> 'platform', s.v ->> 'site') as off from s
  )
  -- The settings that arrived after the first version come first, with their defaults: a
  -- database that was set up before them answers with these until sh_setup runs again.
  select jsonb_build_object('keep_days', 100, 'rum_hosts', '[]'::jsonb, 'private_paths', '[]'::jsonb,
                            'extra_hosts', '[]'::jsonb, 'hide', '[]'::jsonb, 'nav', '[]'::jsonb, 'links', '[]'::jsonb)
    || s.v || jsonb_build_object(
    'off', o.off,
    'pages', p.v,
    -- a key that is not configured is left out, so the screen keeps its own default
    'screen', jsonb_strip_nulls(jsonb_build_object(
      'siteLabel', s.v -> 'label', 'brand', s.v -> 'brand', 'homePage', p.home,
      'probeCount', p.probes, 'coreCount', p.cores, 'downAfter', s.v -> 'down_after',
      'liveHosts', s.v -> 'live_hosts', 'pathLabels', s.v -> 'path_labels', 'bucketNote', s.v -> 'bucket_note',
      'nav', s.v -> 'nav', 'links', s.v -> 'links',
      -- the cards the configuration hides, then the card of each part that is switched off
      'hide', (select coalesce(jsonb_agg(card order by n), '[]')
               from (select card, min(n) as n
                     from (select h.card, h.n
                           from jsonb_array_elements_text(coalesce(s.v -> 'hide', '[]')) with ordinality as h(card, n)
                           union all
                           select c.card, 1000 + c.n
                           from (values (1, 'sitemap', 'slowCard'), (2, 'catalogue', 'issuesCard'),
                                        (3, 'cert', 'certCard')) as c(n, part, card)
                           where o.off ? c.part) listed
                     group by card) cards))))
  from s, p, o
$$;

-- Loads site_health.config.json (spec §7.4 lists its keys). Running it again with the same file
-- changes nothing; a page that left the file is no longer probed or measured, and its history
-- stays. A file that is refused changes nothing at all.
create or replace function sh_setup(p_config jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_site       text := rtrim(p_config ->> 'site', '/');
  v_host       text := lower(substring(v_site from '^https?://([^/:\s]+)'));
  v_zone       text := p_config ->> 'time_zone';
  v_platform   text := coalesce(p_config ->> 'platform', 'other');
  v_down_after int  := coalesce((p_config ->> 'down_after')::int, 1);
  v_morning    text := coalesce(p_config ->> 'morning', '07:30');
  v_keep_days  text := coalesce(p_config ->> 'keep_days', '100');
  v_rum_hosts  jsonb := coalesce(p_config -> 'rum_hosts', '[]');
  v_private    jsonb := coalesce(p_config -> 'private_paths', '[]');
  v_extra      jsonb := coalesce(p_config -> 'extra_hosts', '[]');
  v_off        jsonb := coalesce(p_config -> 'off', '[]');
  v_hide       jsonb := coalesce(p_config -> 'hide', '[]');
  v_nav        jsonb := coalesce(p_config -> 'nav', '[]');
  v_links      jsonb := coalesce(p_config -> 'links', '[]');
  v_live       jsonb := coalesce(p_config -> 'live_hosts', '["live"]');
  v_labels     jsonb := coalesce(p_config -> 'path_labels', case v_platform
                          when 'woocommerce' then '[["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]'
                          when 'shopify'     then '[["/collections/", "קטגוריה: "], ["/products/", "מוצר: "]]'
                          else '[]' end::jsonb);
  v_pages int; v_named int; v_names int; v_homes int; v_probes int; v_home_probes int; v_home_cores int;
  v_bad_urls text;
begin
  if v_host is null then
    raise exception 'sh_setup: "site" must be an absolute http(s) address, got %', coalesce(p_config ->> 'site', 'nothing');
  end if;
  -- no default: every time on the screen and every daily job would silently run on UTC
  if coalesce(v_zone, '') = '' then
    raise exception 'sh_setup: "time_zone" is required: the time zone of the site''s customers, such as Asia/Jerusalem';
  end if;
  if not exists (select 1 from pg_timezone_names where name = v_zone) then
    raise exception 'sh_setup: unknown "time_zone" %', v_zone;
  end if;
  if v_platform not in ('woocommerce', 'shopify', 'other') then
    raise exception 'sh_setup: "platform" must be woocommerce, shopify or other, got %', v_platform;
  end if;
  if v_down_after < 1 then
    raise exception 'sh_setup: "down_after" must be 1 or more, got %', v_down_after;
  end if;
  if v_morning !~ '^([01]\d|2[0-3]):[0-5]\d$' then
    raise exception 'sh_setup: "morning" must be a time such as 07:30, got %', v_morning;
  end if;
  if jsonb_typeof(v_live) <> 'array' or jsonb_typeof(v_labels) <> 'array' then
    raise exception 'sh_setup: "live_hosts" and "path_labels" must be lists';
  end if;
  -- 30 to 400: no less than the screen's "30 יום", no more than its widest window (spec §5.1)
  if v_keep_days !~ '^([3-9]\d|[1-3]\d\d|400)$' then
    raise exception 'sh_setup: "keep_days" must be a whole number of days from 30 to 400, got %', v_keep_days;
  end if;
  if jsonb_typeof(v_rum_hosts) <> 'array' or jsonb_typeof(v_private) <> 'array' then
    raise exception 'sh_setup: "rum_hosts" and "private_paths" must be lists';
  end if;
  if exists (select 1 from jsonb_array_elements(v_rum_hosts) h
             where jsonb_typeof(h) <> 'string' or h #>> '{}' !~ '^[a-z0-9.-]+$') then
    raise exception 'sh_setup: "rum_hosts" takes host names in lower case, such as staging.example.co.il, got %', v_rum_hosts;
  end if;
  if exists (select 1 from jsonb_array_elements(v_private) s
             where jsonb_typeof(s) <> 'string' or s #>> '{}' !~ '^[^/?#[:space:]]+$') then
    raise exception 'sh_setup: "private_paths" takes single path segments, such as checkout or its translated slug, got %', v_private;
  end if;
  if jsonb_typeof(v_extra) <> 'array' or jsonb_typeof(v_off) <> 'array' or jsonb_typeof(v_hide) <> 'array'
     or jsonb_typeof(v_nav) <> 'array' or jsonb_typeof(v_links) <> 'array' then
    raise exception 'sh_setup: "extra_hosts", "off", "hide", "nav" and "links" must be lists';
  end if;
  if exists (select 1 from jsonb_array_elements(v_extra) h
             where jsonb_typeof(h) <> 'string' or h #>> '{}' !~ '^[a-z0-9.-]+$') then
    raise exception 'sh_setup: "extra_hosts" takes host names in lower case, such as shop.example.co.il, got %', v_extra;
  end if;
  if exists (select 1 from jsonb_array_elements(v_off) part
             where jsonb_typeof(part) <> 'string'
                or part #>> '{}' not in ('sitemap', 'real_users', 'catalogue', 'cert')) then
    raise exception 'sh_setup: "off" takes sitemap, real_users, catalogue or cert, got %', v_off;
  end if;
  if exists (select 1 from jsonb_array_elements(v_hide) card where jsonb_typeof(card) <> 'string') then
    raise exception 'sh_setup: "hide" takes the ids of cards of the screen, such as slowCard, got %', v_hide;
  end if;
  if jsonb_typeof(p_config -> 'pages') is distinct from 'array' then
    raise exception 'sh_setup: "pages" must be a list of pages';
  end if;

  select count(*), count(*) filter (where name <> ''), count(distinct name),
         count(*) filter (where home), count(*) filter (where probe), count(*) filter (where home and probe),
         count(*) filter (where home and core),
         string_agg(name, ', ') filter (where url is null or url !~ '^https?://[^/\s]+')
    into v_pages, v_named, v_names, v_homes, v_probes, v_home_probes, v_home_cores, v_bad_urls
  from (select page ->> 'name' as name, page ->> 'url' as url,
               coalesce((page ->> 'probe')::boolean, false) as probe,
               coalesce((page ->> 'core')::boolean, false) as core,
               coalesce((page ->> 'home')::boolean, false) as home
        from jsonb_array_elements(p_config -> 'pages') as page) p;
  if v_named < v_pages then
    raise exception 'sh_setup: every page needs a "name"';
  end if;
  if v_names < v_pages then
    raise exception 'sh_setup: page names must be unique';
  end if;
  if v_bad_urls is not null then
    raise exception 'sh_setup: the "url" of a page must be an absolute http(s) address: %', v_bad_urls;
  end if;
  if v_homes <> 1 then
    raise exception 'sh_setup: exactly one page must have "home": true, found %', v_homes;
  end if;
  if v_probes < 1 then
    raise exception 'sh_setup: at least one page must have "probe": true';
  end if;
  if v_home_probes < 1 then
    raise exception 'sh_setup: the home page must be a probe page';
  end if;
  -- the screen's bottom line and the "slow" alert of the home page read its core runs
  if v_home_cores < 1 then
    raise exception 'sh_setup: the home page must be a core page';
  end if;

  -- what is off: the file's own list, and what follows from the platform and from the address
  v_off := sh_off(v_off, v_platform, v_site);

  insert into sh_settings (key, value)
  select key, value from jsonb_each(jsonb_build_object(
    'site', v_site, 'host', v_host,
    'label', coalesce(p_config ->> 'label', regexp_replace(v_host, '^www\.', '')),
    'brand', coalesce(p_config ->> 'brand', ''),
    'time_zone', v_zone, 'platform', v_platform, 'down_after', v_down_after, 'morning', v_morning,
    'keep_days', v_keep_days::int, 'rum_hosts', v_rum_hosts, 'private_paths', v_private,
    'extra_hosts', v_extra, 'off', v_off, 'hide', v_hide, 'nav', v_nav, 'links', v_links,
    'live_hosts', v_live, 'path_labels', v_labels,
    'bucket_note', coalesce(p_config ->> 'bucket_note', '')))
  on conflict (key) do update set value = excluded.value;

  -- Addresses are stored in the one spelling of sh_url, so a core page is the same page as its
  -- line in the sitemap however the file spells it (Hebrew or %D7…, with or without the "/").
  delete from sh_pages;
  insert into sh_pages (name, url, is_probe, is_core, is_home, sort, expect)
  select page ->> 'name', sh_url(page ->> 'url'),
         coalesce((page ->> 'probe')::boolean, false), coalesce((page ->> 'core')::boolean, false),
         coalesce((page ->> 'home')::boolean, false), sort, nullif(page ->> 'expect', '')
  from jsonb_array_elements(p_config -> 'pages') with ordinality as p(page, sort);

  -- The measurement flows of the screen's last card. Which of them are enabled is worked out
  -- from the configuration on every call, so a flow is never switched by hand: a part of the
  -- measuring that does not apply to this site goes into "off". A flow that is switched off
  -- forgets its last run: switched on again it starts from "אין נתון", not from an old silence.
  -- note is never touched here, and alerts only when the flow is new: whoever turns a flow's
  -- alert on or off by hand keeps that choice. The real-user flow starts without one: a small
  -- site has no visitors for hours every night, and that is not a fault.
  insert into sh_flows (flow_name, sort, cadence, warn_minutes, late_minutes, enabled, alerts) values
    ('בודק זמינות האתר',           1, 'כל דקה',          5,    15,   true,                     true),
    ('מדידת מהירות — עמודי ליבה',   2, 'כל רבע שעה',      45,   90,   true,                     true),
    ('מדידת מהירות — סבב כל האתר',  3, 'כל 5 דקות',       20,   60,   not v_off ? 'sitemap',    true),
    ('טעינת מפת האתר',             4, 'פעם ביום',        1560, 2880, not v_off ? 'sitemap',    true),
    ('בדיקת תעודת האבטחה',         5, 'פעם ביום',        1560, 2880, not v_off ? 'cert',       true),
    ('בדיקת מוצרים שבורים',        6, 'פעם ביום',        1560, 2880, not v_off ? 'catalogue',  true),
    ('מהירות אצל לקוחות',          7, 'כל צפייה בעמוד',  360,  1440, not v_off ? 'real_users', false)
  on conflict (flow_name) do update
    set sort = excluded.sort, cadence = excluded.cadence, warn_minutes = excluded.warn_minutes,
        late_minutes = excluded.late_minutes, enabled = excluded.enabled,
        last_at = case when excluded.enabled then sh_flows.last_at end;

  return sh_config();
end $$;

-- ---------------------------------------------------------------- read side: /api/site

-- Per page over the full rounds of the window, then the outages.
create or replace function sh_availability(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  with per_page as (
    select page, count(*) as checks, count(*) filter (where not ok) as failed,
           percentile_cont(array[0.5, 0.95]) within group (order by ms) filter (where ok) as pct,
           max(round_at) filter (where not ok) as last_fail
    from sh_probe
    where kind = 'full' and round_at >= p_from and round_at < p_to
    group by page
  ), rounds as (
    -- a round is dead when none of its pages answered
    select round_at, bool_or(ok) as alive
    from sh_probe
    where kind = 'full' and round_at >= p_from and round_at < p_to
    group by round_at
  ), numbered as (
    -- dead rounds with no answering round between them share a run number
    select round_at, alive,
           count(*) filter (where alive) over (order by round_at) as run,
           lead(round_at) over (order by round_at) as next_at
    from rounds
  ), outages as (
    select min(round_at) as start_at, count(*) as minutes,
           -- it ends at the round after the last dead one; a run that reaches the end of the
           -- window has none, and ends where the window does (which is now for a live window)
           case when count(next_at) = count(*) then max(next_at) else least(p_to, now()) end as end_at
    from numbered
    where not alive
    group by run
    having count(*) >= 3
  )
  select coalesce((
           select jsonb_agg(jsonb_build_object(
                    'section', 'לפי עמוד', 'page', a.page, 'checks', a.checks, 'failed', a.failed,
                    'fail_pct', round(100.0 * a.failed / a.checks, 2)::text,
                    'p50_ms', round(a.pct[1]::numeric)::int, 'p95_ms', round(a.pct[2]::numeric)::int,
                    'last_fail_il', sh_il(a.last_fail))
                    -- the order of the configuration; a page that left it keeps its history, last
                    order by p.sort nulls last, a.page)
           from per_page a left join sh_pages p on p.name = a.page), '[]')
      || coalesce((
           select jsonb_agg(jsonb_build_object(
                    'section', 'נפילות', 'outage_minutes', minutes,
                    'outage_start_il', sh_il(start_at), 'outage_end_il', sh_il(end_at))
                    order by start_at)
           from outages), '[]')
$$;

-- One row per hour (windows of up to 72 whole hours) or per day, all pages together.
create or replace function sh_availability_series(p_from timestamptz, p_to timestamptz) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  -- hourly up to 72 whole hours: "h=72" arrives as 72 hours and a minute (to = now + 1 minute)
  v_fmt text := sh_bucket_fmt(p_to - p_from < interval '73 hours');
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'bucket', bucket, 'checks', checks, 'failed', failed,
             'ms_p50', round(pct[1]::numeric)::int, 'ms_p95', round(pct[2]::numeric)::int)
             order by bucket), '[]')
    from (
      select to_char(round_at at time zone v_tz, v_fmt) as bucket,
             count(*) as checks, count(*) filter (where not ok) as failed,
             percentile_cont(array[0.5, 0.95]) within group (order by ms) filter (where ok) as pct
      from sh_probe
      where kind = 'full' and round_at >= p_from and round_at < p_to
      group by 1
    ) b);
end $$;

-- The four sections of the speed answer, over the successful runs of the window.
create or replace function sh_speed(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  with runs as materialized (
    select url, strategy, source, at, lcp_ms, score, cls, ttfb_ms, crux_category, crux_lcp_ms
    from sh_speed
    where ok and at >= p_from and at < p_to
  ), core as (
    select p.name as page, p.url, p.sort, r.strategy,
           percentile_cont(array[0.5, 0.95]) within group (order by r.lcp_ms) as lcp,
           percentile_cont(0.5) within group (order by r.score) as score,
           percentile_cont(0.5) within group (order by r.cls) as cls,
           percentile_cont(0.5) within group (order by r.ttfb_ms) as ttfb,
           count(*) filter (where r.lcp_ms > 4000) as slow_runs, count(*) as checks,
           (array_agg(r.crux_category order by r.at desc))[1] as crux_category,
           (array_agg(r.crux_lcp_ms order by r.at desc))[1] as crux_lcp
    from sh_pages p join runs r on r.url = p.url
    where p.is_core and r.source = 'core'
    group by p.name, p.url, p.sort, r.strategy
  ), rotation as (
    -- The whole-site rotation is about every page of the site except the core pages, which are
    -- measured every 15 minutes already. A core page is told by its address: sh_setup and
    -- sh_sitemap_set both store addresses in the spelling of sh_url.
    select url, strategy, at, lcp_ms, score
    from runs
    where source = 'rotation' and url not in (select url from sh_pages where is_core)
  ), heavy as (
    select url, percentile_cont(0.5) within group (order by lcp_ms) as lcp,
           percentile_cont(0.5) within group (order by score) as score,
           count(*) as checks, max(at) as last_at
    from rotation
    where strategy = 'mobile' and lcp_ms is not null
    group by url
    order by lcp desc, url
    limit 10
  ), site_pages as (
    select url from sh_site_pages
    where active and url not in (select url from sh_pages where is_core)
  )
  select
    -- the bottom line: the home page on a phone; the row exists even before the first run
    coalesce((
      select jsonb_agg(jsonb_build_object(
               'section', 'שורה תחתונה', 'page', h.name, 'url', h.url,
               'lcp_p50', round(c.lcp[1]::numeric)::int, 'checks', coalesce(c.checks, 0),
               'verdict', sh_verdict(round(c.lcp[1]::numeric)::int)))
      from sh_pages h left join core c on c.page = h.name and c.strategy = 'mobile'
      where h.is_home), '[]')
    || coalesce((
      select jsonb_agg(jsonb_build_object(
               'section', 'ליבה', 'strategy', strategy, 'page', page, 'url', url,
               'lcp_p50', round(lcp[1]::numeric)::int, 'lcp_p95', round(lcp[2]::numeric)::int,
               'score_med', round(score::numeric)::int, 'cls_med', round(cls::numeric, 3),
               'ttfb_p50', round(ttfb::numeric)::int, 'slow_runs', slow_runs, 'checks', checks,
               'crux_category', crux_category, 'crux_lcp', crux_lcp)
               order by strategy desc, sort)   -- phone first
      from core), '[]')
    || coalesce((
      select jsonb_agg(jsonb_build_object(
               'section', 'האיטיים באתר', 'page', url, 'url', url,
               'lcp_p50', round(lcp::numeric)::int, 'score_med', round(score::numeric)::int,
               'checks', checks, 'last_il', sh_il(last_at))
               order by lcp desc, url)
      from heavy), '[]')
    -- coverage, in the column names the screen reads: checks = pages of today's sitemap that the
    -- rotation measured in the window, slow_runs = pages of today's sitemap that it takes turns on
    || jsonb_build_object(
         'section', 'כיסוי',
         'checks', (select count(distinct r.url) from rotation r join site_pages s on s.url = r.url),
         'slow_runs', (select count(*) from site_pages))
$$;

-- Median LCP per core page per bucket, for one strategy.
create or replace function sh_speed_series(p_from timestamptz, p_to timestamptz, p_strategy text) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  v_fmt text := sh_bucket_fmt(p_to - p_from < interval '73 hours');
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'page', page, 'url', url, 'bucket', bucket, 'lcp_p50', round(lcp::numeric)::int)
             order by sort, bucket), '[]')
    from (
      select p.name as page, p.url, p.sort, to_char(s.at at time zone v_tz, v_fmt) as bucket,
             percentile_cont(0.5) within group (order by s.lcp_ms) as lcp
      from sh_pages p join sh_speed s on s.url = p.url
      where p.is_core and s.source = 'core' and s.strategy = p_strategy and s.ok
        and s.at >= p_from and s.at < p_to
      group by p.name, p.url, p.sort, 4
    ) b);
end $$;

create or replace function sh_alerts_open() returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', id, 'kind', kind, 'title', title, 'body', body,
           'opened_il', sh_il(opened_at), 'acked', acked_at is not null)
           order by opened_at desc, id desc), '[]')
  from sh_alerts
  where closed_at is null
$$;

-- Alerts that were open at any time inside the window.
create or replace function sh_alerts_range(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(sh_alert_row(a) order by a.opened_at desc, a.id desc), '[]')
  from sh_alerts a
  where a.opened_at < p_to and (a.closed_at is null or a.closed_at >= p_from)
$$;

-- The state of each measurement flow, by the age of its last successful run.
create or replace function sh_health() returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'flow_name', flow_name,
           'status', case when age is null then 'אין נתון'
                          when age <= warn_minutes then 'תקין'
                          when age <= late_minutes then 'מתעכב'
                          else 'שקט' end,
           'cadence', cadence,
           'silent_txt', case when age > late_minutes then 'שקט כבר ' || sh_span(floor(age))
                              -- "ב-10 דקות" before a number; "בדקה", "בשעתיים" before a word
                              when age > warn_minutes
                              then 'מאחר ב' || regexp_replace(sh_span(ceil(age - warn_minutes)), '^(\d)', '-\1') end,
           'last_at', last_at, 'warn_minutes', warn_minutes, 'late_minutes', late_minutes, 'note', note)
           order by sort), '[]')
  from (select *, extract(epoch from now() - last_at) / 60 as age from sh_flows where enabled) f
$$;

-- The broken products of the latest snapshot. sh_issues_set records the day of every snapshot,
-- so a snapshot without broken products empties the list.
-- The order: the real faults first and "לא במלאי" last, because the screen shows the first 60;
-- then by issue and by name. collate "C" is plain character order, the same on every database.
create or replace function sh_product_issues() returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'issue', issue, 'name', name, 'url', url, 'snap_date', snap_date)
           order by issue = 'לא במלאי', issue collate "C", name collate "C", product_id collate "C"), '[]')
  from sh_product_issues
  where snap_date = (select max(day) from sh_jobs where job = 'issues_snapshot')
$$;

-- The certificate of the configured host; JSON null before the first check.
create or replace function sh_cert() returns jsonb
language sql stable set search_path = public as $$
  select coalesce((
    select jsonb_build_object(
             'host', host, 'issuer', issuer, 'not_after', not_after, 'days_left', days_left,
             'ok', ok, 'err', err, 'checked_at', checked_at)
    from sh_cert
    where host = (select value #>> '{}' from sh_settings where key = 'host')), 'null')
$$;

-- ---------------------------------------------------------------- read side: /api/site/now

create or replace function sh_now() returns jsonb
language sql stable set search_path = public as $$
  with recent as (
    -- a round older than 15 minutes says nothing about now
    select x.round_at, x.kind, x.page, x.url, x.ok, x.status, x.ms, p.sort
    from sh_probe x left join sh_pages p on p.name = x.page
    where x.round_at >= now() - interval '15 minutes'
  ), last_full as (
    select max(round_at) as at from recent where kind = 'full'
  ), last_any as (
    select round_at as at, kind from recent order by round_at desc, kind limit 1
  ), latest as (
    select r.page, r.ok, r.sort from recent r join last_any l on r.round_at = l.at and r.kind = l.kind
  ), rum as (
    select count(*) as n, round(percentile_cont(0.75) within group (order by lcp_ms)::numeric)::int as p75
    from sh_rum
    where created_at >= now() - interval '60 minutes' and not is_test
      and site in (select jsonb_array_elements_text(value) from sh_settings where key = 'live_hosts')
  ), src as (
    select site, is_test from sh_rum order by created_at desc limit 1000
  )
  select jsonb_build_object(
    'pages', coalesce((
      select jsonb_agg(jsonb_build_object(
               'page', r.page, 'url', r.url, 'ok', r.ok, 'status', r.status,
               'ms', case when r.ok then r.ms end)
               order by r.sort nulls last, r.page)
      from recent r join last_full f on r.round_at = f.at
      where r.kind = 'full'), '[]'),
    'latest', coalesce((
      select jsonb_agg(jsonb_build_object('page', page, 'ok', ok) order by sort nulls last, page)
      from latest), '[]'),
    'light', coalesce((select kind = 'light' from last_any), false),
    'all_ok', coalesce((select bool_and(ok) from latest), false),
    'any_ok', coalesce((select bool_or(ok) from latest), false),
    'age_sec', (select floor(extract(epoch from now() - at))::int from last_any),
    'rum', (select jsonb_build_object('n', n, 'p75_ms', p75) from rum),
    'speed', coalesce((
      select jsonb_build_object('lcp_ms', s.lcp_ms, 'score', s.score, 'checked_at', s.at)
      from sh_pages p join sh_speed s on s.url = p.url
      where p.is_home and s.strategy = 'mobile' and s.ok and s.lcp_ms is not null
      order by s.at desc
      limit 1), '{}'),
    'alerts_open', (select count(*) from sh_alerts where closed_at is null),
    'rum_src', (
      select case when count(*) = 0 then 'null'::jsonb else jsonb_build_object(
               'n', count(*),
               -- the five largest: the tile is one line, and a forged name must not fill the screen
               'hosts', (select jsonb_agg(jsonb_build_object('host', site, 'n', n) order by n desc, site)
                         from (select site, count(*) as n from src group by site order by n desc, site limit 5) h),
               'cols', '["created_at", "is_test", "lcp_ms", "path", "site"]'::jsonb,
               'test', count(*) filter (where is_test)) end
      from src))
$$;

-- ---------------------------------------------------------------- read side: drill-downs

-- The failed checks of the full rounds, newest first, at most 500.
create or replace function sh_drill_fails(
  p_from timestamptz, p_to timestamptz, p_page text default null, p_bucket text default null) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  v_fmt text := sh_bucket_fmt(length(p_bucket) > 10);
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'at_il', sh_il(round_at), 'page', page, 'kind', sh_fail_kind(fail, status), 'err', err, 'ms', ms)
             order by round_at desc, page), '[]')
    from (
      select round_at, page, fail, status, err, ms
      from sh_probe
      where kind = 'full' and not ok and round_at >= p_from and round_at < p_to
        and (coalesce(p_page, '') = '' or page = p_page)
        and (coalesce(p_bucket, '') = '' or to_char(round_at at time zone v_tz, v_fmt) = p_bucket)
      order by round_at desc, page
      limit 500
    ) f);
end $$;

-- Response time per page inside one bucket of the availability chart.
create or replace function sh_drill_bucket(p_bucket text) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz    text := sh_tz();
  v_fmt   text := sh_bucket_fmt(length(p_bucket) > 10);
  v_start timestamp := p_bucket::timestamp;
  v_end   timestamp := v_start + case when length(p_bucket) > 10 then interval '1 hour' else interval '1 day' end;
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'page', b.page, 'checks', b.checks, 'failed', b.failed,
             'ms_p50', round(b.p50::numeric)::int, 'ms_max', b.ms_max, 'worst_il', sh_il(b.worst_at))
             order by p.sort nulls last, b.page), '[]')
    from (
      select page, count(*) as checks, count(*) filter (where not ok) as failed,
             percentile_cont(0.5) within group (order by ms) filter (where ok) as p50,
             max(ms) filter (where ok) as ms_max,
             (array_agg(round_at order by ms desc nulls last, round_at) filter (where ok))[1] as worst_at
      from sh_probe
      where kind = 'full'
        -- An hour more on each side, then the bucket's own text: on the night the clocks go
        -- back one local hour happens twice, and the chart counted both in this bucket.
        and round_at >= (v_start at time zone v_tz) - interval '1 hour'
        and round_at <  (v_end at time zone v_tz) + interval '1 hour'
        and to_char(round_at at time zone v_tz, v_fmt) = p_bucket
      group by page
    ) b left join sh_pages p on p.name = b.page);
end $$;

-- The lab runs of one page, newest first. A failed run carries only its error. The reasons
-- ("opps") go out with the newest 100 successful runs only: they are nine tenths of a run, and
-- "what slows the page" on the sheet should describe the page as it is now.
create or replace function sh_drill_runs(
  p_from timestamptz, p_to timestamptz, p_url text, p_strategy text default 'mobile',
  p_bucket text default null) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  v_fmt text := sh_bucket_fmt(length(p_bucket) > 10);
begin
  return (
    select coalesce(jsonb_agg(
             case when ok then jsonb_build_object(
                    'ok', true, 'err', null, 'at_il', sh_il(at), 'lcp_ms', lcp_ms, 'score', score,
                    'ttfb_ms', ttfb_ms, 'bytes', bytes, 'cls', cls, 'crux_category', crux_category,
                    'crux_lcp_ms', crux_lcp_ms,
                    'opps', case when nth <= 100 then coalesce(opps, '[]') else '[]' end)
                  else jsonb_build_object('ok', false, 'err', err, 'at_il', sh_il(at)) end
             order by at desc), '[]')
    from (
      -- nth: a successful run's place among the successful runs of the answer, newest first
      select *, count(*) filter (where ok) over (order by at desc) as nth
      from sh_speed
      where url = p_url and strategy = p_strategy and at >= p_from and at < p_to
        and (coalesce(p_bucket, '') = '' or to_char(at at time zone v_tz, v_fmt) = p_bucket)
    ) r);
end $$;

-- One alert: its row, the failed checks behind a "down" alert, and the pushes that were sent.
create or replace function sh_drill_alert(p_id bigint) returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(sh_alert_row(a) || jsonb_build_object(
    'fails', coalesce((
      -- the sheet prints "קוד <status>" when there is a status and err otherwise, so the status
      -- goes out only when the status was the failure, and every other failure gets words
      select jsonb_agg(jsonb_build_object(
               'at', sh_il(f.round_at), 'page', f.page,
               'status', case when f.fail = 'http' then f.status end,
               'err', case when f.fail <> 'http' then coalesce(f.err, sh_fail_kind(f.fail, f.status)) end)
               order by f.round_at)
      from (
        -- The failed checks (full and light) from the last answer before the alert opened until
        -- it closed. An alert opens within a minute or two of the first failure, so a day back
        -- is far enough to look for that last answer.
        select x.round_at, x.page, x.status, x.err, x.fail
        from sh_probe x
        where a.kind = 'down' and x.page = substr(a.key, 6) and not x.ok
          and x.round_at <= coalesce(a.closed_at, now())
          and x.round_at > coalesce((
                select max(o.round_at) from sh_probe o
                where o.page = substr(a.key, 6) and o.ok
                  and o.round_at <= a.opened_at and o.round_at > a.opened_at - interval '1 day'),
                a.opened_at - interval '1 day')
        order by x.round_at
        limit 500
      ) f), '[]'),
    -- a push appears once its fate is known: accepted, not configured, or given up after the last retry
    'sent', coalesce((
      select jsonb_agg(jsonb_build_object('event', m.event, 'status', m.status, 'at', sh_il(m.at))
               order by m.at, m.id)
      from sh_messages m
      where m.alert_id = a.id and m.status is not null), '[]'))), '[]')
  from sh_alerts a
  where a.id = p_id
$$;

-- ---------------------------------------------------------------- read side: the rest

-- The push log, newest first. sent = the push service accepted it.
create or replace function sh_messages(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'kind', kind, 'title', title, 'msg', msg, 'at_il', sh_il(at),
           'sent', coalesce(status between 200 and 299, false))
           order by at desc, id desc), '[]')
  from sh_messages
  where at >= p_from and at < p_to
$$;

-- "ראיתי": hides open alerts from the red bar. It does not close them, and an alert that is
-- closed or already marked is left as it is.
create or replace function sh_alert_ack(p_ids jsonb, p_who text) returns jsonb
language sql set search_path = public as $$
  with marked as (
    update sh_alerts set acked_at = now(), acked_by = p_who
    where id in (select value::bigint from jsonb_array_elements_text(p_ids))
      and closed_at is null and acked_at is null
    returning 1
  )
  select jsonb_build_object('n', count(*)) from marked
$$;

create or replace function sh_login_log_add(p_ip text, p_ok boolean, p_who text, p_ua text) returns jsonb
language sql set search_path = public as $$
  with added as (
    insert into sh_login_log (ip, ok, who, ua) values (p_ip, p_ok, p_who, p_ua) returning 1
  )
  select jsonb_build_object('n', count(*)) from added
$$;

-- Real-user page views: [{site, path, lcp_ms, is_test}]. The last line of defence for the
-- limits of the ingest (spec §7.7): no query string is stored, and a row with an impossible
-- timing, a site that is not "live" or a host name, or a path longer than 300 characters is dropped.
-- And nothing at all is stored while the last 24 hours already hold 30,000 rows: the ingest is
-- open to the internet, and a flood of forged views must not fill the database (a full database
-- stops storing probes and alerts too). 30,000 a day is about 130 MB over the 30 days rows are kept.
create or replace function sh_rum_add(p_rows jsonb) returns jsonb
language sql set search_path = public as $$
  with room as (
    select count(*) < 30000 as free
    from (select 1 from sh_rum where created_at > now() - interval '24 hours' limit 30000) today
  ), added as (
    insert into sh_rum (site, path, lcp_ms, is_test)
    select r.site, r.path, r.lcp_ms, coalesce(r.is_test, false)
    from (select site, regexp_replace(path, '[?#].*$', '') as path, lcp_ms, is_test
          from jsonb_to_recordset(p_rows) as x(site text, path text, lcp_ms numeric, is_test boolean)) r
    where (select free from room)
      and r.site ~ '^[a-z0-9.-]{1,100}$' and length(r.path) <= 300 and r.lcp_ms between 1 and 60000
    returning 1
  ), beat as (
    update sh_flows set last_at = now()
    where flow_name = 'מהירות אצל לקוחות' and exists (select 1 from added)
  )
  select jsonb_build_object('n', count(*)) from added
$$;

create or replace function sh_ping() returns jsonb
language sql stable set search_path = public as $$
  select '"ok"'::jsonb
$$;

-- ---------------------------------------------------------------- write side: collectors
-- Every collector function writes its flow's proof of life (sh_flows.last_at) last, and only
-- when the run succeeded: a collector that fails leaves no trace and shows up as late or silent.

-- One probe round: [{page, url, ok, status, ms, fail, err}]. A round that is sent twice is
-- stored once.
create or replace function sh_probe_add(p_round_at timestamptz, p_kind text, p_rows jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_n int;
begin
  insert into sh_probe (round_at, kind, page, url, ok, status, ms, fail, err)
  select p_round_at, p_kind, r.page, r.url, r.ok, r.status, r.ms, nullif(r.fail, ''), nullif(r.err, '')
  from jsonb_to_recordset(p_rows)
       as r(page text, url text, ok boolean, status numeric, ms numeric, fail text, err text)
  on conflict do nothing;
  get diagnostics v_n = row_count;
  -- A full round proves the prober ran, also when every page failed. A light round does not
  -- count: the flow is "a full round every minute".
  if p_kind = 'full' and v_n > 0 then
    update sh_flows set last_at = greatest(last_at, p_round_at) where flow_name = 'בודק זמינות האתר';
  end if;
  return jsonb_build_object('n', v_n);
end $$;

-- Lab runs: [{at, url, page, strategy, source, ok, err, score, lcp_ms, cls, ttfb_ms, bytes,
-- crux_category, crux_lcp_ms, opps, lh_version}]. A run that is sent twice is stored once.
create or replace function sh_speed_add(p_rows jsonb) returns jsonb
language sql set search_path = public as $$
  with added as (
    insert into sh_speed (at, url, page, strategy, source, ok, err, score, lcp_ms, cls, ttfb_ms,
                          bytes, crux_category, crux_lcp_ms, opps, lh_version)
    select coalesce(r.at, now()), r.url, r.page, r.strategy, r.source, r.ok, r.err, r.score, r.lcp_ms,
           r.cls, r.ttfb_ms, r.bytes, r.crux_category, r.crux_lcp_ms, r.opps, r.lh_version
    from jsonb_to_recordset(p_rows)
         as r(at timestamptz, url text, page text, strategy text, source text, ok boolean, err text,
              score numeric, lcp_ms numeric, cls numeric, ttfb_ms numeric, bytes numeric,
              crux_category text, crux_lcp_ms numeric, opps jsonb, lh_version text)
    on conflict do nothing
    returning at, source, ok
  ), beat as (
    -- each of the two speed flows is alive when one of its runs succeeded
    update sh_flows f set last_at = greatest(f.last_at, a.at)
    from (select source, max(at) as at from added where ok group by source) a
    where f.flow_name = case a.source when 'core' then 'מדידת מהירות — עמודי ליבה'
                                      else 'מדידת מהירות — סבב כל האתר' end
  )
  select jsonb_build_object('n', count(*)) from added
$$;

-- Claims the p_n site pages that were measured longest ago (never measured first) and returns
-- their addresses. A page is claimed whether or not its measurement then succeeds. A core page
-- takes no turn: it is measured every 15 minutes already. And nobody takes a turn while the
-- rotation is switched off ("sitemap" under "off" in the configuration).
create or replace function sh_rotation_next(p_n int) returns jsonb
language sql set search_path = public as $$
  with stamp as materialized (
    -- the clock, not now(): two claims inside one transaction must still take turns
    select clock_timestamp() as at
  ), pick as (
    select url from sh_site_pages
    where active and url not in (select url from sh_pages where is_core)
      and exists (select 1 from sh_flows f where f.flow_name = 'מדידת מהירות — סבב כל האתר' and f.enabled)
    order by last_measured_at nulls first, url
    limit p_n
    for update skip locked
  ), claimed as (
    update sh_site_pages s set last_measured_at = stamp.at
    from pick, stamp
    where s.url = pick.url
    returning s.url
  )
  select coalesce(jsonb_agg(url order by url), '[]') from claimed
$$;

-- The pages of the site, from its sitemap: ["https://…", …]. Stored in the spelling of sh_url,
-- the one sh_setup stores the configured pages in, so a core page is recognised as one however
-- the sitemap writes its address.
create or replace function sh_sitemap_set(p_urls jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_urls text[];
  v_n    int;
begin
  select array_agg(url) into v_urls
  from (select distinct sh_url(listed) as url from jsonb_array_elements_text(p_urls) as listed) u
  where url is not null;
  -- an empty read looks exactly like a site whose pages all vanished
  if v_urls is null then
    raise exception 'sh_sitemap_set: an empty list is refused';
  end if;
  insert into sh_site_pages (url)
  select unnest(v_urls)
  on conflict (url) do update set active = true, last_seen = now();
  get diagnostics v_n = row_count;
  update sh_site_pages s set active = false
  where s.active and not exists (select 1 from unnest(v_urls) as l(url) where l.url = s.url);
  update sh_flows set last_at = now() where flow_name = 'טעינת מפת האתר';
  return jsonb_build_object('n', v_n);
end $$;

-- The certificate check: {host, issuer, not_before, not_after, days_left, ok, err, checked_at}.
create or replace function sh_cert_set(p_row jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  r record;
begin
  select x.host, x.issuer, x.not_before, x.not_after, x.days_left, x.ok, x.err,
         coalesce(x.checked_at, now()) as checked_at
    into r
  from jsonb_to_record(p_row) as x(host text, issuer text, not_before timestamptz, not_after timestamptz,
                                   days_left numeric, ok boolean, err text, checked_at timestamptz);
  if r.ok then
    insert into sh_cert (host, issuer, not_before, not_after, days_left, ok, err, checked_at)
    values (r.host, r.issuer, r.not_before, r.not_after, r.days_left, true, null, r.checked_at)
    on conflict (host) do update
      set issuer = excluded.issuer, not_before = excluded.not_before, not_after = excluded.not_after,
          days_left = excluded.days_left, ok = true, err = null, checked_at = excluded.checked_at;
    update sh_flows set last_at = greatest(last_at, r.checked_at) where flow_name = 'בדיקת תעודת האבטחה';
  else
    -- a failed check keeps what the last successful one found: the alert rule reads it
    insert into sh_cert (host, ok, err, checked_at) values (r.host, false, r.err, r.checked_at)
    on conflict (host) do update set ok = false, err = excluded.err, checked_at = excluded.checked_at;
  end if;
  return jsonb_build_object('n', 1);
end $$;

-- The broken products of one day's catalogue snapshot, replacing that day:
-- [{product_id, issue, name, url}]. Call it only with a complete read, also when it is empty.
create or replace function sh_issues_set(p_snap_date date, p_rows jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_n int;
begin
  delete from sh_product_issues where snap_date = p_snap_date;
  insert into sh_product_issues (snap_date, product_id, issue, name, url)
  select p_snap_date, r.product_id, r.issue, r.name, r.url
  from jsonb_to_recordset(p_rows) as r(product_id text, issue text, name text, url text);
  get diagnostics v_n = row_count;
  -- the day itself is remembered: a snapshot without broken products must still become "the latest"
  insert into sh_jobs (job, day) values ('issues_snapshot', p_snap_date) on conflict do nothing;
  update sh_flows set last_at = now() where flow_name = 'בדיקת מוצרים שבורים';
  return jsonb_build_object('n', v_n);
end $$;

-- Daily jobs keep their "done for this day" marker here, not in the worker's memory.
create or replace function sh_job_due(p_job text, p_day date) returns jsonb
language sql stable set search_path = public as $$
  select to_jsonb(not exists (select 1 from sh_jobs where job = p_job and day = p_day))
$$;

-- true when this call set the marker, false when the day was already marked.
create or replace function sh_job_mark(p_job text, p_day date) returns jsonb
language sql set search_path = public as $$
  with marked as (
    insert into sh_jobs (job, day) values (p_job, p_day) on conflict do nothing returning 1
  )
  select to_jsonb(exists (select 1 from marked))
$$;

-- ---------------------------------------------------------------- alerts and pushes

-- Evaluates the four alert rules, opens and closes alerts, queues their pushes, and claims and
-- returns the pushes that are owed, oldest first. Call it every minute, after the full probe round.
-- An alert of any other kind (another part of the owner's system may keep its own in sh_alerts)
-- is never judged, closed or pushed about here.
create or replace function sh_alerts_check() returns jsonb
language plpgsql set search_path = public as $$
declare
  v_down_after int := coalesce((select (value #>> '{}')::int from sh_settings where key = 'down_after'), 1);
  v_owed       jsonb;
begin
  -- One caller at a time: a second one waits here and then, under read committed (the default),
  -- sees what the first one did: its alerts, its pushes and its claims. Under any stricter level
  -- the unique index on open alerts still forbids a duplicate, and the second caller gets an
  -- error instead.
  perform pg_advisory_xact_lock(hashtext('sh_alerts_check'));

  with state as materialized (
    -- One row per thing that can be judged right now. bad = the alert should be open,
    -- good = it should be closed; neither = no news (for example: no check since).

    -- down: the newest down_after rounds of a probe page, full or light, all failed
    select 'down:' || p.name as key, 'down' as kind, 'האתר לא עונה: ' || p.name as title,
           sh_fail_kind(r.fail, r.status) || E'\n' || r.url as body,
           r.n = v_down_after and not r.any_ok as bad, coalesce(r.ok, false) as good
    from sh_pages p
    cross join lateral (
      select count(*) as n, bool_or(t.ok) as any_ok,
             (array_agg(t.ok order by t.round_at desc, t.kind))[1] as ok,
             (array_agg(t.fail order by t.round_at desc, t.kind))[1] as fail,
             (array_agg(t.status order by t.round_at desc, t.kind))[1] as status,
             (array_agg(t.url order by t.round_at desc, t.kind))[1] as url
      from (select x.round_at, x.kind, x.ok, x.fail, x.status, x.url
            from sh_probe x
            -- a round from before yesterday is no evidence about now, and without this bound a
            -- page that was never probed would cost a walk through the whole history
            where x.page = p.name and x.round_at > now() - interval '1 day'
            order by x.round_at desc, x.kind
            limit v_down_after) t
    ) r
    where p.is_probe

    union all
    -- slow: the two newest successful phone runs of a core page are both above 4 seconds
    select 'slow:' || p.name, 'slow', 'עמוד איטי: ' || p.name,
           to_char(r.newest / 1000.0, 'FM990.0') || ' שניות עד התוכן, פעמיים ברצף' || E'\n' || p.url,
           r.n = 2 and r.fastest > 4000, coalesce(r.newest <= 4000, false)
    from sh_pages p
    cross join lateral (
      select count(*) as n, min(t.lcp_ms) as fastest, (array_agg(t.lcp_ms order by t.at desc))[1] as newest
      from (select s.at, s.lcp_ms
            from sh_speed s
            where s.url = p.url and s.strategy = 'mobile' and s.ok and s.lcp_ms is not null
            order by s.at desc
            limit 2) t
    ) r
    where p.is_core

    union all
    -- silent: a flow that has run before is older than its late_minutes. It clears when the flow
    -- "ran again": a run that is not older than the alert. (Not "is young enough again": the
    -- independent check of spec §7.10 opens this alert earlier than late_minutes, and must not
    -- see it closed a minute later.) A flow whose alerts flag is off is not judged at all.
    select 'silent:' || f.flow_name, 'silent', 'המדידה נעצרה: ' || f.flow_name,
           'אין מדידה כבר ' || sh_span(floor(f.age)),          -- whole minutes, as the flow's row on the screen
           f.age > f.late_minutes,
           coalesce(f.last_at >= (select a.opened_at from sh_alerts a
                                  where a.key = 'silent:' || f.flow_name and a.closed_at is null), false)
    from (select *, extract(epoch from now() - last_at) / 60 as age from sh_flows) f
    where f.enabled and f.alerts and f.last_at is not null

    union all
    -- cert: the last successful check found fewer than 14 days. Not judged while the
    -- certificate check is switched off ("off" in the configuration, or an http:// site).
    select 'cert:' || c.host, 'cert',
           case when c.days_left >= 1 then 'תעודת האבטחה פגה בעוד ' || sh_span(c.days_left * 1440)
                when c.days_left = 0 then 'תעודת האבטחה פגה בעוד פחות מיום'
                else 'תוקף תעודת האבטחה פג' end,
           c.host, c.days_left < 14, c.days_left >= 14
    from sh_cert c
    where c.host = (select value #>> '{}' from sh_settings where key = 'host') and c.days_left is not null
      and exists (select 1 from sh_flows f where f.flow_name = 'בדיקת תעודת האבטחה' and f.enabled)
  ), opened as (
    -- insert, never upsert: the unique index on key covers open alerts only
    insert into sh_alerts (key, kind, title, body)
    select s.key, s.kind, s.title, s.body
    from state s
    where s.bad and not exists (select 1 from sh_alerts a where a.key = s.key and a.closed_at is null)
    returning id, kind, title, body
  ), closed as (
    -- also closes an alert whose subject is gone (a page that left the configuration, a flow
    -- that was switched off or lost its alerts flag): nothing could ever clear it
    update sh_alerts a set closed_at = now()
    where a.closed_at is null and a.kind in ('down', 'slow', 'silent', 'cert')
      and coalesce((select s.good from state s where s.key = a.key), true)
    returning a.id, a.kind, a.key, a.title, a.opened_at
  )
  insert into sh_messages (alert_id, event, kind, title, msg, priority)
  select id, 'open', 'התראה', title, body, case when kind in ('down', 'silent') then 4 else 3 end
  from opened
  union all
  -- A recovery names what recovered, the page or the flow (the rest of the alert's key), and
  -- not the alert's title: "חזר לתקין: האתר לא עונה: …" would read as a contradiction. The
  -- alert's title goes into the text, above how long it lasted.
  select id, 'close', 'חזר לתקין',
         'חזר לתקין: ' || case when kind = 'cert' then 'תעודת האבטחה' else substr(key, length(kind) + 2) end,
         title || E'\n' || 'נמשך ' || sh_span(sh_minutes(opened_at, now())), 2
  from closed;

  -- The claim: a push without a final result goes to this caller, and to nobody else for the
  -- next two minutes. Two workers that overlap during a deploy therefore never send one push
  -- twice, and a push whose sender died, or whose attempt failed, is offered again afterwards.
  with claimed as (
    update sh_messages set claimed_at = now()
    where status is null and (claimed_at is null or claimed_at <= now() - interval '2 minutes')
    returning id, at, title, msg, priority, click, kind, event
  )
  -- title and msg are the push as the phone shows it: the sender adds nothing to them
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', id, 'title', title, 'msg', msg, 'priority', priority, 'click', click,
           'kind', kind, 'event', event)
           order by at, id), '[]')
    into v_owed
  from claimed;
  return v_owed;
end $$;

-- Records the result of one attempt to push a message (spec §7.9). A 2xx status settles it as
-- sent, and 0 ("pushing is not configured") settles it at once as not sent. Any other status is
-- a failed attempt: the push stays owed and sh_alerts_check offers it again when its claim has
-- lapsed, until the fifth failure settles it with that last status.
create or replace function sh_message_sent(p_id bigint, p_status int) returns jsonb
language sql set search_path = public as $$
  with tried as (
    update sh_messages
    set attempts = attempts + 1,
        -- a result is never null (null is "still owed"): an attempt reported without a status
        -- counts as 599, a network error
        status = case when p_status between 200 and 299 or p_status = 0 or attempts >= 4
                      then coalesce(p_status, 599) end
    where id = p_id and status is null
    returning 1
  )
  select jsonb_build_object('n', count(*)) from tried
$$;

-- Queues the morning summary of the last 24 hours, once per day: the day's marker is set first,
-- so a second call (or a second worker) queues nothing. A new installation has nothing to sum
-- up, and its first push must not be "good morning, nothing was measured" in the afternoon: until
-- the oldest probe round is six hours old the day counts as done and nothing is queued.
create or replace function sh_morning(p_day date) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_checks  numeric;
  v_failed  numeric;
  v_outages int;
  v_minutes int;
  v_up      numeric;
  v_verdict text;
  v_open    int;
begin
  insert into sh_jobs (job, day) values ('morning', p_day) on conflict do nothing;
  if not found then
    return jsonb_build_object('n', 0);
  end if;
  if not exists (select 1 from sh_probe where round_at <= now() - interval '6 hours') then
    return jsonb_build_object('n', 0, 'skipped', 'the oldest probe round is less than 6 hours old');
  end if;

  -- the same figures the screen shows for "24 שעות", from the same functions
  select sum((r ->> 'checks')::int), sum((r ->> 'failed')::int),
         count(*) filter (where r ? 'outage_minutes'), sum((r ->> 'outage_minutes')::int)
    into v_checks, v_failed, v_outages, v_minutes
  from jsonb_array_elements(sh_availability(now() - interval '24 hours', now())) r;
  v_up := 100 - 100 * v_failed / nullif(v_checks, 0);
  select r ->> 'verdict' into v_verdict
  from jsonb_array_elements(sh_speed(now() - interval '24 hours', now())) r
  where r ->> 'section' = 'שורה תחתונה';
  select count(*) into v_open from sh_alerts where closed_at is null;

  insert into sh_messages (event, kind, title, msg, priority)
  values ('morning', 'בוקר',
          case when v_open = 0 and v_checks is null then 'בוקר טוב: אין מדידות'   -- nothing measured is not "fine"
               when v_open = 0 then 'בוקר טוב: האתר תקין'
               when v_open = 1 then 'בוקר טוב: התראה פתוחה אחת'
               else 'בוקר טוב: ' || v_open || ' התראות פתוחות' end,
          -- a line without a value is left out
          concat_ws(E'\n',
            coalesce('זמינות ' || to_char(v_up, case when v_up < 99.95 then 'FM990.00' else 'FM990.0' end) || '% ב-24 שעות',
                     'אין בדיקות זמינות ב-24 שעות'),
            case when v_outages > 0 then 'נפילות: ' || v_outages || ' (' || v_minutes || ' דקות)' end,
            'מהירות עמוד הבית: ' || v_verdict),
          2);
  return jsonb_build_object('n', 1);
end $$;

-- The retention rules (spec §7.2); alerts and messages are kept for good. Returns how many
-- rows went, per table: sh_probe as "probe" (full rounds) and "probe_light".
create or replace function sh_cleanup() returns jsonb
language plpgsql set search_path = public as $$
declare
  -- what the longest views of the screen read: full-round probes and the runs of the core pages
  v_keep   interval := make_interval(days => (sh_config() ->> 'keep_days')::int);
  v_today  date := (now() at time zone sh_tz())::date;
  v_latest date := (select max(day) from sh_jobs where job = 'issues_snapshot');
  v_probe int; v_light int; v_speed int; v_rum int; v_issues int; v_jobs int; v_logins int;
begin
  delete from sh_probe where kind = 'full' and round_at < now() - v_keep;
  get diagnostics v_probe = row_count;
  delete from sh_probe where kind = 'light' and round_at < now() - interval '7 days';
  get diagnostics v_light = row_count;
  delete from sh_speed
  where (source = 'core' and at < now() - v_keep) or (source = 'rotation' and at < now() - interval '45 days');
  get diagnostics v_speed = row_count;
  delete from sh_rum where created_at < now() - interval '30 days';
  get diagnostics v_rum = row_count;
  -- the latest snapshot is the one the screen shows, however old it is
  delete from sh_product_issues where snap_date < v_today - 30 and snap_date is distinct from v_latest;
  get diagnostics v_issues = row_count;
  -- the newest marker of a job stays: for the catalogue it is what names the latest snapshot
  delete from sh_jobs j
  where j.day < v_today - 400 and j.day < (select max(n.day) from sh_jobs n where n.job = j.job);
  get diagnostics v_jobs = row_count;
  delete from sh_login_log where at < now() - interval '400 days';
  get diagnostics v_logins = row_count;
  return jsonb_build_object('probe', v_probe, 'probe_light', v_light, 'speed', v_speed, 'rum', v_rum,
                            'product_issues', v_issues, 'jobs', v_jobs, 'login_log', v_logins);
end $$;

-- ---------------------------------------------------------------- privileges
-- Only the owner of these functions may run them. On Supabase the service role (the secret
-- key) may too, and the two public API roles lose the grant they get by default. sh_deadman
-- (deadman.sql) stays with the owner alone: only the database's own job runs it.
do $$
declare
  f record;
  r text;
begin
  for f in select p.oid::regprocedure as sig, p.proname as name from pg_proc p
           where p.pronamespace = 'public'::regnamespace and p.proname like 'sh\_%' loop
    execute format('revoke all on function %s from public', f.sig);
    foreach r in array array['anon', 'authenticated'] loop
      if exists (select 1 from pg_roles where rolname = r) then
        execute format('revoke all on function %s from %I', f.sig, r);
      end if;
    end loop;
    if f.name <> 'sh_deadman' and exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', f.sig);
    end if;
  end loop;
end $$;

-- PostgREST (Supabase's REST interface) keeps a list of the functions it may call, and must be
-- told to read it again after this file; on a plain Postgres nobody listens, and that is fine.
notify pgrst, 'reload schema';
