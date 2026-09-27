"""Event-loop liveness and pagination metadata for ``AsyncRESTClientNode``.

Issue #2230, sub-task 4 (blocking I/O) plus the stale-metadata residual flagged
during the same wave.

**Sub-task 4.** ``AsyncRESTClientNode.async_run`` is a coroutine, but when
``paginate=True`` it delegated to the SYNCHRONOUS
``RESTClientNode._handle_pagination``, which issues every follow-up page
through a ``requests``-backed node. Called inline from the coroutine that held
the event loop, that stalls the loop for up to ``(max_pages - 1) * timeout``
seconds and starves every other task on it. The defect was latent only because
the constructor bug (fixed earlier in this issue) made the node unreachable.

**Residual.** ``metadata`` is assembled from the FIRST page's response after
pagination has already merged N pages into ``data``. A ``Link`` header carrying
``rel="next"`` therefore advertises a page that is ALREADY inside ``data``, and
a consumer that follows it re-fetches what it has.

Discrimination
--------------
A test asserting only "pagination returned N items" passes identically on the
blocking and non-blocking implementations, so it is not evidence for either.
``test_pagination_does_not_block_the_event_loop`` instead runs a concurrent
heartbeat task while a paginating ``async_run`` is in flight with a
deliberately slow synchronous transport, and asserts the heartbeat ADVANCED.
That assertion is false on the blocking implementation (the loop never gets
control back) and true on the offloaded one. Its falsifying result was
observed: against the inline call it fails with ``ticks_during=0``.

Every transport double below returns the REAL declared return shape —
``{"response": HTTPResponse(...).model_dump(), "status_code", "success"}``,
built by actually constructing ``HTTPResponse`` from ``kailash.nodes.api.http``
— because a double shaped from the CALL SITE rather than the declared type is
how an earlier attempt in this wave shipped a no-op.
"""

import asyncio
import time
from pathlib import Path

import pytest

from kailash.nodes.api import rest as rest_module
from kailash.nodes.api.http import HTTPResponse
from kailash.nodes.api.rest import AsyncRESTClientNode

_WORKTREE_ROOT = Path(__file__).resolve().parents[3]

_BASE_URL = "https://api.example.test"
_PAGE_URL = f"{_BASE_URL}/items"
_NEXT_LINK = f'<{_PAGE_URL}?page=2>; rel="next"'

# Page 1 of 4, two items per page, eight items in total. ``max_pages`` caps the
# run at 4, so exactly three follow-up pages are requested.
_PER_PAGE = 2
_TOTAL_ITEMS = 8
_MAX_PAGES = 4

_PAGINATION_PARAMS = {
    "type": "page",
    "page_param": "page",
    "limit_param": "per_page",
    "items_path": "data",
    "total_path": "meta.total",
    "max_pages": _MAX_PAGES,
}


def test_module_under_test_is_this_checkout():
    """Guard: pytest in a worktree can silently import a different checkout.

    Without this, a green run would not discriminate between "the fix in THIS
    tree works" and "another tree's already-fixed copy was imported".
    """
    assert Path(rest_module.__file__).resolve().is_relative_to(_WORKTREE_ROOT), (
        f"rest.py imported from {rest_module.__file__}, "
        f"which is outside the checkout under test ({_WORKTREE_ROOT})"
    )


# --------------------------------------------------------------------------
# Doubles — built from the REAL declared return type, never from the call site.
# --------------------------------------------------------------------------


def _transport_payload(
    items,
    *,
    headers=None,
    total=_TOTAL_ITEMS,
    status=200,
    url=_PAGE_URL,
):
    """One transport return, shaped exactly as both HTTP nodes shape theirs.

    ``HTTPRequestNode.run`` (http.py:690-700) and
    ``AsyncHTTPRequestNode.async_run`` (http.py:1046-1062) both return
    ``{"response": HTTPResponse(...).model_dump(), "status_code", "success"}``.
    Constructing the real model here means a field rename in ``HTTPResponse``
    breaks this double loudly instead of letting it drift into fiction.
    """
    content = {"data": list(items), "meta": {"total": total}}
    return {
        "response": HTTPResponse(
            status_code=status,
            headers=dict(headers or {}),
            content_type="application/json",
            content=content,
            response_time_ms=1.5,
            url=url,
        ).model_dump(),
        "status_code": status,
        "success": 200 <= status < 300,
    }


class _FirstPageAsyncTransport:
    """Stands in for ``AsyncHTTPRequestNode`` — serves page 1 only."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def async_run(self, **kwargs):
        self.calls += 1
        # Real async I/O yields to the loop at least once; so does this.
        await asyncio.sleep(0)
        return self._payload


class _SlowSyncTransport:
    """Stands in for ``HTTPRequestNode`` — serves follow-up pages, slowly.

    ``time.sleep`` is the faithful model of a ``requests`` call: it blocks the
    calling THREAD. Whether it also blocks the event LOOP is precisely the
    property under test, and is decided by where the caller runs it.
    """

    def __init__(self, pages, delay):
        self._pages = list(pages)
        self._delay = delay
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        time.sleep(self._delay)
        if not self._pages:
            return _transport_payload([])
        return self._pages.pop(0)


def _build_node(
    *, first_page_headers=None, total=_TOTAL_ITEMS, delay=0.0, follow_up_pages=None
):
    node = AsyncRESTClientNode(base_url=_BASE_URL, resource="items")
    first_page = _transport_payload(
        [{"id": 1}, {"id": 2}], headers=first_page_headers, total=total
    )
    async_transport = _FirstPageAsyncTransport(first_page)
    if follow_up_pages is None:
        follow_up_pages = [
            _transport_payload([{"id": 3}, {"id": 4}], total=total),
            _transport_payload([{"id": 5}, {"id": 6}], total=total),
            _transport_payload([{"id": 7}, {"id": 8}], total=total),
        ]
    sync_transport = _SlowSyncTransport(follow_up_pages, delay)
    node.http_node = async_transport
    node.rest_node.http_node = sync_transport
    return node, async_transport, sync_transport


def _run_kwargs(**overrides):
    kwargs = {
        "base_url": _BASE_URL,
        "resource": "items",
        "method": "GET",
        "query_params": {"per_page": _PER_PAGE},
        "paginate": True,
        "pagination_params": dict(_PAGINATION_PARAMS),
    }
    kwargs.update(overrides)
    return kwargs


async def _heartbeat(state, interval=0.002):
    """Increments a counter every few ms — only while the loop has control."""
    while True:
        state["ticks"] += 1
        await asyncio.sleep(interval)


# --------------------------------------------------------------------------
# Sub-task 4 — the event loop must stay live across paginated follow-ups.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_does_not_block_the_event_loop():
    delay = 0.12  # per follow-up page; three pages => ~0.36s of transport time
    node, async_transport, sync_transport = _build_node(delay=delay)

    state = {"ticks": 0}
    heartbeat = asyncio.create_task(_heartbeat(state))
    # Let the heartbeat reach its first await, then count only the ticks that
    # land WHILE async_run is in flight.
    await asyncio.sleep(0.02)
    state["ticks"] = 0

    started = time.monotonic()
    result = await node.async_run(**_run_kwargs())
    elapsed = time.monotonic() - started
    ticks_during = state["ticks"]

    heartbeat.cancel()
    try:
        await heartbeat
    except asyncio.CancelledError:
        pass

    # The run must genuinely have paginated, or the liveness assertion below
    # would be vacuous: a run that never fetched a follow-up page cannot block.
    assert async_transport.calls == 1
    assert sync_transport.calls == 3, "expected three follow-up page requests"
    assert [item["id"] for item in result["data"]] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert elapsed >= 3 * delay, "transport delay did not actually elapse"

    # ~0.36s of blocking transport at a 2ms heartbeat is ~180 ticks when the
    # loop stays live. The inline (blocking) implementation yields none of
    # them: it holds the loop for the whole span. 20 is a wide margin that
    # still cannot be reached by a held loop.
    assert ticks_during >= 20, (
        "event loop was starved during pagination: heartbeat advanced only "
        f"{ticks_during} ticks across {elapsed:.3f}s of paginated transport"
    )


@pytest.mark.asyncio
async def test_concurrent_coroutine_completes_while_pagination_runs():
    """Stronger form: a sibling coroutine must FINISH mid-pagination.

    The heartbeat test measures progress; this one measures completion
    ordering, which a held loop cannot produce however long it holds.
    """
    delay = 0.12
    node, _, sync_transport = _build_node(delay=delay)
    order = []

    async def sibling():
        await asyncio.sleep(0.05)
        order.append("sibling")

    sibling_task = asyncio.create_task(sibling())
    await node.async_run(**_run_kwargs())
    order.append("pagination")
    await sibling_task

    assert sync_transport.calls == 3
    assert order == ["sibling", "pagination"], (
        "the sibling coroutine did not get the loop back during pagination; "
        f"completion order was {order}"
    )


# --------------------------------------------------------------------------
# Residual — page 1's navigation headers must not survive a multi-page merge.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_page_result_does_not_advertise_a_consumed_next_link():
    node, _, sync_transport = _build_node(
        first_page_headers={"Link": _NEXT_LINK, "X-Total-Count": str(_TOTAL_ITEMS)}
    )

    result = await node.async_run(**_run_kwargs())
    headers = result["metadata"]["headers"]

    assert sync_transport.calls == 3
    assert len(result["data"]) == _TOTAL_ITEMS
    assert not any(name.lower() == "link" for name in headers), (
        "metadata still advertises page 1's next link after pagination merged "
        f"{_MAX_PAGES} pages into data: {headers!r}"
    )
    # Non-navigation headers are untouched — the fix removes a factually-wrong
    # field, it does not blank the header set.
    assert headers["X-Total-Count"] == str(_TOTAL_ITEMS)


@pytest.mark.asyncio
async def test_multi_page_result_records_pages_fetched():
    node, _, sync_transport = _build_node()

    result = await node.async_run(**_run_kwargs())

    assert sync_transport.calls == 3
    assert result["metadata"]["total_pages_fetched"] == _MAX_PAGES
    # The page counter is installed on a per-call copy: the shared REST node's
    # own transport must be exactly what it was, or two concurrent paginating
    # calls on one node instance would corrupt each other's counts.
    assert node.rest_node.http_node is sync_transport


@pytest.mark.asyncio
async def test_pages_fetched_counts_merged_pages_not_requests():
    """The count must mirror what ``_handle_pagination`` actually merged.

    A trailing page with no items ends that method's loop WITHOUT counting,
    so three follow-up REQUESTS here yield two merged pages plus page 1. An
    implementation that simply tallied transport calls would report 4; this
    asserts 3, so the two implementations are distinguishable.
    """
    node, _, sync_transport = _build_node(
        follow_up_pages=[
            _transport_payload([{"id": 3}, {"id": 4}]),
            _transport_payload([]),  # server ran out early
        ]
    )

    result = await node.async_run(**_run_kwargs())

    assert sync_transport.calls == 2, "second follow-up should have ended the loop"
    assert len(result["data"]) == 4
    assert result["metadata"]["total_pages_fetched"] == 2


@pytest.mark.asyncio
async def test_single_page_result_keeps_its_next_link():
    """CONTROL — the fix is conditional on pagination actually spanning pages.

    With ``total`` equal to one page's worth, ``_handle_pagination`` returns
    before issuing any follow-up, so page 1's headers still describe ``data``
    exactly and must be presented unaltered. Without this control the
    stale-link assertion above would also pass an implementation that simply
    deleted every ``Link`` header.
    """
    node, _, sync_transport = _build_node(
        first_page_headers={"Link": _NEXT_LINK}, total=_PER_PAGE
    )

    result = await node.async_run(**_run_kwargs())

    assert sync_transport.calls == 0, "no follow-up page should have been requested"
    assert len(result["data"]) == _PER_PAGE
    assert result["metadata"]["headers"]["Link"] == _NEXT_LINK
    assert result["metadata"]["total_pages_fetched"] == 1


@pytest.mark.asyncio
async def test_non_paginated_request_reports_no_page_count():
    """``total_pages_fetched`` is a pagination fact; it is absent otherwise."""
    node, _, sync_transport = _build_node(first_page_headers={"Link": _NEXT_LINK})

    result = await node.async_run(**_run_kwargs(paginate=False))

    assert sync_transport.calls == 0
    assert "total_pages_fetched" not in result["metadata"]
    assert result["metadata"]["headers"]["Link"] == _NEXT_LINK
    # Un-paginated, ``data`` is the raw envelope, not a merged item list.
    assert result["data"]["data"] == [{"id": 1}, {"id": 2}]


@pytest.mark.asyncio
async def test_follow_up_pages_still_receive_the_originating_transport_kwargs():
    """Regression pin: offloading must not drop ``request_kwargs`` threading.

    A sibling shard fixed follow-up-page auth by threading the originating
    ``http_params`` dict whole into ``_handle_pagination``. Running that call
    in a worker thread must preserve it.
    """
    node, _, sync_transport = _build_node()
    seen = []

    original_execute = sync_transport.execute

    def recording_execute(**kwargs):
        seen.append(kwargs)
        return original_execute(**kwargs)

    sync_transport.execute = recording_execute

    await node.async_run(
        **_run_kwargs(auth_type="bearer", auth_token="s3cret", verify_ssl=False)
    )

    assert len(seen) == 3
    for call in seen:
        assert call["auth_type"] == "bearer"
        assert call["auth_token"] == "s3cret"
        assert call["verify_ssl"] is False
        assert call["method"] == "GET"
