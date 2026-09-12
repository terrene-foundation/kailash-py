"""Regression tests for the async REST path: origin guard, response shape, swallow.

Three defects, fixed together because fixing the second ARMS the first (#2230).

1. **A1 — credential exfiltration via a server-supplied pagination link.**
   ``RESTClientNode._handle_async_pagination`` read ``metadata["links"]["next"]``
   straight out of the RESPONSE BODY and issued the follow-up request against it
   carrying the caller's headers -- ``Authorization`` included -- with no
   validation of any kind (``_extract_links`` checks nothing). A hostile or
   compromised upstream could therefore redirect the caller's bearer token to
   any host it named, or point the node at ``file:///`` or at the cloud
   metadata endpoint. Unreachable in production ONLY because defect 2 kept the
   link out of ``metadata`` -- which is precisely why the guard had to land in
   the same change as the shape fix, not after it.

2. **A2 — every async call returned ``data=None`` while reporting success.**
   ``async_run`` read ``http_result.get("content")`` / ``.get("headers")``.
   ``AsyncHTTPRequestNode.async_run`` has no top-level ``content`` or
   ``headers``: they live inside ``result["response"]``, which is ``None`` on
   the failure path. The same root cause meant ``metadata`` never carried
   ``links``/``pagination``, so ``paginate=True`` silently returned page 1.

3. **A3 — a fully silent swallow.** The pagination loop ended in
   ``except Exception: break`` with no log line at all, so a mis-configured
   follow-up request presented page 1 as the complete result set with nothing
   in the log to say so (``rules/zero-tolerance.md`` Rule 3).

The doubles below are built from the REAL declared type -- every transport
return is an actual ``HTTPResponse(...).model_dump()`` nested under
``"response"``. A previous attempt at defect 2 shipped a no-op precisely
because its double returned a shape the real transport never produces, and its
contract pin compared signature PARAMETERS while the mismatch was in the RETURN
shape. ``test_transport_return_shape_nests_content_and_headers`` therefore
exercises the REAL ``AsyncHTTPRequestNode.async_run`` and asserts on what it
actually returns, so a future transport change REDS this file.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

import pytest

from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPResponse
from kailash.nodes.api.rest import RESTClientNode
from kailash.sdk_exceptions import NodeValidationError

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"
AUTH = "Bearer super-secret-token"


def transport_return(content, *, headers=None, status=200, url=FULL_URL):
    """Build a return value the way the REAL transport builds it.

    ``AsyncHTTPRequestNode.async_run`` returns
    ``{"response": HTTPResponse(...).model_dump(), "status_code", "success"}``.
    Constructing the actual ``HTTPResponse`` model (rather than hand-writing a
    dict) is what keeps this double honest: a field rename on the model REDS
    here instead of silently agreeing with a stale hand-written shape.
    """
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


class RecordingAsyncTransport:
    """Stand-in for ``_async_http_node`` recording every call's full kwargs."""

    def __init__(self, returns):
        self._returns = list(returns)
        self.calls = []

    async def async_run(self, **kwargs):
        self.calls.append(kwargs)
        if not self._returns:
            return transport_return({"data": []}, url=kwargs.get("url", FULL_URL))
        nxt = self._returns.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    @property
    def urls(self):
        return [call.get("url") for call in self.calls]

    @property
    def header_sets(self):
        return [call.get("headers") or {} for call in self.calls]


def make_node(transport):
    node = RESTClientNode()
    node._async_http_node = transport  # type: ignore[attr-defined]
    return node


def page(items, next_link=None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": list(items)}
    if next_link is not None:
        body["links"] = {"next": next_link}
    return body


# ---------------------------------------------------------------------------
# Contract pin — the REAL transport's RETURN shape
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


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.requests = []

    def request(self, **kwargs):
        self.requests.append(kwargs)
        response = self._response

        @asynccontextmanager
        async def _cm():
            yield response

        return _cm()


class _FakePool:
    def __init__(self, session):
        self._session = session

    def acquire(self):
        session = self._session

        @asynccontextmanager
        async def _cm():
            yield session

        return _cm()


async def test_transport_return_shape_nests_content_and_headers(monkeypatch):
    """CONTRACT PIN on ``AsyncHTTPRequestNode.async_run``'s RETURN shape.

    Runs the REAL transport (only the aiohttp session pool is faked) and pins
    that ``content``/``headers`` are reachable ONLY under ``["response"]`` and
    are ABSENT at the top level. If a future change promotes them to the top
    level -- or drops the ``response`` nesting -- this test REDs, which is the
    signal ``RESTClientNode._build_async_result`` depends on.
    """
    import kailash.nodes.api.http as http_mod

    fake_response = _FakeAiohttpResponse(
        {"data": [1, 2]},
        {"Content-Type": "application/json", "X-RateLimit-Limit": "60"},
        200,
        FULL_URL,
    )
    monkeypatch.setattr(
        http_mod, "_async_http_session_pool", _FakePool(_FakeSession(fake_response))
    )

    result = await AsyncHTTPRequestNode().async_run(url=FULL_URL, method="GET")

    assert "response" in result, result.keys()
    assert result["response"]["content"] == {"data": [1, 2]}
    assert result["response"]["headers"]["X-RateLimit-Limit"] == "60"
    # The mismatch that caused the defect: these are NOT top-level keys.
    assert "content" not in result, "transport promoted content to top level"
    assert "headers" not in result, "transport promoted headers to top level"
    # And the nested payload really is the declared model.
    assert set(result["response"]) == set(HTTPResponse.model_fields)


# ---------------------------------------------------------------------------
# A2 — response shape
# ---------------------------------------------------------------------------


async def test_async_run_returns_nested_content_as_data():
    """The HIGH: ``data`` was ``None`` on every async call."""
    transport = RecordingAsyncTransport([transport_return({"data": [1, 2, 3]})])
    node = make_node(transport)

    result = await node.async_run(base_url=BASE, resource=RESOURCE)

    assert result["data"] == {"data": [1, 2, 3]}
    assert result["success"] is True


async def test_async_run_metadata_carries_headers_and_extracted_links():
    """Without this, ``_handle_async_pagination`` never finds a next link."""
    transport = RecordingAsyncTransport(
        [
            transport_return(
                page([1], next_link=f"{FULL_URL}?page=2"),
                headers={"X-RateLimit-Limit": "60", "Content-Type": "application/json"},
            )
        ]
    )
    node = make_node(transport)

    result = await node.async_run(base_url=BASE, resource=RESOURCE)

    assert result["metadata"]["headers"]["X-RateLimit-Limit"] == "60"
    assert result["metadata"]["links"]["next"] == f"{FULL_URL}?page=2"
    assert result["metadata"]["rate_limit"]["limit"] == 60
    assert result["metadata"]["response_time_ms"] == 12.5


async def test_async_run_survives_the_none_response_failure_path():
    """The transport returns ``{"response": None, ...}`` when it gives up."""
    transport = RecordingAsyncTransport(
        [{"response": None, "status_code": None, "success": False}]
    )
    node = make_node(transport)

    result = await node.async_run(base_url=BASE, resource=RESOURCE)

    assert result["data"] is None
    assert result["success"] is False
    assert result["metadata"]["headers"] == {}


# ---------------------------------------------------------------------------
# A1 — origin guard: ALLOW poles
# ---------------------------------------------------------------------------


async def test_same_origin_next_link_is_followed_with_credentials_intact():
    """ALLOW pole. Same-origin pagination keeps working, auth forwarded."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1, 2], next_link=f"{FULL_URL}?page=2")),
            transport_return(page([3, 4]), url=f"{FULL_URL}?page=2"),
        ]
    )
    node = make_node(transport)

    result = await node.async_run(
        base_url=BASE,
        resource=RESOURCE,
        paginate=True,
        headers={"Authorization": AUTH},
    )

    assert transport.urls == [FULL_URL, f"{FULL_URL}?page=2"]
    assert transport.header_sets[1]["Authorization"] == AUTH
    assert result["metadata"]["total_pages_fetched"] == 2


async def test_relative_next_link_resolves_against_the_request_url():
    """A relative link is same-origin by construction once resolved."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1], next_link="/items?page=2")),
            transport_return(page([2]), url=f"{BASE}/items?page=2"),
        ]
    )
    node = make_node(transport)

    await node.async_run(
        base_url=BASE, resource=RESOURCE, paginate=True, headers={"Authorization": AUTH}
    )

    assert transport.urls[1] == f"{BASE}/items?page=2"
    assert transport.header_sets[1]["Authorization"] == AUTH


async def test_default_port_normalization_counts_as_same_origin():
    """``http://h:80`` and ``http://h`` are one origin, so credentials stay."""
    transport = RecordingAsyncTransport(
        [
            transport_return(
                page([1], next_link="http://plain.example:80/items?page=2"),
                url="http://plain.example/items",
            ),
            transport_return(page([2]), url="http://plain.example:80/items?page=2"),
        ]
    )
    node = make_node(transport)

    await node.async_run(
        base_url="http://plain.example",
        resource=RESOURCE,
        paginate=True,
        headers={"Authorization": AUTH},
    )

    assert transport.urls[1] == "http://plain.example:80/items?page=2"
    assert transport.header_sets[1]["Authorization"] == AUTH


async def test_allowlisted_cross_origin_proceeds_without_credentials():
    """ALLOW pole with a STRIP: the page is fetched, the token is not sent."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1], next_link="https://cdn.example/items?page=2")),
            transport_return(page([2]), url="https://cdn.example/items?page=2"),
        ]
    )
    node = make_node(transport)

    await node.async_run(
        base_url=BASE,
        resource=RESOURCE,
        paginate=True,
        headers={
            "Authorization": AUTH,
            "Cookie": "session=abc",
            "Proxy-Authorization": "Basic zzz",
            "x-api-key": "k1",
            "X-Auth-Token": "t1",
            "Api-Key": "k2",
            "X-Tenant": "acme",
            "Accept": "application/json",
        },
        allowed_pagination_origins=["https://cdn.example"],
    )

    assert transport.urls[1] == "https://cdn.example/items?page=2"
    sent = transport.header_sets[1]
    assert set(sent) == {"X-Tenant", "Accept"}, sent
    assert "Authorization" not in sent


async def test_allowlisted_cross_origin_strips_the_configured_api_key_header():
    """The caller's own ``api_key_header`` name joins the strip set."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1], next_link="https://cdn.example/items?page=2")),
            transport_return(page([2]), url="https://cdn.example/items?page=2"),
        ]
    )
    node = make_node(transport)

    await node.async_run(
        base_url=BASE,
        resource=RESOURCE,
        paginate=True,
        headers={"X-Corp-Secret": "s3cr3t", "Accept": "application/json"},
        api_key_header="X-Corp-Secret",
        allowed_pagination_origins=["https://cdn.example"],
    )

    sent = transport.header_sets[1]
    assert "X-Corp-Secret" not in sent, sent
    assert sent["Accept"] == "application/json"


async def test_same_origin_localhost_still_paginates():
    """Rule 3's carve-out: a node pointed at localhost is not self-blocking."""
    transport = RecordingAsyncTransport(
        [
            transport_return(
                page([1], next_link="http://127.0.0.1:8000/items?page=2"),
                url="http://127.0.0.1:8000/items",
            ),
            transport_return(page([2]), url="http://127.0.0.1:8000/items?page=2"),
        ]
    )
    node = make_node(transport)

    await node.async_run(
        base_url="http://127.0.0.1:8000", resource=RESOURCE, paginate=True
    )

    assert transport.urls[1] == "http://127.0.0.1:8000/items?page=2"


# ---------------------------------------------------------------------------
# A1 — origin guard: REJECT poles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "next_link,reason_fragment",
    [
        ("file:///etc/passwd", "not http(s)"),
        ("javascript:alert(1)", "not http(s)"),
        ("data:text/html,<script>fetch(1)</script>", "not http(s)"),
        ("gopher://evil.example/x", "not http(s)"),
        ("http://169.254.169.254/latest/meta-data/", "internal/reserved"),
        ("http://metadata.google.internal/computeMetadata/v1/", "internal/reserved"),
        ("http://10.0.0.5/internal", "internal/reserved"),
        ("http://[::1]/internal", "internal/reserved"),
        ("http://[fd00::1]/internal", "internal/reserved"),
        ("http://localhost:9999/admin", "internal/reserved"),
        ("http://attacker.example/steal", "not allow-listed"),
        ("https://attacker.example/steal", "not allow-listed"),
        # Protocol-relative: inherits the origin's scheme, not its host.
        ("//attacker.example/steal", "not allow-listed"),
        # Suffix confusion -- a prefix match would have let this through.
        ("https://api.example.com.evil.com/steal", "not allow-listed"),
        # Port is part of the origin.
        ("https://api.example.com:8443/items?page=2", "not allow-listed"),
        # Scheme downgrade would put the bearer token on the wire in clear.
        ("http://api.example.com/items?page=2", "not allow-listed"),
    ],
)
async def test_hostile_next_link_is_never_requested(next_link, reason_fragment, caplog):
    """REJECT poles. The follow-up request is NEVER issued, so the caller's
    Authorization header cannot reach the attacker-named host."""
    transport = RecordingAsyncTransport(
        [transport_return(page([1], next_link=next_link))]
    )
    node = make_node(transport)

    with caplog.at_level(logging.WARNING):
        result = await node.async_run(
            base_url=BASE,
            resource=RESOURCE,
            paginate=True,
            headers={"Authorization": AUTH},
        )

    assert transport.urls == [FULL_URL], f"guard let {next_link!r} through"
    assert all(AUTH not in str(h) for h in transport.header_sets[1:])
    assert result["metadata"]["total_pages_fetched"] == 1
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "Pagination stopped" in messages
    assert reason_fragment in messages


async def test_rejection_log_does_not_echo_embedded_credentials(caplog):
    """The warning names the reason; any rendered URL is masked first."""
    transport = RecordingAsyncTransport(
        [
            transport_return(
                page([1], next_link="http://user:hunter2@attacker.example/steal")
            )
        ]
    )
    node = make_node(transport)

    with caplog.at_level(logging.WARNING):
        await node.async_run(base_url=BASE, resource=RESOURCE, paginate=True)

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "hunter2" not in messages, messages
    assert "***@attacker.example" in messages


async def test_allowlist_does_not_unlock_an_internal_address():
    """Rule 3 outranks rule 5: only SAME origin exempts an internal target."""
    transport = RecordingAsyncTransport(
        [transport_return(page([1], next_link="http://127.0.0.1:9000/admin"))]
    )
    node = make_node(transport)

    await node.async_run(
        base_url=BASE,
        resource=RESOURCE,
        paginate=True,
        allowed_pagination_origins=["http://127.0.0.1:9000"],
    )

    assert transport.urls == [FULL_URL]


async def test_allowlisted_hop_cannot_win_credentials_back_on_a_later_hop():
    """``request_url`` stays pinned to the ORIGINAL request, so page 2's own
    origin never counts as "same origin" for page 3."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1], next_link="https://cdn.example/items?page=2")),
            transport_return(
                page([2], next_link="https://cdn.example/items?page=3"),
                url="https://cdn.example/items?page=2",
            ),
            transport_return(page([3]), url="https://cdn.example/items?page=3"),
        ]
    )
    node = make_node(transport)

    await node.async_run(
        base_url=BASE,
        resource=RESOURCE,
        paginate=True,
        headers={"Authorization": AUTH, "Accept": "application/json"},
        allowed_pagination_origins=["https://cdn.example"],
    )

    assert len(transport.calls) == 3
    for sent in transport.header_sets[1:]:
        assert "Authorization" not in sent, sent


# ---------------------------------------------------------------------------
# A3 — the silent swallow
# ---------------------------------------------------------------------------


async def test_transport_failure_is_logged_not_swallowed(caplog):
    """Was ``except Exception: break`` with no log line at all."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1, 2], next_link=f"{FULL_URL}?page=2")),
            ConnectionResetError("connection reset by peer"),
        ]
    )
    node = make_node(transport)

    with caplog.at_level(logging.WARNING):
        result = await node.async_run(base_url=BASE, resource=RESOURCE, paginate=True)

    assert result["success"] is True
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "Async pagination request failed" in messages
    assert "connection reset by peer" in messages


async def test_transport_failure_log_masks_credentials(caplog):
    """The exception text carries the URL the transport was handed."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1], next_link=f"{FULL_URL}?page=2")),
            OSError(f"cannot connect to {BASE}/items?access_token=leaked-value"),
        ]
    )
    node = make_node(transport)

    with caplog.at_level(logging.WARNING):
        await node.async_run(base_url=BASE, resource=RESOURCE, paginate=True)

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "leaked-value" not in messages, messages
    assert "access_token=***" in messages


async def test_misconfigured_followup_request_propagates():
    """A NodeValidationError is a configuration bug, not a transient failure.
    Swallowing it is what presented page 1 as the whole result set."""
    transport = RecordingAsyncTransport(
        [
            transport_return(page([1], next_link=f"{FULL_URL}?page=2")),
            NodeValidationError("URL parameter is required"),
        ]
    )
    node = make_node(transport)

    with pytest.raises(NodeValidationError, match="URL parameter is required"):
        await node.async_run(base_url=BASE, resource=RESOURCE, paginate=True)


# ---------------------------------------------------------------------------
# Declared parameter
# ---------------------------------------------------------------------------


def test_allowed_pagination_origins_is_a_declared_parameter():
    param = RESTClientNode().get_parameters()["allowed_pagination_origins"]
    assert param.type is list
    assert param.required is False
    assert param.default is None
