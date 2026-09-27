"""Sync half of the redirect-guard parity finding, plus two log-hygiene findings.

Commit 613468d4d added a redirect origin guard, but ``allow_redirects=False``
reached exactly ONE of five request sites — the async HATEOAS hop. The two
SYNCHRONOUS sites (``RESTClientNode.run``'s initial request and
``_handle_pagination``'s page-2+ follow-up) issued CREDENTIALED requests with
auto-follow ON, so the destination was chosen by the server's ``Location``
header and ``_MAX_REDIRECT_HOPS`` never applied (``requests`` allows 30).

Three findings are pinned here:

**S-HIGH-1 — the guard reached one site of five.** Both transports default
``allow_redirects`` to ``True`` (``http.py:535``, ``http.py:923``), and
``requests`` drops only ``Authorization`` on a cross-host redirect — ``Cookie``,
``X-API-Key`` and the node's configured ``api_key_header`` ride along. Worse on
the sync path than on the async one: ``http_params`` also carries
``auth_type``/``auth_token``/``auth_username``/``auth_password``, which
``HTTPRequestNode`` injects as headers ITSELF, so stripping the caller's
``headers`` dict alone would still hand the credential to the redirect target.
``RESTClientNode.get_parameters()`` additionally did not DECLARE
``allow_redirects``, so a caller who passed it had it silently dropped by
parameter validation — the control was unreachable from a workflow.

**S-MED-6 — unmasked request URL logged at INFO.** ``rest.py:982`` rendered the
raw ``url`` into an f-string. ``http.py:625`` does the identical thing
correctly, through ``mask_url``.

**S-MED-7 — server-controlled string logged unsanitized.** ``error_message`` is
read out of the RESPONSE BODY (``content["error"]`` / ``content["message"]``)
and was logged raw, one function away from the ``_sanitize_for_log`` helper
added precisely to stop CR/LF log forging.

**Why these assertions are not vacuous.** A transport double cannot emulate
``requests``' auto-follow — ``requests`` does that, not the node. So "no call
reached the attacker" alone would pass vacuously. Each redirect proof therefore
has three legs that only hold together:

1. the request is ASKED to send ``allow_redirects=False`` (auto-follow off),
2. the double is shown able to record the OTHER value (``_control`` below), so
   an assertion of ``False`` is a reading and not a constant,
3. the node itself processes 3xx: a SAME-ORIGIN ``Location`` IS followed. Leg 3
   is what makes "the metadata endpoint was not called" a decision rather than
   an absence — the redirect path is live and it refused that destination.

Every transport double is built from the REAL declared type: an actual
``HTTPResponse(...).model_dump()`` nested under ``"response"``, the shape
``HTTPRequestNode.execute`` genuinely returns.
"""

import logging
import pathlib
from typing import Any

from kailash.nodes.api.http import HTTPRequestNode, HTTPResponse
from kailash.nodes.api.rest import _MAX_REDIRECT_HOPS, RESTClientNode

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"
CDN = "https://cdn.example.net/items"
METADATA = "http://169.254.169.254/latest/meta-data/"

# Credential headers the caller sends. `Authorization` is the ONLY one
# `requests` drops on a cross-host redirect; the rest are the payload.
CREDENTIAL_HEADERS = {
    "Authorization": "Bearer super-secret-token",
    "Cookie": "session=super-secret-cookie",
    "X-API-Key": "super-secret-api-key",
}
CREDENTIAL_VALUES = tuple(CREDENTIAL_HEADERS.values())


def test_source_under_test_is_this_checkout():
    """Pin the import path to THIS checkout, wherever it is.

    pytest silently imports a different tree when ``pythonpath`` resolves
    elsewhere. The anchor is derived from THIS FILE's location rather than
    hard-coded, so the pin survives the worktree being reaped (commit
    dab1b679d pinned an authoring location and went red when it was removed).
    """
    from kailash.nodes.api import rest as rest_module

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    module_path = pathlib.Path(rest_module.__file__).resolve()

    assert module_path.is_relative_to(repo_root / "src"), (
        f"kailash.nodes.api.rest resolved to {module_path}, which is not under "
        f"{repo_root / 'src'} — the assertions below would describe a different tree"
    )


def transport_return(content, *, headers=None, status=200, url=FULL_URL):
    """Build a return value the way the REAL transport builds it.

    ``HTTPRequestNode.execute`` returns ``{"response":
    HTTPResponse(...).model_dump(), "status_code", "success"}``. Constructing
    the actual model (rather than hand-writing a dict) is what keeps the double
    honest: a field rename REDS here instead of passing silently.
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


class RoutingSyncTransport:
    """Stand-in for ``http_node`` that answers BY URL and records every call.

    Routing by URL (rather than by call order) is what lets a redirect loop be
    exercised: the same URL can answer the same 302 every time.
    """

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

    def headers_for(self, url):
        return next(c.get("headers") or {} for c in self.calls if c.get("url") == url)

    def call_to(self, url):
        return next(c for c in self.calls if c.get("url") == url)


def make_node(transport):
    node = RESTClientNode()
    node.http_node = transport
    return node


def call_kwargs(**overrides):
    kwargs = {
        "base_url": BASE,
        "resource": RESOURCE,
        "headers": dict(CREDENTIAL_HEADERS),
        "auth_type": "bearer",
        "auth_token": "super-secret-node-token",
    }
    kwargs.update(overrides)
    return kwargs


def credential_free(headers: dict) -> bool:
    rendered = repr(headers)
    return not any(secret in rendered for secret in CREDENTIAL_VALUES)


# ---------------------------------------------------------------------------
# Leg 2 of every redirect proof: the instrument can record the OTHER value.
# ---------------------------------------------------------------------------


def test_control_double_records_allow_redirects_true():
    """The double is shown able to emit the falsifying reading.

    Every `allow_redirects is False` assertion below is only evidence if this
    double would have recorded `True` had the node sent `True`. It would.
    """
    transport = RoutingSyncTransport()
    transport.execute(url=FULL_URL, allow_redirects=True)
    assert transport.calls[0]["allow_redirects"] is True

    # ...and the transport's OWN default is True, so False is a decision the
    # node makes, not a value it inherits.
    assert HTTPRequestNode().get_parameters()["allow_redirects"].default is True


# ---------------------------------------------------------------------------
# S-HIGH-1 (1) — allow_redirects=False reaches BOTH sync transport sites
# ---------------------------------------------------------------------------


def test_sync_initial_request_disables_automatic_redirects():
    transport = RoutingSyncTransport({FULL_URL: transport_return(page([{"id": 1}]))})
    make_node(transport).run(**call_kwargs())

    assert transport.calls, "the initial request never reached the transport"
    assert transport.calls[0]["allow_redirects"] is False, (
        "sync initial request left automatic redirect-following ON: the server's "
        "Location header chooses the destination for a credentialed request"
    )


def test_sync_pagination_followup_disables_automatic_redirects():
    transport = RoutingSyncTransport(
        default=lambda url: transport_return(page([{"id": 2}], total=99), url=str(url))
    )
    make_node(transport).run(
        **call_kwargs(
            paginate=True,
            pagination_params={"max_pages": 3, "items_path": "data"},
        )
    )

    assert len(transport.calls) >= 2, "pagination never issued a follow-up page"
    assert all(call.get("allow_redirects") is False for call in transport.calls), (
        "a sync pagination follow-up left automatic redirect-following ON: "
        f"{[c.get('allow_redirects') for c in transport.calls]}"
    )


# ---------------------------------------------------------------------------
# S-HIGH-1 (2) — the control is DECLARED, and the caller's value is not dropped
# ---------------------------------------------------------------------------


def test_allow_redirects_is_declared_on_the_rest_node():
    params = RESTClientNode().get_parameters()
    assert "allow_redirects" in params, (
        "RESTClientNode does not declare allow_redirects, so parameter "
        "validation silently drops it and the control is unreachable"
    )
    assert params["allow_redirects"].type is bool
    assert params["allow_redirects"].default is True


def test_caller_supplied_allow_redirects_false_is_not_dropped_by_validation():
    """The declaration bug is the DROP, which `get_parameters()` cannot show.

    Driven through `execute()` — the path that validates and filters inputs —
    so an undeclared parameter is discarded exactly as it is in a workflow.
    """
    routes = {
        FULL_URL: redirect_return(f"{BASE}/items/v2"),
        f"{BASE}/items/v2": transport_return(page([{"id": 1}]), url=f"{BASE}/items/v2"),
    }

    opted_out = RoutingSyncTransport(dict(routes))
    result = make_node(opted_out).execute(**call_kwargs(allow_redirects=False))
    assert opted_out.urls == [FULL_URL], (
        "allow_redirects=False was dropped by parameter validation: the node "
        f"followed the redirect anyway ({opted_out.urls})"
    )
    assert result["status_code"] == 302

    # Opposite pole: the default DOES follow, so the assertion above is a
    # reading of the caller's value and not of a node that never redirects.
    default = RoutingSyncTransport(dict(routes))
    make_node(default).execute(**call_kwargs())
    assert default.urls == [FULL_URL, f"{BASE}/items/v2"]


# ---------------------------------------------------------------------------
# S-HIGH-1 (3) — cross-origin initial redirect: FOLLOWED, credentials STRIPPED
# ---------------------------------------------------------------------------


def test_cross_origin_initial_redirect_is_followed_without_credentials():
    transport = RoutingSyncTransport(
        {
            FULL_URL: redirect_return(CDN),
            CDN: transport_return(page([{"id": 1}]), url=CDN),
        }
    )
    make_node(transport).run(**call_kwargs())

    assert CDN in transport.urls, (
        "a cross-origin redirect on the CALLER-CHOSEN initial request was "
        "refused; ordinary CDN and vanity-domain redirects would break"
    )
    hop = transport.call_to(CDN)
    assert credential_free(
        hop.get("headers") or {}
    ), f"credential headers crossed the origin boundary: {hop.get('headers')}"
    assert hop.get("auth_type") is None and hop.get("auth_token") is None, (
        "node-level auth survived the cross-origin hop; HTTPRequestNode injects "
        "it as a header itself, so stripping `headers` alone is not enough"
    )


def test_same_origin_initial_redirect_keeps_credentials():
    target = f"{BASE}/items/v2"
    transport = RoutingSyncTransport(
        {
            FULL_URL: redirect_return(target),
            target: transport_return(page([{"id": 1}]), url=target),
        }
    )
    make_node(transport).run(**call_kwargs())

    assert transport.urls == [FULL_URL, target]
    hop = transport.call_to(target)
    assert (hop.get("headers") or {}).get("Authorization") == (
        CREDENTIAL_HEADERS["Authorization"]
    ), "a SAME-ORIGIN redirect must still carry the caller's credentials"
    assert hop.get("auth_token") == "super-secret-node-token"


def test_credential_stripping_is_sticky_back_to_the_original_origin():
    """Once a hop has left the origin, credentials do not come back."""
    back_home = f"{BASE}/items/final"
    transport = RoutingSyncTransport(
        {
            FULL_URL: redirect_return(CDN),
            CDN: redirect_return(back_home, url=CDN),
            back_home: transport_return(page([{"id": 1}]), url=back_home),
        }
    )
    make_node(transport).run(**call_kwargs())

    assert back_home in transport.urls
    hop = transport.call_to(back_home)
    assert credential_free(hop.get("headers") or {}), (
        "a third-party origin laundered the caller's credentials back onto the "
        f"original origin: {hop.get('headers')}"
    )
    assert hop.get("auth_token") is None


# ---------------------------------------------------------------------------
# S-HIGH-1 (4) — internal / metadata destinations are refused on BOTH paths
# ---------------------------------------------------------------------------


def test_initial_redirect_to_metadata_endpoint_is_refused(caplog):
    transport = RoutingSyncTransport(
        {
            FULL_URL: redirect_return(METADATA),
            METADATA: transport_return({"iam": "credentials"}, url=METADATA),
        }
    )
    with caplog.at_level(logging.WARNING):
        result = make_node(transport).run(**call_kwargs())

    assert transport.urls == [
        FULL_URL
    ], f"the cloud metadata endpoint was requested: {transport.urls}"
    assert result["status_code"] == 302
    assert any("internal" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# S-HIGH-1 (5) — the hop bound applies, instead of the client default (30)
# ---------------------------------------------------------------------------


def test_redirect_chain_is_bounded_by_max_redirect_hops(caplog):
    def endless(url):
        current = str(url)
        nxt = f"{BASE}/hop{len(transport.calls)}"
        return redirect_return(nxt, url=current)

    transport = RoutingSyncTransport()
    transport.default = endless

    with caplog.at_level(logging.WARNING):
        make_node(transport).run(**call_kwargs())

    assert len(transport.calls) == _MAX_REDIRECT_HOPS + 1, (
        f"redirect chain ran to {len(transport.calls)} requests; the bound is "
        f"the initial request plus {_MAX_REDIRECT_HOPS} hops"
    )
    assert any("hop" in record.getMessage() for record in caplog.records)


def test_missing_location_fails_closed_with_a_warning(caplog):
    transport = RoutingSyncTransport({FULL_URL: redirect_return(None)})

    with caplog.at_level(logging.WARNING):
        result = make_node(transport).run(**call_kwargs())

    assert transport.urls == [FULL_URL]
    assert result["status_code"] == 302
    assert any("Location" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# S-MED-6 — the request URL is masked before it is logged
# ---------------------------------------------------------------------------


def test_request_url_is_masked_in_the_info_log(caplog):
    transport = RoutingSyncTransport(default=transport_return(page([])))
    node = make_node(transport)

    with caplog.at_level(logging.INFO):
        node.run(
            base_url="https://svc:hunter2@api.example.com",
            resource="items?api_key=super-secret-key",
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "hunter2" not in rendered, f"userinfo password logged verbatim: {rendered}"
    assert (
        "super-secret-key" not in rendered
    ), f"api_key query parameter logged verbatim: {rendered}"
    # Opposite pole: the line is still USEFUL — masking is not deletion.
    assert (
        "api.example.com" in rendered
    ), f"masking removed the host too, leaving an unusable log line: {rendered}"


# ---------------------------------------------------------------------------
# S-MED-7 — a server-supplied error message cannot forge log lines
# ---------------------------------------------------------------------------


FORGED = "denied\r\n2026-09-12 CRITICAL kailash.audit: access granted to attacker"


def test_server_error_message_cannot_forge_log_lines(caplog):
    transport = RoutingSyncTransport(
        {FULL_URL: transport_return({"error": FORGED}, status=403)}
    )

    with caplog.at_level(logging.ERROR):
        result = make_node(transport).run(**call_kwargs())

    records = [r for r in caplog.records if "REST API error" in r.getMessage()]
    assert len(records) == 1, f"expected one error record, got {len(records)}"
    message = records[0].getMessage()
    assert (
        "\r" not in message and "\n" not in message
    ), f"raw CR/LF from the response body reached the log: {message!r}"
    assert (
        "\\x0d" in message and "\\x0a" in message
    ), f"control characters were dropped rather than made visible: {message!r}"
    # The returned surface is sanitized too — see the module docstring of the
    # fix: this field's consumers are line-oriented sinks.
    assert "\r" not in result["error"] and "\n" not in result["error"]


def test_clean_error_message_survives_unchanged():
    """Opposite pole: sanitizing is not mangling."""
    transport = RoutingSyncTransport(
        {FULL_URL: transport_return({"error": "not found"}, status=404)}
    )
    result = make_node(transport).run(**call_kwargs())

    assert result["error"] == "not found (status: 404)"
