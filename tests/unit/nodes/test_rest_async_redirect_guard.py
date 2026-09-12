"""Async half of the redirect-guard parity finding, plus the log-hygiene pair.

Commit 613468d4d landed an origin guard for redirect hops; a sibling then wired
it into BOTH synchronous request sites. ``AsyncRESTClientNode`` — the
``@register_node()`` async REST node users actually select — was left out:

**S-HIGH-1 (async half).** ``async_run``'s initial request reached
``AsyncHTTPRequestNode.async_run`` with ``allow_redirects`` at its default
``True`` (``http.py:923``), so aiohttp followed the server's ``Location`` for a
CREDENTIALED request. aiohttp keeps every header — ``Cookie``, ``X-API-Key`` and
the node's configured ``api_key_header`` — across a cross-host redirect, and
``http_params`` additionally carries ``auth_type``/``auth_token``/
``auth_username``/``auth_password``, which ``AsyncHTTPRequestNode`` injects as
headers ITSELF (``http.py::_apply_authentication``). Stripping the caller's
``headers`` dict alone would therefore still hand the credential to whatever
host the server named — including the link-local addresses the guard exists to
refuse.

**S-MED-4.** ``async_run``'s page/offset/cursor pagination runs the SYNCHRONOUS
``_paginate_with_page_count`` through ``asyncio.to_thread``. The guard the
sibling put into that sync path should therefore be INHERITED rather than
re-implemented — but "should be" is not a measurement, so it is measured here.

**S-MED-6.** ``rest.py``'s async initial request rendered the raw ``url`` into
an f-string at INFO. ``http.py:625`` does the identical thing correctly,
through ``mask_url``.

**S-MED-7.** ``error_message`` is lifted out of the RESPONSE BODY and was
logged raw, one module-level function away from ``_sanitize_for_log``.

**Why these assertions are not vacuous.** A transport double cannot emulate
aiohttp's auto-follow — the CLIENT does that, not the node. So "no call reached
the attacker" alone would pass vacuously. Each redirect proof therefore has
three legs that only hold together:

1. the request is ASKED to send ``allow_redirects=False``,
2. the double is shown able to record the OTHER value
   (``test_control_double_records_allow_redirects_true``), so an assertion of
   ``False`` is a reading and not a constant,
3. the node itself processes 3xx: a SAME-ORIGIN ``Location`` IS followed, WITH
   credentials. Leg 3 is what makes "the metadata endpoint was not called" a
   decision rather than an absence.

Every transport double is built from the REAL declared type: an actual
``HTTPResponse(...).model_dump()`` nested under ``"response"``.
"""

import logging
import pathlib
from typing import Any

import pytest

from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPRequestNode, HTTPResponse
from kailash.nodes.api.rest import (
    _MAX_REDIRECT_HOPS,
    AsyncRESTClientNode,
    RESTClientNode,
)

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"
CDN = "https://cdn.example.net/items"
CDN_ORIGIN = "https://cdn.example.net"
METADATA = "http://169.254.169.254/latest/meta-data/"
LOOPBACK = "http://127.0.0.1:9000/steal"

CREDENTIAL_HEADERS = {
    "Authorization": "Bearer super-secret-token",
    "Cookie": "session=super-secret-cookie",
    "X-API-Key": "super-secret-api-key",
}
NODE_AUTH_TOKEN = "super-secret-node-token"
CREDENTIAL_VALUES = tuple(CREDENTIAL_HEADERS.values()) + (NODE_AUTH_TOKEN,)


def test_source_under_test_is_this_checkout():
    """Pin the import path to THIS checkout, wherever it is.

    The anchor is derived from THIS FILE's location rather than hard-coded, so
    the pin survives the worktree being reaped (commit dab1b679d pinned an
    authoring location and went red when it was removed).
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


def page(items, *, total=None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": list(items)}
    if total is not None:
        body["meta"] = {"total": total}
    return body


class RoutingAsyncTransport:
    """Stand-in for the async transport that answers BY URL, recording calls."""

    def __init__(self, routes=None, default=None):
        self.routes = dict(routes or {})
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
        if callable(self.default):
            return self.default(url)
        if self.default is not None:
            return self.default
        return transport_return(page([]), url=str(url))

    @property
    def urls(self):
        return [call.get("url") for call in self.calls]

    def call_to(self, url):
        return next(c for c in self.calls if c.get("url") == url)


class RoutingSyncTransport:
    """Stand-in for ``rest_node.http_node`` — the sync pagination transport."""

    def __init__(self, routes=None, default=None):
        self.routes = dict(routes or {})
        self.default = default
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        url = kwargs.get("url")
        if url in self.routes:
            answer = self.routes[url]
            if isinstance(answer, list):
                answer = answer.pop(0) if len(answer) > 1 else answer[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        if callable(self.default):
            return self.default(url)
        if self.default is not None:
            return self.default
        return transport_return(page([]), url=str(url))

    @property
    def urls(self):
        return [call.get("url") for call in self.calls]

    def call_to(self, url):
        return next(c for c in self.calls if c.get("url") == url)


def make_node(async_transport, sync_transport=None):
    node = AsyncRESTClientNode()
    node.http_node = async_transport
    if sync_transport is not None:
        node.rest_node.http_node = sync_transport
    return node


def call_kwargs(**overrides):
    kwargs = {
        "base_url": BASE,
        "resource": RESOURCE,
        "headers": dict(CREDENTIAL_HEADERS),
        "auth_type": "bearer",
        "auth_token": NODE_AUTH_TOKEN,
    }
    kwargs.update(overrides)
    return kwargs


def credential_free(call: dict) -> bool:
    """No caller credential survives — in the HEADERS or in the auth kwargs.

    Rendering the WHOLE call (not just ``headers``) is deliberate: a test that
    inspected only the headers dict would pass while ``auth_token`` was still
    set, and ``AsyncHTTPRequestNode._apply_authentication`` would re-inject it
    as ``Authorization`` at the transport boundary.
    """
    rendered = repr(call)
    return not any(secret in rendered for secret in CREDENTIAL_VALUES)


# ---------------------------------------------------------------------------
# Leg 2 of every redirect proof: the instrument can record the OTHER value.
# ---------------------------------------------------------------------------


async def test_control_double_records_allow_redirects_true():
    """The double is shown able to emit the falsifying reading."""
    transport = RoutingAsyncTransport()
    await transport.async_run(url=FULL_URL, allow_redirects=True)
    assert transport.calls[0]["allow_redirects"] is True

    # ...and BOTH transports' own default is True, so False is a decision the
    # node makes, not a value it inherits.
    assert AsyncHTTPRequestNode().get_parameters()["allow_redirects"].default is True
    assert HTTPRequestNode().get_parameters()["allow_redirects"].default is True

    # ...and both controls are DECLARED on the async node, so a caller who
    # passes either does not have it silently dropped by parameter validation.
    params = AsyncRESTClientNode().get_parameters()
    assert "allow_redirects" in params
    assert "allowed_pagination_origins" in params


# ---------------------------------------------------------------------------
# S-HIGH-1 (async) — allow_redirects=False reaches the async transport
# ---------------------------------------------------------------------------


async def test_async_initial_request_disables_automatic_redirects():
    transport = RoutingAsyncTransport({FULL_URL: transport_return(page([{"id": 1}]))})
    await make_node(transport).async_run(**call_kwargs())

    assert transport.calls, "the initial request never reached the transport"
    assert transport.calls[0]["allow_redirects"] is False, (
        "async initial request left automatic redirect-following ON: the "
        "server's Location header chooses the destination for a credentialed "
        "request"
    )


async def test_async_same_origin_redirect_is_followed_with_credentials():
    """Leg 3, and the OTHER pole: a same-origin hop keeps the credentials."""
    same_origin_next = f"{BASE}/items/page-2"
    transport = RoutingAsyncTransport(
        {
            FULL_URL: redirect_return(same_origin_next),
            same_origin_next: transport_return(page([{"id": 2}]), url=same_origin_next),
        }
    )
    result = await make_node(transport).async_run(**call_kwargs())

    assert same_origin_next in transport.urls, (
        "a SAME-ORIGIN redirect was not followed — the node's redirect path is "
        "dead, so every 'the attacker was not called' assertion here would be "
        "vacuous"
    )
    followed = transport.call_to(same_origin_next)
    assert followed["headers"].get("Authorization") == (
        CREDENTIAL_HEADERS["Authorization"]
    ), "a same-origin redirect must keep the caller's credentials"
    assert followed.get("auth_token") == NODE_AUTH_TOKEN
    # ...and the FOLLOWED hop's body is what the caller receives, so the walk
    # really did terminate on the redirect target rather than on the 3xx.
    assert result["data"] == page([{"id": 2}])
    assert result["success"] is True


async def test_async_cross_origin_redirect_strips_credentials_and_auth_kwargs():
    transport = RoutingAsyncTransport(
        {
            FULL_URL: redirect_return(CDN),
            CDN: transport_return(page([{"id": 3}]), url=CDN),
        }
    )
    await make_node(transport).async_run(**call_kwargs())

    assert CDN in transport.urls, (
        "a caller-chosen cross-origin redirect was refused outright; CDN and "
        "vanity-domain redirects are routine and must be FOLLOWED, stripped"
    )
    hop = transport.call_to(CDN)
    assert credential_free(hop), (
        "a cross-origin redirect carried the caller's credentials to a "
        f"third-party origin: {hop!r}"
    )
    # The auth kwargs specifically: stripping `headers` alone is not enough,
    # because AsyncHTTPRequestNode._apply_authentication re-injects from these.
    assert hop.get("auth_type") is None, (
        "auth_type survived a credential-withheld hop; "
        "AsyncHTTPRequestNode._apply_authentication would re-inject "
        "Authorization from it at the transport boundary"
    )
    assert hop.get("auth_token") is None
    assert hop.get("auth_username") is None
    assert hop.get("auth_password") is None


async def test_async_redirect_to_metadata_endpoint_is_refused():
    transport = RoutingAsyncTransport(
        {
            FULL_URL: redirect_return(METADATA),
            METADATA: transport_return({"secret": "iam-role"}, url=METADATA),
        }
    )
    await make_node(transport).async_run(**call_kwargs())

    assert METADATA not in transport.urls, (
        "the async initial request followed a redirect to the cloud metadata "
        f"endpoint: {transport.urls!r}"
    )


async def test_async_redirect_to_loopback_is_refused():
    transport = RoutingAsyncTransport(
        {
            FULL_URL: redirect_return(LOOPBACK),
            LOOPBACK: transport_return({"secret": "local"}, url=LOOPBACK),
        }
    )
    await make_node(transport).async_run(**call_kwargs())

    assert (
        LOOPBACK not in transport.urls
    ), f"the async initial request followed a redirect to loopback: {transport.urls!r}"


async def test_async_redirect_chain_is_bounded():
    """The hop bound stops an unbounded same-origin redirect walk."""

    def hop(url):
        index = len(transport.calls)
        return redirect_return(f"{BASE}/items/hop-{index}", url=str(url))

    transport = RoutingAsyncTransport(default=hop)
    await make_node(transport).async_run(**call_kwargs())

    assert len(transport.calls) == 1 + _MAX_REDIRECT_HOPS, (
        f"the redirect walk made {len(transport.calls)} requests; the bound is "
        f"1 initial + {_MAX_REDIRECT_HOPS} hops"
    )


async def test_async_redirect_without_location_fails_closed():
    transport = RoutingAsyncTransport({FULL_URL: redirect_return(None)})
    result = await make_node(transport).async_run(**call_kwargs())

    assert len(transport.calls) == 1
    assert result["success"] is False


# ---------------------------------------------------------------------------
# S-MED-6 — the request URL is masked at INFO
# ---------------------------------------------------------------------------


async def test_async_request_url_is_masked_in_the_log(caplog):
    secret_base = "https://svc:hunter2@api.example.com"
    transport = RoutingAsyncTransport(default=lambda url: transport_return(page([])))

    with caplog.at_level(logging.INFO):
        await make_node(transport).async_run(
            **call_kwargs(
                base_url=secret_base,
                query_params={"api_key": "super-secret-query-key"},
            )
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert (
        "hunter2" not in rendered
    ), f"the async request log rendered userinfo credentials verbatim: {rendered!r}"
    # The OTHER pole: masking must not blank the line out entirely.
    assert "api.example.com" in rendered, (
        "the host vanished from the log — the masking removed the diagnostic "
        f"value the line exists for: {rendered!r}"
    )


# ---------------------------------------------------------------------------
# S-MED-7 — a server-supplied error_message cannot forge log lines
# ---------------------------------------------------------------------------


async def test_async_error_message_is_sanitized_at_the_log_and_in_the_return(caplog):
    forged = "boom\r\nERROR kailash.security: all clear, nothing to see"
    transport = RoutingAsyncTransport(
        {
            FULL_URL: {
                "response": HTTPResponse(
                    status_code=500,
                    headers={"Content-Type": "application/json"},
                    content_type="application/json",
                    content={"error": forged},
                    response_time_ms=1.0,
                    url=FULL_URL,
                ).model_dump(),
                "status_code": 500,
                "success": False,
                "error": "HTTP 500",
            }
        }
    )

    with caplog.at_level(logging.ERROR):
        result = await make_node(transport).async_run(**call_kwargs())

    error_records = [r for r in caplog.records if "REST API error" in r.getMessage()]
    assert (
        len(error_records) == 1
    ), f"expected exactly one error record, got {len(error_records)}"
    message = error_records[0].getMessage()
    assert "\r" not in message and "\n" not in message, (
        "a server-supplied error_message put raw CR/LF into the log, letting "
        f"the upstream forge whole log lines: {message!r}"
    )
    assert (
        "\\x0d" in message and "\\x0a" in message
    ), f"control characters were dropped rather than made visible: {message!r}"
    # The sibling's sync site sanitizes ONCE and returns the sanitized value.
    # Matched here so the two paths cannot diverge.
    assert "\r" not in result["error"] and "\n" not in result["error"], (
        "the RETURNED error_message is still raw, which merely moves the forge "
        f"one hop downstream to the caller's own logger: {result['error']!r}"
    )
    # The OTHER pole: the message itself is not destroyed.
    assert "boom" in message and "boom" in result["error"]


def test_async_node_sync_run_inherits_the_sanitized_error_message():
    """``AsyncRESTClientNode.run`` has no error site of its own to fix.

    It forwards to ``self.rest_node.execute``, so the ONLY ``REST API error:``
    line it can produce is the synchronous one the sibling already sanitized.
    Measured rather than assumed: a CR/LF payload through this entry point must
    come back neutralized, or there is a second unfixed site here.
    """
    forged = "boom\r\nERROR kailash.security: all clear"
    transport = RoutingSyncTransport(
        {
            FULL_URL: {
                "response": HTTPResponse(
                    status_code=500,
                    headers={"Content-Type": "application/json"},
                    content_type="application/json",
                    content={"error": forged},
                    response_time_ms=1.0,
                    url=FULL_URL,
                ).model_dump(),
                "status_code": 500,
                "success": False,
                "error": "HTTP 500",
            }
        }
    )
    node = AsyncRESTClientNode()
    node.rest_node.http_node = transport

    result = node.run(**call_kwargs())

    assert (
        "\r" not in result["error"] and "\n" not in result["error"]
    ), f"the async node's sync entry point returned a raw CR/LF: {result['error']!r}"
    assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# S-MED-4 — the redirect guard is INHERITED by async pagination
# ---------------------------------------------------------------------------


def paginating_kwargs(**overrides):
    kwargs = call_kwargs(
        paginate=True,
        pagination_params={
            "type": "page",
            "items_path": "data",
            "total_path": "meta.total",
            "max_pages": 2,
        },
    )
    kwargs.update(overrides)
    return kwargs


async def test_async_pagination_followup_refuses_a_metadata_redirect():
    """Page 2 runs on the SYNC transport; the guard must cover it there."""
    async_transport = RoutingAsyncTransport(
        {FULL_URL: transport_return(page([{"id": 1}], total=99))}
    )
    sync_transport = RoutingSyncTransport(
        {
            FULL_URL: redirect_return(METADATA),
            METADATA: transport_return(page([{"id": "stolen"}]), url=METADATA),
        }
    )
    await make_node(async_transport, sync_transport).async_run(**paginating_kwargs())

    assert sync_transport.calls, "pagination never issued a follow-up page"
    assert METADATA not in sync_transport.urls, (
        "an AsyncRESTClientNode pagination follow-up followed a redirect to the "
        f"cloud metadata endpoint: {sync_transport.urls!r}"
    )
    assert all(c.get("allow_redirects") is False for c in sync_transport.calls), (
        "an async-node pagination follow-up left automatic redirect-following "
        f"ON: {[c.get('allow_redirects') for c in sync_transport.calls]}"
    )


async def test_async_pagination_followup_strips_credentials_cross_origin():
    async_transport = RoutingAsyncTransport(
        {FULL_URL: transport_return(page([{"id": 1}], total=99))}
    )
    sync_transport = RoutingSyncTransport(
        {
            FULL_URL: redirect_return(CDN),
            CDN: transport_return(page([{"id": 2}]), url=CDN),
        }
    )
    await make_node(async_transport, sync_transport).async_run(**paginating_kwargs())

    assert CDN in sync_transport.urls, (
        "the cross-origin pagination hop was refused outright — the OTHER pole "
        "of this proof is dead"
    )
    hop = sync_transport.call_to(CDN)
    assert credential_free(
        hop
    ), f"an async-node pagination follow-up leaked credentials cross-origin: {hop!r}"
    assert hop.get("auth_type") is None and hop.get("auth_token") is None


# ---------------------------------------------------------------------------
# The caller's allowlist REACHES the sync pagination redirect guard
#
# SCOPE, stated so these assertions are not over-read. Measured on the UNFIXED
# tree, `test_async_pagination_followup_strips_credentials_cross_origin` above
# already PASSED: because the sync pagination follow-up passes
# `caller_chosen=True`, `_evaluate_redirect_hop` appends the resolved target to
# its own effective allowlist, so a cross-origin hop was FOLLOWED (stripped),
# not refused. The threading below therefore closes a PARITY gap -- one run's
# two halves were guarded to different widths, and the narrower half only
# happened to coincide -- it does not change an observable refusal today. What
# these tests measure is exactly that: the caller's value REACHES the guard,
# and an omitted value is not invented.
# ---------------------------------------------------------------------------


def _spy_on_redirect_hop(monkeypatch):
    seen: list[dict[str, Any]] = []
    original = RESTClientNode._evaluate_redirect_hop

    def recording(self, hop_result, **kwargs):
        seen.append(dict(kwargs))
        return original(self, hop_result, **kwargs)

    monkeypatch.setattr(RESTClientNode, "_evaluate_redirect_hop", recording)
    return seen


def test_sync_pagination_threads_the_callers_allowlist(monkeypatch):
    """``RESTClientNode.run`` — the caller's allowlist reaches the hop guard."""
    seen = _spy_on_redirect_hop(monkeypatch)
    transport = RoutingSyncTransport(
        {
            FULL_URL: [
                transport_return(page([{"id": 1}], total=99)),
                redirect_return(CDN),
            ],
            CDN: transport_return(page([{"id": 2}]), url=CDN),
        }
    )
    node = RESTClientNode()
    node.http_node = transport
    node.run(
        **call_kwargs(
            paginate=True,
            allowed_pagination_origins=[CDN_ORIGIN],
            pagination_params={
                "type": "page",
                "items_path": "data",
                "total_path": "meta.total",
                "max_pages": 2,
            },
        )
    )

    assert seen, "no redirect hop was evaluated during sync pagination"
    assert any(call.get("allowed_origins") == [CDN_ORIGIN] for call in seen), (
        "the caller's allowed_pagination_origins never reached the sync "
        "pagination redirect guard; it ran with "
        f"{[c.get('allowed_origins') for c in seen]}"
    )


async def test_async_pagination_threads_the_callers_allowlist(monkeypatch):
    """``AsyncRESTClientNode.async_run`` — same thread, same allowlist."""
    seen = _spy_on_redirect_hop(monkeypatch)
    async_transport = RoutingAsyncTransport(
        {FULL_URL: transport_return(page([{"id": 1}], total=99))}
    )
    sync_transport = RoutingSyncTransport(
        {
            FULL_URL: redirect_return(CDN),
            CDN: transport_return(page([{"id": 2}]), url=CDN),
        }
    )
    await make_node(async_transport, sync_transport).async_run(
        **paginating_kwargs(allowed_pagination_origins=[CDN_ORIGIN])
    )

    assert seen, "no redirect hop was evaluated during async pagination"
    assert any(call.get("allowed_origins") == [CDN_ORIGIN] for call in seen), (
        "the caller's allowed_pagination_origins never reached the pagination "
        f"redirect guard on the async path; it ran with "
        f"{[c.get('allowed_origins') for c in seen]}"
    )


def test_omitted_allowlist_stays_none_and_fails_closed(monkeypatch):
    """The OTHER pole: an omitted allowlist is not invented."""
    seen = _spy_on_redirect_hop(monkeypatch)
    transport = RoutingSyncTransport(
        {
            FULL_URL: [
                transport_return(page([{"id": 1}], total=99)),
                redirect_return(METADATA),
            ],
            METADATA: transport_return(page([{"id": "stolen"}]), url=METADATA),
        }
    )
    node = RESTClientNode()
    node.http_node = transport
    node.run(
        **call_kwargs(
            paginate=True,
            pagination_params={
                "type": "page",
                "items_path": "data",
                "total_path": "meta.total",
                "max_pages": 2,
            },
        )
    )

    assert seen, "no redirect hop was evaluated"
    assert all(
        call.get("allowed_origins") is None for call in seen
    ), f"an omitted allowlist became {[c.get('allowed_origins') for c in seen]!r}"
    assert METADATA not in transport.urls
