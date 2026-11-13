-- Site Health: who watches the watcher (spec §7.10, option 1), for Supabase.
--
-- If the worker that probes the site dies, nothing in the worker can say so. This file makes the
-- database say it: every 5 minutes pg_cron runs sh_deadman(), which opens the alert
-- "המדידה נעצרה: בודק זמינות האתר" when the newest full probe round is older than 10 minutes, and
-- pushes it straight to ntfy with pg_net. The alert is an ordinary row of sh_alerts with an
-- ordinary row of sh_messages, so the screen and the message log show it like any other.
--
-- THE KIT'S TESTS RUN THIS FILE ONLY AGAINST STAND-INS. It needs pg_cron, pg_net and Vault, which
-- the test database does not have: tests/test_sql.py puts empty look-alikes in their place and
-- checks what sh_deadman() decides and hands to pg_net, not that anything is really scheduled or
-- sent. The calls were written from the documentation of the three (pg_net: the request leaves
-- only after the transaction commits; the answer arrives later in net._http_response; the body
-- must be JSON; the default timeout differs between versions, so it is always passed). Verify
-- it on the real project with the steps at the end of this comment.
--
-- What it guarantees, and how
--   * One open alert at most: it takes the same lock as sh_alerts_check and inserts only when no
--     alert with this key is open (the unique index on open alerts would refuse a second one).
--   * No push twice: a push is published only by whoever holds its claim (sh_messages.claimed_at,
--     the worker's own rule). This function claims for ten minutes, until its next run has read
--     the answer of ntfy. An accepted push is settled as sent. A refused or timed-out one counts
--     as a failed attempt and is published again at once (five attempts, like the worker). A
--     request without any answer is never published again: pg_net may still send it.
--   * It closes the alert when a full round newer than the alert exists, and pushes "חזר לתקין".
--     While the worker is alive its own alert tick does this first, within the minute.
--   * The message log tells the truth: a push shows as sent only after ntfy's answer was read,
--     which is one run (up to 5 minutes) after it left.
--
-- What it cannot see: a database that is itself down, paused or read-only. For that, also give
-- the worker a HEARTBEAT_URL (option 2 of spec §7.10).
--
-- Before running this file
--   1. Dashboard > Integrations: enable Cron (pg_cron). Dashboard > Database > Extensions: pg_net.
--      (The lines below the header repeat Supabase's own install commands for the two, the two
--      grants on the cron schema included; they change nothing when the dashboard already did it.)
--   2. Dashboard > Project Settings > Vault: add the secrets. Never write their values into a
--      file of the repository.
--        sh_ntfy_topic      the topic, the same value as NTFY_TOPIC of the worker   (required)
--        sh_ntfy_url        the ntfy server; without it https://ntfy.sh             (optional)
--        sh_ntfy_token      an access token, when the topic is reserved             (optional)
--        sh_dashboard_url   this dashboard's address, for the tap on the push       (optional)
--      Without sh_ntfy_topic the alert still opens and shows on the screen; its message is
--      logged as not sent.
--   3. schema.sql and functions.sql are applied, and sh_setup has run.
--
-- Verifying it on the real project (none of this is covered by the kit's tests)
--   a. Run this file in the SQL editor. Then:
--        select jobname, schedule, active from cron.job where jobname like 'sh-deadman%';
--      shows two active jobs.
--   b. select name from vault.decrypted_secrets where name like 'sh\_%';     -- the names only
--   c. While the worker runs:  select sh_deadman();   answers {"opened": null, "closed": null, "published": 0}.
--   d. Stop the worker for 16 minutes (go-live checklist, item 3). The job runs every 5 minutes
--      and opens the alert once the newest round is older than 10 minutes, so the push comes 10
--      to 15 minutes after the stop; a worker that is started again earlier can hide it. The
--      phone gets "המדידה נעצרה: בודק זמינות האתר" and the screen shows the alert. Then:
--        select id, status_code, timed_out, error_msg from net._http_response order by created desc limit 3;
--      shows status_code 200, and after the next run (5 minutes):
--        select title, event, status, attempts from sh_messages order by id desc limit 3;
--      shows status 200 for the "open" message.
--   e. Start the worker. Within a few minutes of the start the alert closes and the phone gets
--      "חזר לתקין: בודק זמינות האתר" (the host builds and starts the service first).
--   f. select status, return_message, start_time from cron.job_run_details
--      where jobid = (select jobid from cron.job where jobname = 'sh-deadman') order by start_time desc limit 5;
--      shows "succeeded" every 5 minutes.
--   To remove it:  select cron.unschedule('sh-deadman');  select cron.unschedule('sh-deadman-history');
--
-- Safe to run again: the function is replaced and a job with the same name is replaced.

create extension if not exists pg_cron with schema pg_catalog;
grant usage on schema cron to postgres;
grant all privileges on all tables in schema cron to postgres;
create extension if not exists pg_net with schema extensions;

-- The pg_net request of each push this function published, until its answer has been read.
create table if not exists sh_deadman_push (
  message_id bigint primary key references sh_messages (id),
  request_id bigint not null,
  at         timestamptz not null default now()
);
alter table sh_deadman_push enable row level security;

create or replace function sh_deadman() returns jsonb
language plpgsql set search_path = public as $$
declare
  -- the flow of the availability probe and the key of its "silent" alert, as sh_alerts_check
  -- names them; the title and the texts below are the ones of its "silent" rule
  c_flow constant text := 'בודק זמינות האתר';
  c_key  constant text := 'silent:בודק זמינות האתר';
  v_last   timestamptz;
  v_alert  sh_alerts;
  v_opened bigint;
  v_closed bigint;
  v_topic  text;
  v_url    text;
  v_token  text;
  v_click  text;
  v_published int := 0;
  r record;
begin
  -- The lock of sh_alerts_check: the worker and this function never judge the alert, or hand
  -- out its pushes, at the same moment.
  perform pg_advisory_xact_lock(hashtext('sh_alerts_check'));

  -- 1. What became of the pushes of earlier runs. pg_net sends after the commit, so the answer
  --    of a push is known one run later, and is kept for six hours.
  for r in
    select p.message_id, h.id is not null as answered, h.status_code, p.at
    from sh_deadman_push p left join net._http_response h on h.id = p.request_id
  loop
    if r.answered then
      -- 2xx settles it as sent; anything else (no status: a timeout or a network error, 599)
      -- is a failed attempt, and the push is free to be published again
      perform sh_message_sent(r.message_id, coalesce(r.status_code, 599));
      update sh_messages set claimed_at = null where id = r.message_id and status is null;
      delete from sh_deadman_push where message_id = r.message_id;
    elsif r.at < now() - interval '6 hours' then
      -- no answer will come any more: settled as not sent, whatever the count of attempts
      update sh_messages set status = 599, attempts = attempts + 1 where id = r.message_id and status is null;
      delete from sh_deadman_push where message_id = r.message_id;
    else
      -- still on its way, or pg_net is not sending: nobody may publish it a second time
      update sh_messages set claimed_at = now() + interval '8 minutes' where id = r.message_id and status is null;
    end if;
  end loop;

  -- 2. The alert. A flow that is switched off, or that never ran, is not judged.
  select last_at into v_last from sh_flows where flow_name = c_flow and enabled and alerts;
  select * into v_alert from sh_alerts where key = c_key and closed_at is null;

  if v_last < now() - interval '10 minutes' and v_alert.id is null then
    insert into sh_alerts (key, kind, title, body)
    values (c_key, 'silent', 'המדידה נעצרה: ' || c_flow,
            'אין מדידה כבר ' || sh_span(floor(extract(epoch from now() - v_last) / 60)))
    returning id into v_opened;
    insert into sh_messages (alert_id, event, kind, title, msg, priority)
    select id, 'open', 'התראה', title, body, 4 from sh_alerts where id = v_opened;
  elsif v_alert.id is not null and v_last >= v_alert.opened_at then
    -- it ran again: a full round that is newer than the alert
    update sh_alerts set closed_at = now() where id = v_alert.id;
    insert into sh_messages (alert_id, event, kind, title, msg, priority)
    values (v_alert.id, 'close', 'חזר לתקין', 'חזר לתקין: ' || c_flow,
            v_alert.title || E'\n' || 'נמשך ' || sh_span(sh_minutes(v_alert.opened_at, now())), 2);
    v_closed := v_alert.id;
  end if;

  -- 3. Publish the pushes of this alert that are owed and that nobody holds: the one this run
  --    just queued, one whose attempt failed, one the worker queued and then died on.
  select decrypted_secret into v_topic from vault.decrypted_secrets where name = 'sh_ntfy_topic';
  select decrypted_secret into v_url from vault.decrypted_secrets where name = 'sh_ntfy_url';
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'sh_ntfy_token';
  select decrypted_secret into v_click from vault.decrypted_secrets where name = 'sh_dashboard_url';
  -- JSON goes to the root of the ntfy server, never to /<topic>
  v_url := rtrim(coalesce(nullif(btrim(v_url), ''), 'https://ntfy.sh'), '/') || '/';
  v_click := rtrim(nullif(btrim(v_click), ''), '/') || '/site';

  for r in
    -- the claim lasts until now + 10 minutes (sh_alerts_check adds two to claimed_at): over
    -- the next run, which reads the answer
    update sh_messages m set claimed_at = now() + interval '8 minutes'
    from sh_alerts a
    where a.id = m.alert_id and a.key = c_key and m.status is null
      and (m.claimed_at is null or m.claimed_at <= now() - interval '2 minutes')
    returning m.id, m.event, m.title, m.msg, m.priority
  loop
    if coalesce(btrim(v_topic), '') = '' then
      perform sh_message_sent(r.id, 0);          -- pushing is not configured: logged, not sent
    else
      insert into sh_deadman_push (message_id, request_id)
      values (r.id, net.http_post(
        url := v_url,
        body := jsonb_strip_nulls(jsonb_build_object(
          'topic', btrim(v_topic),
          -- title and text as they are stored, as the worker sends them
          'title', left(r.title, 199),
          'message', left(coalesce(r.msg, r.title), 1499),
          'priority', r.priority,
          'tags', jsonb_build_array(case when r.event = 'close' then 'white_check_mark' else 'rotating_light' end),
          'click', v_click)),
        -- pg_net refuses any other Content-Type
        headers := jsonb_strip_nulls(jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || nullif(btrim(v_token), ''))),
        timeout_milliseconds := 10000))
      on conflict (message_id) do update set request_id = excluded.request_id, at = now();
      v_published := v_published + 1;
    end if;
  end loop;

  return jsonb_build_object('opened', v_opened, 'closed', v_closed, 'published', v_published);
end $$;

-- Private, more so than the other sh_* tables and functions: only the owner (the role pg_cron
-- runs the job as) gets in. The service role does not need this function or its table, so it
-- loses what the platform's default privileges gave it, and schema.sql and functions.sql leave
-- the two out of their grants: applying those files again later (an upgrade) changes nothing here.
do $$
declare
  r text;
begin
  revoke all on function sh_deadman() from public;
  foreach r in array array['anon', 'authenticated', 'service_role'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on function sh_deadman() from %I', r);
      execute format('revoke all on table sh_deadman_push from %I', r);
    end if;
  end loop;
end $$;

-- Every 5 minutes. (pg_cron counts in UTC; an interval does not care.)
select cron.schedule('sh-deadman', '*/5 * * * *', 'select public.sh_deadman()');

-- pg_cron keeps a row for every run, for ever: 288 a day for the job above.
select cron.schedule('sh-deadman-history', '23 3 * * *', $$
  delete from cron.job_run_details
  where end_time < now() - interval '7 days'
    and jobid in (select jobid from cron.job where jobname like 'sh-deadman%')
$$);
