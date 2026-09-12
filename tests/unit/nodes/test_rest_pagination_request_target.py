"""Regression tests for REST pagination follow-up requests (RT-1b + sub-issue).

Two defects shipped together in ``RESTClientNode._handle_pagination``:

1. **HIGH — ``paginate=True`` was a silent no-op.** The follow-up page request
   built its URL from ``self._last_url``, an attribute that was never assigned
   anywhere in the repository, so the ``hasattr`` guard was always False and
   ``url=None`` was always passed. Against the real transport that raises
   ``NodeValidationError: URL parameter is required``, which a bare
   ``except Exception`` downgraded to a WARNING before ``break``-ing. Every
   caller received page 1 presented as the complete result set. Headers and
   timeout were read from magic ``query_params`` keys (``_headers``,
   ``_timeout``) that nothing ever wrote, so auth headers were always dropped.

2. **RT-1b — no cursor dedup.** A server returning a constant cursor looped to
   ``max_pages``, appending the same page each time, so the caller received
   duplicated records. This was unreachable in production only because defect 1
   masked it — fixing 1 is precisely what makes it reachable.

The tests below assert on the ARGUMENTS the transport receives, not merely that
it was called. A stub that ignores ``url``/``headers`` is exactly the blind spot
that let defect 1 ship past the existing ``max_pages`` test.
"""

import pytest

from kailash.nodes.api.http import HTTPResponse
from kailash.nodes.api.rest import RESTClientNode
from kailash.sdk_exceptions import NodeValidationError

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"
AUTH_HEADERS = {"Authorization": "Bearer secret-token", "Accept": "application/json"}


def transport_result(content, status_code: int = 200):
    """Build the EXACT payload ``HTTPRequestNode.execute`` returns.

    The double is constructed from the REAL declared type -- ``HTTPResponse``
    (``kailash/nodes/api/http.py``), dumped exactly as the production node
    dumps it at ``http.py:691`` -- and wrapped in the same three-key envelope
    (``response``/``status_code``/``success``) the node returns at
    ``http.py:704-708``. Hand-rolling ``{"response": {"content": ...}}`` from
    what the CALL SITE happens to read is how a double ends up asserting
    against a shape the real transport never produces: the envelope's
    ``status_code`` key and every ``HTTPResponse`` field but ``content`` were
    missing, so a consumer reading any of them was exercised against nothing.
    """
    return {
        "response": HTTPResponse(
            status_code=status_code,
            headers={"Content-Type": "application/json"},
            content_type="application/json",
            content=content,
            response_time_ms=1.5,
            url=FULL_URL,
        ).model_dump(),
        "status_code": status_code,
        "success": 200 <= status_code < 300,
    }


class RecordingTransport:
    """Stand-in for ``http_node`` that records the full call and FAILS the way
    the real transport fails when handed an unusable URL."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = []

    def execute(self, **kwargs):
        # Record a SNAPSHOT, params included: what a page actually put on the
        # wire is what the dict held at call time. Storing the live object
        # would let a later mutation rewrite history, so a per-page ``params``
        # assertion could no longer distinguish "sent page=2" from "sent
        # page=1 and mutated the dict afterwards".
        recorded = dict(kwargs)
        if isinstance(recorded.get("params"), dict):
            recorded["params"] = dict(recorded["params"])
        self.calls.append(recorded)
        # Mirror HTTPRequestNode's real contract: no URL is a validation error,
        # not a quietly-empty response.
        if not kwargs.get("url"):
            raise NodeValidationError("URL parameter is required")
        content = self._pages.pop(0) if self._pages else {"data": []}
        return transport_result(content)


def test_followup_request_carries_the_originating_url_headers_and_timeout():
    """The HIGH. Pins that the real url/headers/timeout ARRIVE at the transport
    on every follow-up page — the assertion the original stub never made."""
    node = RESTClientNode()
    transport = RecordingTransport([{"data": [3, 4]}, {"data": [5, 6]}])
    node.http_node = transport  # type: ignore[assignment]

    all_items = node._handle_pagination(
        {"data": [1, 2]},
        {"page": "1", "per_page": "2", "sort": "desc"},
        {"type": "page", "items_path": "data", "max_pages": 3},
        request_url=FULL_URL,
        request_headers=AUTH_HEADERS,
        request_timeout=17,
    )

    assert len(transport.calls) == 2, "both follow-up pages must be requested"
    for call in transport.calls:
        assert call["url"] == FULL_URL
        # Auth headers must survive to page 2+, or the follow-up 401s.
        assert call["headers"] == AUTH_HEADERS
        assert call["timeout"] == 17
    # The WHOLE query for each follow-up, not merely that one was issued: the
    # accumulated items below come from the stub's queue, so a regression that
    # re-sent `page=1` forever would still hand back [1,2,3,4,5,6] and pass
    # every assertion above it. Only the params say which page was requested.
    # Asserted as EXACT dicts (and `==` on the full list, not per-key), so a
    # dropped `sort`/`per_page` -- the shape of the auth-drop defect, applied
    # to the query rather than the headers -- fails here too.
    assert [call["params"] for call in transport.calls] == [
        {"page": "2", "per_page": "2", "sort": "desc"},
        {"page": "3", "per_page": "2", "sort": "desc"},
    ]
    # Pages actually accumulate now, instead of stopping at page 1.
    assert all_items == [1, 2, 3, 4, 5, 6]


def test_end_to_end_run_threads_the_request_target_into_pagination():
    """Caller-wiring guard: exercises ``RESTClientNode.run`` so a future caller
    that forgets to thread the request target fails HERE rather than silently
    truncating in production."""
    node = RESTClientNode()
    transport = RecordingTransport(
        [
            {"data": [1, 2]},  # the initial request
            {"data": [3, 4]},  # follow-up page 2
            {"data": [5, 6]},  # follow-up page 3
        ]
    )
    node.http_node = transport  # type: ignore[assignment]

    result = node.run(
        base_url=BASE,
        resource=RESOURCE,
        method="GET",
        headers={"Authorization": "Bearer secret-token"},
        query_params={"page": "1", "per_page": "2", "sort": "desc"},
        timeout=17,
        paginate=True,
        pagination_params={
            "type": "page",
            "items_path": "data",
            "max_pages": 3,
        },
    )

    assert result["success"] is True
    assert result["data"] == [1, 2, 3, 4, 5, 6], "pagination must not stop at page 1"
    assert len(transport.calls) == 3, "1 initial + 2 follow-up requests"
    for call in transport.calls:
        assert call["url"] == FULL_URL
        assert call["headers"]["Authorization"] == "Bearer secret-token"
        assert call["timeout"] == 17
    # Same params discipline end-to-end: the page number must ADVANCE on the
    # wire (1 -> 2 -> 3) and the caller's non-pagination query must survive
    # `run()`'s threading of the request target into `_handle_pagination`.
    assert [call["params"] for call in transport.calls] == [
        {"page": "1", "per_page": "2", "sort": "desc"},
        {"page": "2", "per_page": "2", "sort": "desc"},
        {"page": "3", "per_page": "2", "sort": "desc"},
    ]


def test_constant_cursor_stops_instead_of_duplicating_pages():
    """RT-1b. A server that keeps returning the same cursor must stop the loop,
    not append the same page until ``max_pages``."""
    node = RESTClientNode()

    class ConstantCursorTransport(RecordingTransport):
        def execute(self, **kwargs):
            recorded = dict(kwargs)
            if isinstance(recorded.get("params"), dict):
                recorded["params"] = dict(recorded["params"])
            self.calls.append(recorded)
            if not kwargs.get("url"):
                raise NodeValidationError("URL parameter is required")
            return transport_result({"items": [7], "meta": {"next": "STUCK"}})

    transport = ConstantCursorTransport([])
    node.http_node = transport  # type: ignore[assignment]

    all_items = node._handle_pagination(
        {"items": [1], "meta": {"next": "STUCK"}},
        {},
        {
            "type": "cursor",
            "items_path": "items",
            "next_page_path": "meta.next",
            "cursor_param": "cursor",
            "max_pages": 5,
        },
        request_url=FULL_URL,
        request_headers={},
        request_timeout=30,
    )

    # One request for cursor "STUCK"; the repeat is recognised and the loop ends.
    assert len(transport.calls) == 1
    assert transport.calls[0]["params"]["cursor"] == "STUCK"
    assert all_items == [1, 7], "a repeated cursor must not duplicate its page"


def test_advancing_cursor_still_paginates():
    """No-false-positive guard for the dedup: distinct cursors must keep going,
    so the dedup cannot be satisfied by simply never fetching a second page."""
    node = RESTClientNode()
    pages = [
        {"items": [2], "meta": {"next": "c2"}},
        {"items": [3], "meta": {"next": "c3"}},
        {"items": [4], "meta": {}},
    ]
    transport = RecordingTransport(pages)
    node.http_node = transport  # type: ignore[assignment]

    all_items = node._handle_pagination(
        {"items": [1], "meta": {"next": "c1"}},
        {},
        {
            "type": "cursor",
            "items_path": "items",
            "next_page_path": "meta.next",
            "cursor_param": "cursor",
            "max_pages": 10,
        },
        request_url=FULL_URL,
        request_headers={},
        request_timeout=30,
    )

    assert [c["params"]["cursor"] for c in transport.calls] == ["c1", "c2", "c3"]
    assert all_items == [1, 2, 3, 4]


def test_misconfigured_followup_request_surfaces_instead_of_truncating():
    """The narrowed except. A ``NodeValidationError`` from the follow-up request
    is a configuration error and MUST propagate — swallowing it as a warning is
    what let defect 1 ship, because the caller could not tell a truncated result
    from a complete one."""
    node = RESTClientNode()
    transport = RecordingTransport([{"data": [3, 4]}])
    node.http_node = transport  # type: ignore[assignment]

    with pytest.raises(NodeValidationError, match="URL parameter is required"):
        node._handle_pagination(
            {"data": [1, 2]},
            {"page": "1", "per_page": "2"},
            {"type": "page", "items_path": "data", "max_pages": 3},
            request_url="",  # what the old `url=None` expression always produced
            request_headers={},
            request_timeout=30,
        )


def test_transport_failure_still_degrades_to_pages_fetched_so_far():
    """No-false-positive guard for the narrowing: genuine transport errors keep
    their graceful-degradation behaviour, so the narrowing did not turn every
    network blip into a hard failure."""
    node = RESTClientNode()

    class FlakyTransport(RecordingTransport):
        def execute(self, **kwargs):
            recorded = dict(kwargs)
            if isinstance(recorded.get("params"), dict):
                recorded["params"] = dict(recorded["params"])
            self.calls.append(recorded)
            if len(self.calls) == 1:
                return transport_result({"data": [3, 4]})
            raise ConnectionError("connection reset by peer")

    transport = FlakyTransport([])
    node.http_node = transport  # type: ignore[assignment]

    all_items = node._handle_pagination(
        {"data": [1, 2]},
        {"page": "1", "per_page": "2"},
        {"type": "page", "items_path": "data", "max_pages": 5},
        request_url=FULL_URL,
        request_headers={},
        request_timeout=30,
    )

    assert all_items == [1, 2, 3, 4], "keep what was fetched before the failure"
    assert len(transport.calls) == 2
