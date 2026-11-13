"""Database access for the site-health server and collectors.

Everything goes through rpc(): one call of one sh_* SQL function, returning its JSON result.
The transport is chosen by the environment:

    SUPABASE_URL + SUPABASE_SECRET_KEY    HTTPS: POST {SUPABASE_URL}/rest/v1/rpc/<fn>
    DATABASE_URL                          a normal Postgres connection (psycopg 3)

Parameter values must be JSON values (send times as ISO 8601 strings), so both transports
accept exactly the same calls.
"""
import http.client
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request

TIMEOUT = 30                                  # seconds
_FUNCTION = re.compile(r"sh_[a-z_]+")         # names go into a URL or into SQL text: nothing else may pass
_PARAMETER = re.compile(r"p_[a-z_]+")
_LOCAL_HTTP = re.compile(r"http://(127\.0\.0\.1|localhost)(:[0-9]+)?(/.*)?")     # plain HTTP: this machine only
_thread = threading.local()                   # the Postgres transport keeps one connection per thread
log = logging.getLogger("site_health.db")


class DbError(Exception):
    """A database call failed. The text names no host, user, password or key, so it may be shown to a
    viewer: it is either a fixed sentence of this file or the message the database itself sent.
    Connection details (host, user; never a password or a key) go to the log.

    answered: True when the call was refused for what it carried (bad data), by the database or by
    the driver before it was sent; False when the database was not reached, or the call failed for a
    reason that another call would meet as well."""

    def __init__(self, text, answered=False):
        super().__init__(text)
        self.answered = answered


def rpc(fn, params=None):
    """Call the SQL function `fn` with named parameters and return its (JSON) result."""
    params = params or {}
    if not _FUNCTION.fullmatch(fn) or not all(_PARAMETER.fullmatch(name) for name in params):
        raise DbError("bad function or parameter name in a call of %r" % (fn,))
    # stripped: a value pasted into a host's settings easily ends with a space or a newline
    url, key = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if url and key:
        return _rpc_https(url, key, fn, params)
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        return _rpc_postgres(dsn, fn, params)
    raise DbError("no database configured: set SUPABASE_URL and SUPABASE_SECRET_KEY, or DATABASE_URL")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is never followed: the key rides on every request and must not travel to another address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                                            # urllib then raises the 3xx as an HTTPError


def _rpc_https(url, key, fn, params):
    if not (url.startswith("https://") or _LOCAL_HTTP.fullmatch(url)):
        raise DbError("SUPABASE_URL must start with https://")          # the key would travel in clear text
    data = json.dumps(params).encode("utf-8")
    try:
        request = urllib.request.Request(
            "%s/rest/v1/rpc/%s" % (url.rstrip("/"), fn), data=data,
            headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            raise DbError("HTTP %d: the database address answers with a redirect; check SUPABASE_URL" % e.code) from None
        try:
            message = json.loads(e.read())["message"]          # PostgREST explains itself in the body
        except (ValueError, KeyError, TypeError, OSError):
            message = None
        # 400 and 409 are PostgREST's statuses for an SQL error about the data of this very call
        raise DbError("HTTP %d: %s" % (e.code, message or e.reason), answered=e.code in (400, 409)) from None
    except (OSError, http.client.HTTPException) as e:          # no route, TLS, timeout, broken answer
        log.warning("database call %s failed: %r", fn, e)
        cause = getattr(e, "reason", e)                        # URLError wraps the real failure
        name = type(cause if isinstance(cause, Exception) else e).__name__
        raise DbError("database unreachable (%s)" % name) from None
    except ValueError:                                         # also UnicodeError. The text of such an error quotes
        raise DbError("the database address or key is malformed") from None    # the address or the key: never passed on
    try:
        return json.loads(body) if body else None
    except ValueError:
        raise DbError("the database API did not answer with JSON") from None


def _rpc_postgres(dsn, fn, params):
    import psycopg                                             # only this transport needs the driver
    from psycopg.types.json import Jsonb

    sql = "select %s(%s)" % (fn, ", ".join(name + " => %s" for name in params))
    values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in params.values()]

    def connect():
        # autocommit and no server-side prepared statements: works behind a transaction pooler
        _thread.conn = psycopg.connect(dsn, autocommit=True, prepare_threshold=None, connect_timeout=TIMEOUT)
        return _thread.conn

    connecting = True                                          # which step an error without a message comes from
    try:
        conn = getattr(_thread, "conn", None)
        reused = conn is not None and not conn.closed
        if not reused:
            conn = connect()
        connecting = False
        try:
            return conn.execute(sql, values).fetchone()[0]
        except psycopg.OperationalError:
            if not (reused and conn.closed):
                raise
            connecting = True
            conn = connect()                                   # an idle connection was dropped: once more
            connecting = False
            return conn.execute(sql, values).fetchone()[0]
    except psycopg.OperationalError as e:
        log.warning("database call %s failed: %s", fn, e)       # the full text (host, user) stays in the log
        raise DbError(e.diag.message_primary or "database unreachable") from None
    except psycopg.Error as e:
        if e.diag.message_primary:
            # SQLSTATE classes 22, 23 and P0: a data exception, a broken constraint, a "raise exception"
            raise DbError(e.diag.message_primary, answered=(e.sqlstate or "")[:2] in ("22", "23", "P0")) from None
        # Only what the database itself said is passed on. An error without such a message was raised on
        # this side. While connecting, its text can quote the connection string with its password (a "%"
        # in the password, quotes pasted around the address): it goes neither to the viewer nor to the log.
        if connecting:
            log.warning("database call %s failed: %s (is DATABASE_URL well formed?)", fn, type(e).__name__)
            raise DbError("database call failed (%s): check DATABASE_URL" % type(e).__name__) from None
        # Raised while the call was being sent: the driver refused one of its values (a NUL in a text, a
        # value it cannot convert). That is the call's own fault, not the connection's.
        log.warning("database call %s failed: %s (a value of the call cannot be sent)", fn, type(e).__name__)
        raise DbError("database call failed (%s): the call carried a value the database cannot store"
                      % type(e).__name__, answered=True) from None
