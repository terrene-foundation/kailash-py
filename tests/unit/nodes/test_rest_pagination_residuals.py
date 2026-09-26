"""Residual defects on the SYNC REST pagination path (issue #2231, items 1/2/3/5).

Ordered as the issue orders them.

1. **C1 — node-parameter auth was dropped on follow-up pages.** The follow-up
   request forwarded only ``url``/``method``/``headers``/``params``/
   ``response_format``/``timeout``. ``HTTPRequestNode`` injects the
   ``Authorization`` header FROM ``auth_type``/``auth_token`` (``http.py``
   ``_apply_authentication``) — it never enters the caller's ``headers`` dict —
   so pages 2+ went out unauthenticated, 401'd, and
   ``if not next_result.get("success"): break`` returned page 1 as the complete
   result set. ``verify_ssl``/``retry_count``/``retry_backoff`` were dropped the
   same way (``verify_ssl`` fails CLOSED, so that half is a correctness bug, not
   a security one).
2. **C2 — cursor dedup was a single slot**, so a server cycling ``A -> B -> A``
   never compared equal to its immediate predecessor and duplicate pages were
   appended up to ``max_pages``.
3. **C3 — the transport-failure sink logged the rendered exception unmasked**,
   unlike every sibling sink in ``http.py``. Parity / defence-in-depth.
4. **C4 — the accumulator aliased the caller's own list** and was ``extend``ed
   in place, so merely reading the pages mutated the caller's response.

Discipline note: ``RecordingTransport`` returns the **real**
``HTTPRequestNode.execute`` shape, constructed by actually instantiating
``HTTPResponse`` and calling ``.model_dump()``. A double that returns a
hand-rolled ``{"response": {"content": ...}}`` cannot catch a regression in how
the production code reads the response envelope.
"""

import logging

import pytest

from kailash.nodes.api.http import HTTPResponse
from kailash.nodes.api.rest import RESTClientNode
from kailash.sdk_exceptions import NodeValidationError

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"

AUTH_KWARGS = {
    "auth_type": "bearer",
    "auth_token": "TOK",
    "auth_username": "u",
    "auth_password": "p",
    "api_key_header": "X-Custom-Key",
    "verify_ssl": False,
    "retry_count": 3,
    "retry_backoff": 1.5,
}


def http_result(content, *, status_code=200):
    """The REAL ``HTTPRequestNode.execute`` return shape.

    Built from the declared ``HTTPResponse`` model rather than from what the
    call site happens to read, so the double cannot drift from the transport.
    """
    response = HTTPResponse(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        content_type="application/json",
        content=content,
        response_time_ms=1.0,
        url=FULL_URL,
    ).model_dump()
    return {
        "response": response,
        "status_code": status_code,
        "success": 200 <= status_code < 300,
    }


class RecordingTransport:
    """Records every kwarg set the node hands the transport."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs.get("url"):
            raise NodeValidationError("URL parameter is required")
        content = self._pages.pop(0) if self._pages else {"data": []}
        return http_result(content)


def test_recording_double_matches_the_real_transport_envelope():
    """Pins the DOUBLE's return SHAPE against the declared model, so a shape
    drift fails here instead of silently making every test below a no-op."""
    result = http_result({"data": [1]})
    assert set(result) == {"response", "status_code", "success"}
    assert set(result["response"]) == set(HTTPResponse.model_fields)
    assert result["response"]["content"] == {"data": [1]}


# --------------------------------------------------------------------------
# C1 — node-parameter auth / transport settings reach page 2+
# --------------------------------------------------------------------------


def test_followup_pages_carry_node_parameter_auth_to_the_transport():
    """The HIGH. Asserts the auth kwargs ARRIVE AT THE TRANSPORT on call1 and
    call2 — not merely that a second call happened."""
    node = RESTClientNode()
    transport = RecordingTransport(
        [{"data": [1, 2]}, {"data": [3, 4]}, {"data": [5, 6]}]
    )
    node.http_node = transport  # type: ignore[assignment]

    result = node.run(
        base_url=BASE,
        resource=RESOURCE,
        method="GET",
        query_params={"page": "1", "per_page": "2"},
        timeout=17,
        paginate=True,
        pagination_params={"type": "page", "items_path": "data", "max_pages": 3},
        **AUTH_KWARGS,
    )

    assert result["data"] == [1, 2, 3, 4, 5, 6]
    assert len(transport.calls) == 3, "1 initial + 2 follow-up requests"

    for index, call in enumerate(transport.calls[1:], start=1):
        for key, expected in AUTH_KWARGS.items():
            assert call.get(key) == expected, (
                f"follow-up call{index} dropped {key!r}: "
                f"got {call.get(key)!r}, want {expected!r}"
            )


def test_followup_pages_do_not_replay_the_originating_request_body():
    """No-false-positive guard for the whole-dict threading: inheriting the
    originating kwargs must NOT drag the POST body onto a follow-up GET."""
    node = RESTClientNode()
    transport = RecordingTransport(
        [{"data": [1, 2]}, {"data": [3, 4]}, {"data": [5, 6]}]
    )
    node.http_node = transport  # type: ignore[assignment]

    node.run(
        base_url=BASE,
        resource=RESOURCE,
        method="GET",
        query_params={"page": "1", "per_page": "2"},
        data={"unexpected": "body"},
        paginate=True,
        pagination_params={"type": "page", "items_path": "data", "max_pages": 3},
        **AUTH_KWARGS,
    )

    for call in transport.calls[1:]:
        assert call["method"] == "GET"
        assert call["json_data"] is None
        assert call["data"] is None
        assert call["params"]["page"] in ("2", "3")


# --------------------------------------------------------------------------
# C2 — cursor dedup is a bounded set, not a single slot
# --------------------------------------------------------------------------


def test_alternating_cursor_cycle_is_detected():
    """A -> B -> A -> B defeats a single-slot dedup entirely. Measured before
    the fix at ``max_pages=6``: cursors ``['A','B','A','B','A']`` and items
    ``[1, 99, 99, 99, 99, 99]`` — five duplicate pages appended."""
    node = RESTClientNode()

    class CyclingTransport(RecordingTransport):
        def execute(self, **kwargs):
            self.calls.append(kwargs)
            if not kwargs.get("url"):
                raise NodeValidationError("URL parameter is required")
            requested = kwargs["params"]["cursor"]
            nxt = "B" if requested == "A" else "A"
            return http_result({"items": [99], "meta": {"next": nxt}})

    transport = CyclingTransport([])
    node.http_node = transport  # type: ignore[assignment]

    all_items = node._handle_pagination(
        {"items": [1], "meta": {"next": "A"}},
        {},
        {
            "type": "cursor",
            "items_path": "items",
            "next_page_path": "meta.next",
            "cursor_param": "cursor",
            "max_pages": 6,
        },
        request_url=FULL_URL,
        request_headers={},
        request_timeout=30,
    )

    assert [c["params"]["cursor"] for c in transport.calls] == ["A", "B"], (
        "each cursor must be requested at most once; a cycle longer than 1 "
        "defeats a single-slot dedup"
    )
    assert all_items == [1, 99, 99]


def test_seen_cursor_set_is_bounded_by_max_pages():
    """The set is bounded BY CONSTRUCTION: one cursor added per loop iteration,
    and the loop is bounded by ``max_pages``. Asserted behaviourally — a server
    handing back an endless stream of fresh cursors stops at ``max_pages``."""
    node = RESTClientNode()

    class EndlessTransport(RecordingTransport):
        def execute(self, **kwargs):
            self.calls.append(kwargs)
            return http_result(
                {"items": [0], "meta": {"next": f"c{len(self.calls) + 1}"}}
            )

    transport = EndlessTransport([])
    node.http_node = transport  # type: ignore[assignment]

    all_items = node._handle_pagination(
        {"items": [1], "meta": {"next": "c1"}},
        {},
        {
            "type": "cursor",
            "items_path": "items",
            "next_page_path": "meta.next",
            "cursor_param": "cursor",
            "max_pages": 4,
        },
        request_url=FULL_URL,
        request_headers={},
        request_timeout=30,
    )

    assert len(transport.calls) == 3, "max_pages caps follow-ups at max_pages-1"
    assert len(all_items) == 4


# --------------------------------------------------------------------------
# C3 — the transport-failure sink is masked
# --------------------------------------------------------------------------


def test_pagination_transport_failure_is_logged_masked(caplog):
    """Parity with ``http.py``'s rendered-exception sinks. Defence-in-depth: no
    concrete credential has been traced to this sink, but a driver renders the
    full request URL — credentials and all — into its exception text."""
    node = RESTClientNode()
    leaky = "connection failed for https://user:hunter2@api.example.com/items"

    class ExplodingTransport(RecordingTransport):
        def execute(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError(leaky)

    node.http_node = ExplodingTransport([])  # type: ignore[assignment]

    with caplog.at_level(logging.WARNING):
        all_items = node._handle_pagination(
            {"data": [1, 2]},
            {"page": "1", "per_page": "2"},
            {"type": "page", "items_path": "data", "max_pages": 3},
            request_url=FULL_URL,
            request_headers={},
            request_timeout=30,
        )

    assert all_items == [1, 2], "a transport failure still degrades to page 1"
    assert "hunter2" not in caplog.text, "credential rendered into the log sink"
    assert "***@api.example.com" in caplog.text, "masked form must still be logged"


# --------------------------------------------------------------------------
# C4 — the accumulator does not alias the caller's list
# --------------------------------------------------------------------------


def test_pagination_does_not_mutate_the_callers_response_list():
    """Measured before the fix: a caller dict ``{"data":[1,2]}`` became
    ``{"data":[1,2,3,4]}`` and ``out is resp["data"]`` was ``True``."""
    node = RESTClientNode()
    transport = RecordingTransport([{"data": [3, 4]}, {"data": [5, 6]}])
    node.http_node = transport  # type: ignore[assignment]

    caller_response = {"data": [1, 2]}
    out = node._handle_pagination(
        caller_response,
        {"page": "1", "per_page": "2"},
        {"type": "page", "items_path": "data", "max_pages": 3},
        request_url=FULL_URL,
        request_headers={},
        request_timeout=30,
    )

    assert out == [1, 2, 3, 4, 5, 6]
    assert out is not caller_response["data"], "must not alias the caller's list"
    assert caller_response["data"] == [1, 2], "caller's response must be untouched"


def test_early_return_also_does_not_alias():
    """The no-additional-pages short circuit returns a copy too, so the
    non-aliasing guarantee does not depend on which exit is taken."""
    node = RESTClientNode()
    node.http_node = RecordingTransport([])  # type: ignore[assignment]

    caller_response = {"items": [1], "meta": {}}
    out = node._handle_pagination(
        caller_response,
        {},
        {
            "type": "cursor",
            "items_path": "items",
            "next_page_path": "meta.next",
            "max_pages": 3,
        },
        request_url=FULL_URL,
        request_headers={},
        request_timeout=30,
    )

    assert out == [1]
    assert out is not caller_response["items"]
