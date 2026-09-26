"""Redirect bypass of the async pagination origin guard (#2230 follow-up).

Commit 416a6951e added ``_evaluate_pagination_next_link`` so a pagination link
read out of an upstream's RESPONSE BODY cannot carry the caller's credentials to
an arbitrary host. The guard was BYPASSABLE, because it authorized a *link* and
not a *destination*:

**F1 (CRITICAL) — redirect laundering.** ``AsyncHTTPRequestNode.async_run``
never set ``allow_redirects`` (``grep -n allow_redirects http.py`` → no matches),
so aiohttp's default applied — ``inspect.signature(
aiohttp.ClientSession._request).parameters['allow_redirects'].default`` is
``True``. A hostile upstream therefore returned a next link on its OWN origin
(passing rule 4, headers forwarded UNCHANGED) and answered it with
``302 Location: http://attacker.example/``. aiohttp followed that automatically
and the only credential header it drops on a cross-host redirect is
``Authorization`` (``headers.pop(hdrs.AUTHORIZATION, None)``) — so ``Cookie``,
``X-API-Key``, ``X-Auth-Token``, ``api-key`` and the caller's configured
``api_key_header`` were all delivered to the attacker. The link-local rejection
in rule 3 was defeated outright: the guard never saw the redirect target.

**F2 (MED) — credential stripping was not sticky.** An allow-listed cross-origin
hop got credentials stripped, but an absolute link from that origin back to the
ORIGINAL origin matched rule 4 again and was fetched with FULL credentials —
laundering the third party back into the trusted position.

**F3 (MED) — log injection.** The rejection log rendered the rejected link
through ``mask_error_text``, which masks credentials but leaves control
characters intact (verified: ``mask_error_text('http://user:secret@[::1\\r\\n…')``
→ ``'http://***@[::1\\r\\nFORGED'``), so CR/LF in a rejected link forged log
lines. Note the injection only reaches the log through the branches that render
the RAW link (missing/empty, unparseable): ``urlsplit`` strips ``\\t\\r\\n`` from
anything it successfully parses.

**Why the F1 assertions are not vacuous.** The transport double cannot emulate
aiohttp's auto-follow — aiohttp does that, not the node. So "no call reached the
attacker" alone would pass vacuously. The F1 proof therefore has three legs that
only hold together:

1. the follow-up is ASKED to send ``allow_redirects=False`` (auto-follow off),
2. that kwarg demonstrably reaches the real ``aiohttp``/``requests`` call — the
   transport pins below drive the REAL nodes against a fake session, so a kwarg
   silently swallowed by ``**kwargs`` REDS here,
3. the node itself processes 3xx: a SAME-ORIGIN ``Location`` IS followed. Leg 3
   is what makes "the attacker was not called" a decision rather than an
   absence — the redirect path is live and it rejected that destination.

Every transport double is built from the REAL declared type: an actual
``HTTPResponse(...).model_dump()`` nested under ``"response"``, the shape
``AsyncHTTPRequestNode.async_run`` genuinely returns.
"""

import logging
import pathlib
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import pytest

from kailash.nodes.api import http as http_module
from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPRequestNode, HTTPResponse
from kailash.nodes.api.rest import RESTClientNode

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"
ATTACKER = "http://attacker.example/"
METADATA = "http://169.254.169.254/latest/meta-data/"

# Credential headers the caller sends. `Authorization` is the ONLY one aiohttp
# drops on a cross-host redirect; the rest are the payload of F1.
CREDENTIAL_HEADERS = {
    "Authorization": "Bearer super-secret-token",
    "Cookie": "session=super-secret-cookie",
    "X-API-Key": "super-secret-api-key",
}


def test_source_under_test_is_this_checkout():
    """Pin the import path to THIS checkout, wherever it is.

    pytest silently imports a different tree when ``pythonpath`` resolves
    elsewhere — the main checkout from inside a linked worktree, or an installed
    site-packages copy from anywhere — which would make every assertion below a
    statement about code this file never edited.

    The anchor is derived from THIS FILE's location rather than hard-coded, so
    the pin survives the worktree being reaped. The original form asserted a
    literal ``/.kailash-py-wt/rest/src/`` and went red the moment the lane's
    worktree was removed and the work landed on the trunk — pinning the
    authoring location rather than the invariant.
    """
    from kailash.nodes.api import rest as rest_module

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    module_path = pathlib.Path(rest_module.__file__).resolve()

    assert module_path.is_relative_to(repo_root / "src"), (
        f"kailash.nodes.api.rest resolved to {module_path}, which is not under "
        f"{repo_root / 'src'} — the assertions below would describe a different tree"
    )


def transport_return(content, *, headers=None, status=200, url=FULL_URL):
    """Build a return value the way the REAL transport builds it."""
    response = HTTPResponse(
        status_code=status,
        headers=dict(headers or {"Content-Type": "application/json"}),
        content_type="application/json",
        content=content,
        response_time_ms=12.5,
        url=url,
    ).model_dump()
    return {
        "response": response,
        "status_code": status,
        "success": 200 <= status < 300,
    }


def redirect_return(location, *, status=302, url=FULL_URL):
    """A 3xx the way the real transport returns it: no raise, success=False."""
    headers = {"Content-Type": "text/html"}
    if location is not None:
        headers["Location"] = location
    return transport_return("", headers=headers, status=status, url=url)


def page(items, next_link=None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": list(items)}
    if next_link is not None:
        body["links"] = {"next": next_link}
    return body


class RoutingAsyncTransport:
    """Stand-in for ``_async_http_node`` that answers BY URL and records calls.

    Routing by URL (rather than by call order) is what lets a redirect loop be
    exercised: the same URL can answer the same 302 every time.
    """

    def __init__(self, routes, default=None):
        self.routes = dict(routes)
        self.default = default
        self.calls: list[dict[str, Any]] = []

    async def async_run(self, **kwargs):
        self.calls.append(kwargs)
        url = kwargs.get("url")
        if url in self.routes:
            answer = self.routes[url]
            if isinstance(answer, list):
                answer = answer.pop(0) if len(answer) > 1 else answer[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        if self.default is not None:
            return self.default
        return transport_return(page([]), url=str(url))

    @property
    def urls(self):
        return [call.get("url") for call in self.calls]

    def calls_to(self, prefix):
        return [c for c in self.calls if str(c.get("url", "")).startswith(prefix)]


def make_node(transport):
    node = RESTClientNode()
    node._async_http_node = transport  # type: ignore[attr-defined]
    return node


async def paginate(transport, *, headers=None, allowed_origins=None, max_pages=10):
    node = make_node(transport)
    initial = transport_return(
        page([{"id": 1}], next_link=f"{BASE}/items?page=2"), url=FULL_URL
    )
    kwargs = {
        "headers": dict(CREDENTIAL_HEADERS if headers is None else headers),
        "paginate": True,
        "pagination_params": {"max_pages": max_pages},
    }
    if allowed_origins is not None:
        kwargs["allowed_pagination_origins"] = allowed_origins
    result = node._build_async_result(initial, FULL_URL, "GET")
    return await node._handle_async_pagination(result, kwargs)


# ---------------------------------------------------------------------------
# H1 — transport plumbing: allow_redirects must REACH the real client call
# ---------------------------------------------------------------------------


class _FakeAiohttpResponse:
    def __init__(self, payload, headers, status, url):
        self._payload = payload
        self.headers = dict(headers)
        self.status = status
        self.url = url

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)

    async def read(self):
        return str(self._payload).encode()


class _FakeAsyncSession:
    def __init__(self, response):
        self._response = response
        self.requests: list[dict[str, Any]] = []

    def request(self, **kwargs):
        self.requests.append(kwargs)
        response = self._response

        @asynccontextmanager
        async def _cm():
            yield response

        return _cm()


class _FakeAsyncPool:
    def __init__(self, session):
        self._session = session

    def acquire(self):
        session = self._session

        @asynccontextmanager
        async def _cm():
            yield session

        return _cm()


class _FakeSyncResponse:
    def __init__(self, payload, headers, status, url):
        self._payload = payload
        self.headers = dict(headers)
        self.status_code = status
        self.url = url
        self.text = str(payload)
        self.content = str(payload).encode()

    def json(self):
        return self._payload


class _FakeSyncSession:
    def __init__(self, response):
        self._response = response
        self.requests: list[dict[str, Any]] = []

    def request(self, **kwargs):
        self.requests.append(kwargs)
        return self._response


class _FakeSyncPool:
    def __init__(self, session):
        self._session = session

    def acquire(self):
        session = self._session

        @contextmanager
        def _cm():
            yield session

        return _cm()


def test_http_node_declares_allow_redirects_defaulting_true():
    """The node declares the input, and the DEFAULT preserves today's behavior."""
    params = HTTPRequestNode().get_parameters()
    assert "allow_redirects" in params, sorted(params)
    assert params["allow_redirects"].type is bool
    assert params["allow_redirects"].default is True
    # The async node reuses the sync declaration; pin that it stays in sync.
    assert "allow_redirects" in AsyncHTTPRequestNode().get_parameters()


async def test_async_transport_forwards_allow_redirects_to_aiohttp(monkeypatch):
    """CONTRACT PIN: the kwarg reaches ``aiohttp``'s own ``session.request``.

    Without this, ``allow_redirects=False`` could be silently absorbed by
    ``async_run(**kwargs)`` and aiohttp's ``True`` default would still apply —
    the bypass would be untouched while every node-level test went green.
    """
    session = _FakeAsyncSession(
        _FakeAiohttpResponse(
            {"ok": True}, {"Content-Type": "application/json"}, 200, FULL_URL
        )
    )
    monkeypatch.setattr(
        http_module, "_async_http_session_pool", _FakeAsyncPool(session)
    )

    await AsyncHTTPRequestNode().async_run(
        url=FULL_URL, method="GET", allow_redirects=False
    )
    assert session.requests[0]["allow_redirects"] is False

    await AsyncHTTPRequestNode().async_run(url=FULL_URL, method="GET")
    assert session.requests[1]["allow_redirects"] is True


def test_sync_transport_forwards_allow_redirects_to_requests(monkeypatch):
    """CONTRACT PIN on the sync sibling: the kwarg reaches ``requests``."""
    session = _FakeSyncSession(
        _FakeSyncResponse(
            {"ok": True}, {"Content-Type": "application/json"}, 200, FULL_URL
        )
    )
    monkeypatch.setattr(http_module, "_http_session_pool", _FakeSyncPool(session))

    HTTPRequestNode().run(url=FULL_URL, method="GET", allow_redirects=False)
    assert session.requests[0]["allow_redirects"] is False

    HTTPRequestNode().run(url=FULL_URL, method="GET")
    assert session.requests[1]["allow_redirects"] is True


# ---------------------------------------------------------------------------
# H1 — the attack
# ---------------------------------------------------------------------------


async def test_pagination_followup_disables_automatic_redirects():
    """Leg 1: every pagination follow-up asks the transport NOT to auto-follow."""
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": transport_return(
                page([{"id": 2}]), url=f"{BASE}/items?page=2"
            )
        }
    )
    await paginate(transport)

    assert transport.calls, "no follow-up request was issued"
    for call in transport.calls:
        assert (
            call.get("allow_redirects") is False
        ), f"follow-up to {call.get('url')} left redirects on: {call}"


async def test_same_origin_redirect_to_attacker_never_receives_credentials():
    """F1: the same-origin link answers 302 → attacker. Nothing may reach it."""
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": redirect_return(
                ATTACKER, url=f"{BASE}/items?page=2"
            ),
            ATTACKER: transport_return(page([{"id": "stolen"}]), url=ATTACKER),
        }
    )
    await paginate(transport)

    leaked = transport.calls_to("http://attacker.example")
    assert leaked == [], f"credentials sent to the attacker: {leaked}"
    # Stated the other way round, against the credential payload itself: no
    # request carrying Cookie/X-API-Key was aimed anywhere but the origin.
    for call in transport.calls:
        headers = call.get("headers") or {}
        if set(headers) & {"Cookie", "X-API-Key"}:
            assert str(call.get("url", "")).startswith(BASE), call


async def test_redirect_to_link_local_metadata_is_rejected():
    """F1 variant: rule 3 (link-local) now sees the redirect target."""
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": redirect_return(
                METADATA, url=f"{BASE}/items?page=2"
            ),
            METADATA: transport_return(page([{"id": "imds"}]), url=METADATA),
        }
    )
    await paginate(transport)

    assert transport.calls_to("http://169.254.169.254") == []


async def test_same_origin_redirect_is_followed_as_a_guarded_hop():
    """Leg 3: the redirect path is LIVE — a same-origin 302 IS followed."""
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": redirect_return(
                f"{BASE}/items?page=2&moved=1", url=f"{BASE}/items?page=2"
            ),
            f"{BASE}/items?page=2&moved=1": transport_return(
                page([{"id": 2}]), url=f"{BASE}/items?page=2&moved=1"
            ),
        }
    )
    result = await paginate(transport)

    assert f"{BASE}/items?page=2&moved=1" in transport.urls, transport.urls
    followed = transport.calls_to(f"{BASE}/items?page=2&moved=1")[0]
    assert followed["headers"]["Authorization"] == CREDENTIAL_HEADERS["Authorization"]
    assert result["data"] == [{"id": 1}, {"id": 2}]


async def test_redirect_loop_is_bounded():
    """A self-referential 302 must not spin."""
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": redirect_return(
                f"{BASE}/items?page=2", url=f"{BASE}/items?page=2"
            )
        }
    )
    await paginate(transport)

    assert len(transport.calls) <= 6, f"{len(transport.calls)} hops: {transport.urls}"


async def test_missing_location_stops_pagination_with_a_warning(caplog):
    """Fail closed: a 3xx with no ``Location`` stops, loudly."""
    transport = RoutingAsyncTransport(
        {f"{BASE}/items?page=2": redirect_return(None, url=f"{BASE}/items?page=2")}
    )
    with caplog.at_level(logging.WARNING):
        result = await paginate(transport)

    assert len(transport.calls) == 1, transport.urls
    assert any(
        "redirect" in record.getMessage().lower() for record in caplog.records
    ), [r.getMessage() for r in caplog.records]
    assert result["data"] == [{"id": 1}]


# ---------------------------------------------------------------------------
# H2 — credential stripping is STICKY for the rest of the run
# ---------------------------------------------------------------------------


async def test_credential_stripping_is_sticky_after_leaving_the_origin():
    """F2: a hop back to the ORIGINAL origin must NOT win the credentials back."""
    partner = "https://partner.example"
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": transport_return(
                page([{"id": 2}], next_link=f"{partner}/items?page=3"),
                url=f"{BASE}/items?page=2",
            ),
            f"{partner}/items?page=3": transport_return(
                page([{"id": 3}], next_link=f"{BASE}/items?page=4"),
                url=f"{partner}/items?page=3",
            ),
            f"{BASE}/items?page=4": transport_return(
                page([{"id": 4}]), url=f"{BASE}/items?page=4"
            ),
        }
    )
    await paginate(transport, allowed_origins=[partner])

    partner_headers = transport.calls_to(f"{partner}/items?page=3")[0]["headers"]
    assert set(partner_headers) & set(CREDENTIAL_HEADERS) == set(), partner_headers

    back_home = transport.calls_to(f"{BASE}/items?page=4")
    assert back_home, f"the run stopped early: {transport.urls}"
    returned_headers = back_home[0]["headers"]
    assert (
        set(returned_headers) & set(CREDENTIAL_HEADERS) == set()
    ), f"credentials re-attached after leaving the origin: {returned_headers}"


async def test_credential_stripping_is_sticky_across_a_redirect():
    """The sticky rule also survives a 3xx hop (redirects use the same path)."""
    partner = "https://partner.example"
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": transport_return(
                page([{"id": 2}], next_link=f"{partner}/items?page=3"),
                url=f"{BASE}/items?page=2",
            ),
            f"{partner}/items?page=3": redirect_return(
                f"{BASE}/items?page=4", url=f"{partner}/items?page=3"
            ),
            f"{BASE}/items?page=4": transport_return(
                page([{"id": 4}]), url=f"{BASE}/items?page=4"
            ),
        }
    )
    await paginate(transport, allowed_origins=[partner])

    back_home = transport.calls_to(f"{BASE}/items?page=4")
    assert back_home, f"the redirect hop was not followed: {transport.urls}"
    assert set(back_home[0]["headers"]) & set(CREDENTIAL_HEADERS) == set(), back_home[
        0
    ]["headers"]


async def test_first_hop_still_forwards_credentials_same_origin():
    """No silent narrowing: the ordinary same-origin case is unchanged."""
    transport = RoutingAsyncTransport(
        {
            f"{BASE}/items?page=2": transport_return(
                page([{"id": 2}]), url=f"{BASE}/items?page=2"
            )
        }
    )
    await paginate(transport)

    assert transport.calls[0]["headers"] == CREDENTIAL_HEADERS


# ---------------------------------------------------------------------------
# H3 — control characters in a rejected link cannot forge log lines
# ---------------------------------------------------------------------------

# `urlsplit` strips \t\r\n from anything it parses successfully, so the raw
# link only reaches the log through the missing/empty and unparseable branches.
# This one raises ValueError("Invalid IPv6 URL") — verified by execution — and
# carries BOTH a credential and a CRLF payload.
CRLF_LINK = "http://user:secret@[::1\r\n2026-09-12 WARNING forged log line"


async def test_rejected_link_control_chars_cannot_forge_log_lines(caplog):
    """F3: CR/LF are neutralized, and credential masking is KEPT."""
    transport = RoutingAsyncTransport({})
    node = make_node(transport)
    initial = transport_return(page([{"id": 1}], next_link=CRLF_LINK), url=FULL_URL)
    result = node._build_async_result(initial, FULL_URL, "GET")

    with caplog.at_level(logging.WARNING):
        await node._handle_async_pagination(
            result, {"headers": dict(CREDENTIAL_HEADERS), "paginate": True}
        )

    rejections = [
        r.getMessage() for r in caplog.records if "Pagination stopped" in r.getMessage()
    ]
    assert rejections, [r.getMessage() for r in caplog.records]
    message = rejections[0]
    assert "\n" not in message and "\r" not in message, repr(message)
    assert "\\x0d\\x0a" in message, repr(message)
    # Credential masking survives the sanitization.
    assert "secret" not in message, repr(message)
    assert "***" in message, repr(message)


async def test_empty_link_rejection_is_also_sanitized(caplog):
    """The other raw-rendering branch: a control-character-only link.

    (``"\\r\\n\\tINJECTED"`` would NOT reach this branch -- ``.strip()`` leaves
    ``"INJECTED"``, a legal relative link. Only a link that is control
    characters all the way through renders raw here.)
    """
    transport = RoutingAsyncTransport({})
    node = make_node(transport)
    initial = transport_return(page([{"id": 1}], next_link="\r\n\t"), url=FULL_URL)
    result = node._build_async_result(initial, FULL_URL, "GET")

    with caplog.at_level(logging.WARNING):
        await node._handle_async_pagination(
            result, {"headers": dict(CREDENTIAL_HEADERS), "paginate": True}
        )

    rejections = [
        r.getMessage() for r in caplog.records if "Pagination stopped" in r.getMessage()
    ]
    assert rejections, [r.getMessage() for r in caplog.records]
    assert "\n" not in rejections[0] and "\r" not in rejections[0], repr(rejections[0])
