"""Transport-layer credential containment for ``kailash.nodes.api.http``.

Two findings, one file, because they are the same leak read at two depths: a
session credential that the transport hands onward without the caller ever
asking for it.

S-HIGH-2 — cookie jars defeat the origin guard from underneath
--------------------------------------------------------------
``_http_session_pool`` and ``_async_http_session_pool`` are PROCESS-GLOBAL
pools. ``ResourcePool.acquire`` hands out a pooled object and appends the SAME
object back on release, so a ``requests.Session`` / ``aiohttp.ClientSession``
cookie jar persists across calls and across unrelated workflows.

Two live consequences:

1. ``RESTClientNode``'s pagination origin guard strips the ``Cookie`` HEADER on
   a cross-origin hop (``rest.py::_strip_credential_headers``), but the
   session's own jar re-attaches the origin's session cookie BELOW that strip.
   An allow-listed partner returning a link back to the ORIGINAL origin gets an
   authenticated, attacker-directed request — exactly the laundering the guard's
   sticky rule exists to prevent.
2. The jar is global across every caller, so one workflow's cookies attach to a
   different workflow's request to the same host.

S-MED-5 — response headers returned to callers unredacted
----------------------------------------------------------
Both response builders did ``HTTPResponse(headers=dict(response.headers), ...)``.
That dict surfaces to workflow callers as ``metadata["headers"]``, which is
logged and persisted — carrying ``Set-Cookie``, which this very file calls "a
session credential" at the log sink one layer down, where it IS redacted.
Masking at the log surface only is the ``observability.md`` Rule 6.3 failure.

Discrimination
--------------
Every assertion is written so it can return the OTHER answer:

* The cookie tests assert on the REAL jar of the REAL object the factory
  produces, driven by a REAL loopback HTTP server that really emits
  ``Set-Cookie`` — not on a mock's call record. An unfixed factory reds them
  with the stored cookie's value in the message.
* ``test_sync_send_suppressed_even_if_jar_is_seeded_directly`` is the mechanism
  discriminator. A policy-only fix (``DefaultCookiePolicy(allowed_domains=[])``
  or a ``set_ok``/``return_ok`` subclass installed via ``set_policy``) passes
  every OTHER cookie test here and FAILS this one, because ``requests``
  rebuilds a fresh default-policy ``RequestsCookieJar`` at prepare time
  (``Session.prepare_request`` → ``merge_cookies(merge_cookies(RequestsCookieJar(),
  self.cookies), cookies)``), so the session jar's ``return_ok`` never governs
  the outbound direction. Measured, not assumed.
* ``test_explicit_cookie_header_still_reaches_the_wire`` (both transports) and
  ``test_benign_headers_survive_redaction`` are the NO-FALSE-POSITIVE poles:
  they fail on an over-broad fix that strips cookies the caller deliberately
  set, or that redacts the whole header map.
* ``Link`` is asserted intact because ``rest.py::_extract_links`` /
  ``_extract_metadata`` parse pagination out of ``metadata["headers"]``;
  clobbering it would silently break pagination while every redaction
  assertion stayed green.
"""

import asyncio
import http.cookiejar
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import pytest
import requests

from kailash.nodes.api.http import (
    AsyncHTTPRequestNode,
    HTTPRequestNode,
    _async_http_session_pool,
    _http_session_pool,
)

COOKIE_NAME = "sid"
COOKIE_VALUE = "SECRET-SESSION-VALUE"
SET_COOKIE = f"{COOKIE_NAME}={COOKIE_VALUE}; Path=/"


def test_source_under_test_is_this_checkout():
    """Pin the import path to THIS checkout, wherever it is.

    pytest silently imports a different tree when ``pythonpath`` resolves
    elsewhere — the main checkout from inside a linked worktree, or an
    installed site-packages copy from anywhere — which would make every
    assertion below a statement about code this file never edited. Measured
    live in this session: a bare ``python -c`` from the worktree root imported
    ``site-packages/kailash/utils/secure_logging.py``.

    The anchor is derived from THIS FILE's location, never hard-coded to a
    worktree path (see commit dab1b679d).
    """
    from kailash.nodes.api import http as http_module

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    module_path = pathlib.Path(http_module.__file__).resolve()

    assert module_path.is_relative_to(repo_root / "src"), (
        f"kailash.nodes.api.http resolved to {module_path}, which is not under "
        f"{repo_root / 'src'} — the assertions below would describe a different tree"
    )


class _CookieHandler(BaseHTTPRequestHandler):
    """Real origin that really sets a cookie and really records what it receives."""

    received_cookies: list = []

    def do_GET(self):  # noqa: N802 — stdlib-mandated name
        type(self).received_cookies.append(self.headers.get("Cookie"))
        body = json.dumps({"items": [1, 2]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", SET_COOKIE)
        self.send_header(
            "Link",
            f"<http://{self.server.server_address[0]}:"
            f'{self.server.server_address[1]}/items?page=2>; rel="next"',
        )
        self.send_header("X-Total-Count", "8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence the stderr access log
        return


@pytest.fixture
def origin():
    """A loopback origin. No external network; the cookie jar is the subject.

    The URL uses the HOSTNAME ``localhost``, never the IP literal, and that is
    load-bearing rather than cosmetic. ``aiohttp.CookieJar`` runs ``unsafe=False``
    by default, which REFUSES to store a cookie whose host is an IP address —
    measured: against ``http://127.0.0.1:<port>`` the unfixed async session held
    ``jar_len=0`` and the second hop sent no cookie, so the async suppression
    tests were green BEFORE the fix and proved nothing. Against
    ``http://localhost:<port>`` the same unfixed session held ``jar_len=1`` and
    the second hop sent ``sid=SECRET``. The hostname is what makes this
    instrument able to return the other answer.
    """
    _CookieHandler.received_cookies = []
    server = ThreadingHTTPServer(("localhost", 0), _CookieHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://localhost:{port}/items"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
async def fresh_async_pool():
    """Rebind the process-global async pool to THIS test's event loop.

    PRE-EXISTING, NOT INTRODUCED HERE and deliberately not fixed from this
    region: ``_async_http_session_pool`` is a module-level ``AsyncResourcePool``
    holding ``asyncio.Lock``/``Semaphore`` and pooled ``ClientSession`` objects
    that bind to the first loop that touches them. A second test with its own
    loop reuses them and raises ``RuntimeError: Event loop is closed`` from
    inside ``async_run``. Reported to the lane rather than repaired, because the
    fix belongs in ``utils/resource_manager.py``.
    """
    pool = _async_http_session_pool
    pool._pool.clear()
    pool._in_use.clear()
    pool._created_count = 0
    pool._lock = asyncio.Lock()
    pool._semaphore = asyncio.Semaphore(pool._max_size)
    yield
    for session in list(pool._pool):
        await session.close()
    pool._pool.clear()
    pool._in_use.clear()
    pool._created_count = 0


# --------------------------------------------------------------------------
# S-HIGH-2 — sync transport
# --------------------------------------------------------------------------


def test_sync_factory_session_stores_no_cookie(origin):
    """A response carrying ``Set-Cookie`` leaves the pooled session's jar EMPTY."""
    session = _http_session_pool._factory()
    try:
        response = session.get(origin)
        assert response.status_code == 200
        assert response.headers["Set-Cookie"] == SET_COOKIE, (
            "the origin must really be emitting Set-Cookie, or this test proves "
            "nothing about suppression"
        )
        assert len(session.cookies) == 0, (
            f"pooled session jar retained {dict(session.cookies)!r}; a process-global "
            f"pooled jar carries {COOKIE_NAME} into every later caller's request"
        )
    finally:
        session.close()


def test_sync_second_request_through_same_session_sends_no_cookie(origin):
    """The hop AFTER the Set-Cookie carries no ``Cookie`` header.

    This is the origin-guard bypass in its smallest form: hop 2 is the one
    ``rest.py::_strip_credential_headers`` believes it has de-credentialed.
    """
    session = _http_session_pool._factory()
    try:
        session.get(origin)
        session.get(origin)
    finally:
        session.close()

    assert _CookieHandler.received_cookies[0] is None
    assert _CookieHandler.received_cookies[1] is None, (
        f"second hop through the pooled session sent "
        f"{_CookieHandler.received_cookies[1]!r} — the jar re-attached the session "
        f"credential below the header strip"
    )


def test_sync_send_suppressed_even_if_jar_is_seeded_directly(origin):
    """MECHANISM DISCRIMINATOR — a policy-only fix fails here.

    ``requests.Session.prepare_request`` copies the session jar into a FRESH
    ``RequestsCookieJar()`` carrying the DEFAULT policy, so a ``return_ok``
    override installed via ``set_policy`` never governs the outbound direction.
    Measured against both candidate policies before the fix was chosen. Only a
    jar that refuses to hold a cookie at all suppresses BOTH directions
    unconditionally.
    """
    session = _http_session_pool._factory()
    try:
        session.cookies.set(
            COOKIE_NAME, COOKIE_VALUE, domain="localhost.local", path="/"
        )
        assert len(session.cookies) == 0, (
            f"direct set() seeded the pooled jar with {dict(session.cookies)!r}; a "
            f"policy-only suppression leaves this route open"
        )
        session.get(origin)
    finally:
        session.close()

    assert _CookieHandler.received_cookies[0] is None, (
        f"seeded jar sent {_CookieHandler.received_cookies[0]!r} — suppression does "
        f"not hold on the send path"
    )


def test_sync_explicit_cookie_header_still_reaches_the_wire(origin):
    """NO-FALSE-POSITIVE POLE — a caller who asks for a cookie still gets one."""
    session = _http_session_pool._factory()
    try:
        session.get(origin, headers={"Cookie": "explicit=YES"})
    finally:
        session.close()

    assert _CookieHandler.received_cookies[0] == "explicit=YES", (
        "suppressing the ambient jar must not suppress a cookie the caller set "
        "deliberately via headers"
    )


# --------------------------------------------------------------------------
# S-HIGH-2 — async transport
# --------------------------------------------------------------------------


async def test_async_factory_session_stores_no_cookie(origin):
    """``aiohttp`` side: the real jar the real factory builds stays empty."""
    session = _async_http_session_pool._factory()
    try:
        assert isinstance(session.cookie_jar, aiohttp.DummyCookieJar), (
            f"async factory built a {type(session.cookie_jar).__name__}; a storing "
            f"jar on a process-global pooled session is cross-caller contamination"
        )
        async with session.get(origin) as response:
            assert response.status == 200
            assert response.headers["Set-Cookie"] == SET_COOKIE
        assert (
            len(session.cookie_jar) == 0
        ), "pooled aiohttp session retained cookies from the response"
    finally:
        await session.close()


async def test_async_second_request_through_same_session_sends_no_cookie(origin):
    session = _async_http_session_pool._factory()
    try:
        async with session.get(origin):
            pass
        async with session.get(origin):
            pass
    finally:
        await session.close()

    assert _CookieHandler.received_cookies[0] is None
    assert _CookieHandler.received_cookies[1] is None, (
        f"second async hop sent {_CookieHandler.received_cookies[1]!r} — the pooled "
        f"jar re-attached the session credential"
    )


async def test_async_explicit_cookie_header_still_reaches_the_wire(origin):
    """NO-FALSE-POSITIVE POLE, async side."""
    session = _async_http_session_pool._factory()
    try:
        async with session.get(origin, headers={"Cookie": "explicit=YES"}):
            pass
    finally:
        await session.close()

    assert _CookieHandler.received_cookies[0] == "explicit=YES"


# --------------------------------------------------------------------------
# S-MED-5 — returned headers
# --------------------------------------------------------------------------


def test_sync_returned_headers_redact_set_cookie(origin):
    result = HTTPRequestNode().run(url=origin, method="GET")
    headers = result["response"]["headers"]

    assert headers.get("Set-Cookie") == "[REDACTED]", (
        f"HTTPResponse.headers returned Set-Cookie as {headers.get('Set-Cookie')!r}; "
        f"this dict surfaces as metadata['headers'] and is logged and persisted"
    )
    assert COOKIE_VALUE not in json.dumps(headers)


def test_sync_benign_headers_survive_redaction(origin):
    """NO-FALSE-POSITIVE POLE + the ``Link``-parsing contract rest.py depends on."""
    result = HTTPRequestNode().run(url=origin, method="GET")
    headers = result["response"]["headers"]

    assert headers.get("Content-Type") == "application/json"
    assert headers.get("X-Total-Count") == "8"
    assert 'rel="next"' in headers.get("Link", ""), (
        f"Link header came back as {headers.get('Link')!r} — rest.py::_extract_links "
        f"parses pagination out of this value"
    )
    # content_type is read from the RAW headers before redaction and must keep working
    assert result["response"]["content_type"] == "application/json"


async def test_async_returned_headers_redact_set_cookie(origin, fresh_async_pool):
    result = await AsyncHTTPRequestNode().async_run(url=origin, method="GET")
    headers = result["response"]["headers"]

    assert headers.get("Set-Cookie") == "[REDACTED]", (
        f"async HTTPResponse.headers returned Set-Cookie as "
        f"{headers.get('Set-Cookie')!r}"
    )
    assert COOKIE_VALUE not in json.dumps(headers)


async def test_async_benign_headers_survive_redaction(origin, fresh_async_pool):
    """NO-FALSE-POSITIVE POLE, async side."""
    result = await AsyncHTTPRequestNode().async_run(url=origin, method="GET")
    headers = result["response"]["headers"]

    assert headers.get("Content-Type") == "application/json"
    assert 'rel="next"' in headers.get("Link", "")
    assert result["response"]["content_type"] == "application/json"


def test_block_all_jar_is_a_real_cookiejar():
    """The suppression object must still satisfy every contract ``requests`` has.

    ``Session.send`` calls ``extract_cookies_to_jar``, redirect resolution calls
    ``merge_cookies``, and both assume a real ``http.cookiejar``-compatible jar.
    A bare stub would pass the behavioural assertions above and explode on the
    first redirect.
    """
    session = _http_session_pool._factory()
    try:
        assert isinstance(session.cookies, requests.cookies.RequestsCookieJar)
        assert isinstance(session.cookies, http.cookiejar.CookieJar)
        # the standard jar protocol must not raise
        assert list(session.cookies) == []
        session.cookies.clear()
    finally:
        session.close()


def test_structural_nav_headers_survive_redaction_byte_intact():
    """REVERSED at lane level, deliberately -- this replaces an earlier pin.

    An earlier revision routed response headers through ``redact_mapping``
    wholesale and PINNED the consequence that a credential-bearing ``Link`` /
    ``Location`` comes back masked, on the rationale that ``rest.py`` would then
    "follow a masked URL and fail loudly instead of silently re-sending the
    credential". That rationale was MEASURED and is false in the case that
    matters. ``redact_mapping`` runs each string leaf through the value-level
    URL masker, and when the credential is the LAST query parameter the masker
    consumes the closing ``>;`` delimiter with it::

        raw    = '<https://h/items?page=2&access_token=abc123>; rel="next"'
        masked = '<https://h/items?page=2&access_token=*** rel="next"'
        RESTClientNode._parse_link_header(masked) -> {}

    An empty parse is not a loud failure: the ``next`` link simply VANISHES,
    pagination stops, and page 1 is returned as the complete result set with
    nothing in the log to say so -- the silent-degradation class
    ``zero-tolerance.md`` Rule 3 forbids, and the very class the surrounding
    pagination work exists to remove. ``Location`` is worse still: the redirect
    guard consumes it, so a mangled value breaks redirect following outright.

    So ``_redact_response_headers`` exempts the STRUCTURAL navigation headers
    from value masking while keeping key-based redaction for everything else.
    What the returned-header finding actually named -- ``Set-Cookie`` -- is
    withheld by KEY and is unaffected by the exemption, which the companion
    tests above pin. A credential inside a pagination URL is the UPSTREAM's own
    placement in a URL it is handing back to us, and the origin guard in
    ``rest.py`` already stops those credentials from reaching a third party.
    """
    from kailash.nodes.api.http import _redact_response_headers
    from kailash.nodes.api.rest import RESTClientNode

    credential_last = (
        '<https://api.example.test/items?page=2&access_token=abc123>; rel="next"'
    )
    out = _redact_response_headers(
        {
            "Link": credential_last,
            "Location": "https://user:pw@api.example.test/next",
            "Set-Cookie": SET_COOKIE,
            "Content-Type": "application/json",
        }
    )

    # The navigation headers are byte-intact, so the SDK's own parsers still work.
    assert out["Link"] == credential_last
    assert out["Location"] == "https://user:pw@api.example.test/next"

    node = RESTClientNode.__new__(RESTClientNode)
    assert node._parse_link_header(out["Link"]) == {
        "next": "https://api.example.test/items?page=2&access_token=abc123"
    }

    # The OTHER pole: the exemption is by NAME and buys nothing for any other
    # header. `Set-Cookie` -- the credential the finding named -- is still gone.
    assert out["Set-Cookie"] == "[REDACTED]"
    assert "SECRET" not in out["Set-Cookie"]
    assert out["Content-Type"] == "application/json"


def test_nav_exemption_does_not_leak_into_the_logging_sink():
    """The exemption is scoped to the RETURNED surface, not to logging.

    ``redact_mapping`` is still what the log sinks call, so a credential-bearing
    `Link` is masked on its way to a log even though it is byte-intact on its way
    to the caller. Without this the exemption could be widened by accident into
    the sink it was never meant to touch.
    """
    from kailash.utils.secure_logging import redact_mapping

    raw = '<https://api.example.test/items?page=2&access_token=abc123>; rel="next"'
    assert "abc123" not in redact_mapping({"Link": raw})["Link"]
