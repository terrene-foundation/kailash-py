"""Stale pagination metadata on the SYNCHRONOUS ``RESTClientNode.run``.

Issue #2231 item 5 (downstream half), sync side.

``RESTClientNode.run`` assembles its returned ``metadata`` from the FIRST
page's response *after* ``_handle_pagination`` has already merged N pages into
``data``. Worse than the async sibling: it calls
``metadata.update(self._extract_metadata(response))``, which injects page 1's
``pagination`` block (``next``/``prev`` URLs parsed out of the ``Link`` header)
and its HATEOAS ``links`` block into a result that already CONTAINS those
pages. A consumer following ``metadata["links"]["next"]`` re-fetches data it
was just handed, and nothing in the return says how many pages ``data``
actually spans.

Discrimination
--------------
Every assertion below is written so that the pre-fix implementation produces a
named, readable failure rather than an error:

* ``test_sync_multi_page_*`` — the pre-fix run returns ``links``/``pagination``
  /``Link`` intact and no ``total_pages_fetched``; each is asserted with
  ``in``/``not in`` on a dict, never by indexing, so the red is an assertion
  message and not a ``KeyError``.
* ``test_single_page_*`` / ``test_non_paginated_*`` are the NO-FALSE-POSITIVE
  poles: they fail on an implementation that strips unconditionally, which is
  exactly the over-broad fix the stripping tests alone would accept.
* ``test_both_clients_route_through_one_page_counter`` pins the SINGLE-SOURCE
  property. Two copies of the page-counting proxy would satisfy every
  behavioural assertion in this file on the day they are written and then
  drift; this module has already paid that price once (the divergent async
  result shaping that returned ``data=None`` on every call).

Every transport double returns the REAL declared return shape —
``{"response": HTTPResponse(...).model_dump(), "status_code", "success"}`` —
built by actually constructing ``HTTPResponse`` from ``kailash.nodes.api.http``
(``http.py:97-109``). A double shaped from the CALL SITE rather than the
declared type is how an earlier attempt in this wave shipped a no-op.
"""

import asyncio
from pathlib import Path

import pytest

from kailash.nodes.api import rest as rest_module
from kailash.nodes.api.http import HTTPResponse
from kailash.nodes.api.rest import AsyncRESTClientNode, RESTClientNode

_WORKTREE_ROOT = Path(__file__).resolve().parents[3]

_BASE_URL = "https://api.example.test"
_PAGE_URL = f"{_BASE_URL}/items"
_NEXT_URL = f"{_PAGE_URL}?page=2"
_NEXT_LINK = f'<{_NEXT_URL}>; rel="next"'

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
    links=None,
    status=200,
    url=_PAGE_URL,
):
    """One transport return, shaped exactly as ``HTTPRequestNode`` shapes its own."""
    content = {"data": list(items), "meta": {"total": total}}
    if links is not None:
        content["links"] = dict(links)
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


class _SyncTransport:
    """Stands in for ``HTTPRequestNode`` — serves page 1 then follow-ups."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        if not self._pages:
            return _transport_payload([])
        return self._pages.pop(0)


class _FirstPageAsyncTransport:
    """Stands in for ``AsyncHTTPRequestNode`` — serves page 1 only."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def async_run(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0)
        return self._payload


def _first_page(*, headers=None, total=_TOTAL_ITEMS, links=None):
    return _transport_payload(
        [{"id": 1}, {"id": 2}], headers=headers, total=total, links=links
    )


def _default_follow_ups(total=_TOTAL_ITEMS):
    return [
        _transport_payload([{"id": 3}, {"id": 4}], total=total),
        _transport_payload([{"id": 5}, {"id": 6}], total=total),
        _transport_payload([{"id": 7}, {"id": 8}], total=total),
    ]


def _build_sync_node(*, headers=None, total=_TOTAL_ITEMS, links=None, follow_ups=None):
    node = RESTClientNode(base_url=_BASE_URL, resource="items")
    pages = [_first_page(headers=headers, total=total, links=links)]
    pages.extend(_default_follow_ups(total) if follow_ups is None else follow_ups)
    transport = _SyncTransport(pages)
    node.http_node = transport
    return node, transport


def _build_async_node(*, headers=None, total=_TOTAL_ITEMS, links=None, follow_ups=None):
    node = AsyncRESTClientNode(base_url=_BASE_URL, resource="items")
    node.http_node = _FirstPageAsyncTransport(
        _first_page(headers=headers, total=total, links=links)
    )
    follow_transport = _SyncTransport(
        _default_follow_ups(total) if follow_ups is None else follow_ups
    )
    node.rest_node.http_node = follow_transport
    return node, follow_transport


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


# --------------------------------------------------------------------------
# F2 — the merged result must not advertise pages it already contains.
# --------------------------------------------------------------------------


def test_sync_multi_page_result_drops_every_stale_navigation_pointer():
    """All three pointers page 1 carried are factually wrong after the merge."""
    node, transport = _build_sync_node(
        headers={"Link": _NEXT_LINK, "X-Total-Count": str(_TOTAL_ITEMS)},
        links={"next": _NEXT_URL, "self": _PAGE_URL},
    )

    result = node.run(**_run_kwargs())
    metadata = result["metadata"]

    # The run must genuinely have merged pages, or the assertions below would
    # be vacuous — a single-page run has nothing stale to drop.
    assert transport.calls == _MAX_PAGES, "expected page 1 plus three follow-ups"
    assert [item["id"] for item in result["data"]] == [1, 2, 3, 4, 5, 6, 7, 8]

    assert not any(name.lower() == "link" for name in metadata["headers"]), (
        "metadata still advertises page 1's Link header after pagination "
        f"merged {_MAX_PAGES} pages into data: {metadata['headers']!r}"
    )
    # Finding C-F4: the NAVIGATION half of these blocks is what the merge
    # falsified. The DESCRIPTIVE half still describes the collection and is
    # kept -- see test_rest_pagination_metadata_split.py for the full contract.
    assert "next" not in metadata.get("links", {}), (
        "metadata['links'] still points at a page already inside data: "
        f"{metadata.get('links')!r}"
    )
    assert metadata["links"]["self"] == _PAGE_URL, (
        "the collection-scoped 'self' relation was dropped; the merge did not "
        f"falsify it: {metadata.get('links')!r}"
    )
    assert "next" not in metadata.get("pagination", {}), (
        "metadata['pagination'] still points at a page already inside data: "
        f"{metadata.get('pagination')!r}"
    )
    # ...while the record count it also carried is a fact about the
    # COLLECTION that the merge did not falsify.
    assert metadata["pagination"]["total"] == _TOTAL_ITEMS, (
        "the record count was dropped along with the stale pointers: "
        f"{metadata.get('pagination')!r}"
    )
    # The fix removes factually-wrong fields; it does not blank the header set.
    assert metadata["headers"]["X-Total-Count"] == str(_TOTAL_ITEMS)


def test_sync_multi_page_result_drops_a_lowercase_link_header():
    """Header names are case-insensitive on the wire; the strip must be too."""
    node, transport = _build_sync_node(
        headers={"link": _NEXT_LINK, "X-Total-Count": str(_TOTAL_ITEMS)}
    )

    result = node.run(**_run_kwargs())

    assert transport.calls == _MAX_PAGES
    assert not any(
        name.lower() == "link" for name in result["metadata"]["headers"]
    ), f"lowercase 'link' survived the strip: {result['metadata']['headers']!r}"


def test_sync_multi_page_result_records_pages_fetched():
    node, transport = _build_sync_node()

    result = node.run(**_run_kwargs())
    metadata = result["metadata"]

    assert transport.calls == _MAX_PAGES
    assert "total_pages_fetched" in metadata, (
        "sync run() reports no page count at all, so a consumer cannot tell a "
        f"merged result from a single page: {sorted(metadata)}"
    )
    assert metadata["total_pages_fetched"] == _MAX_PAGES


def test_sync_page_count_counts_merged_pages_not_requests():
    """A trailing empty page ends ``_handle_pagination``'s loop WITHOUT counting.

    Two follow-up REQUESTS here yield one merged page plus page 1. An
    implementation that simply tallied transport calls would report 3; this
    asserts 2, so the two implementations are distinguishable.
    """
    node, transport = _build_sync_node(
        follow_ups=[
            _transport_payload([{"id": 3}, {"id": 4}]),
            _transport_payload([]),  # server ran out early
        ]
    )

    result = node.run(**_run_kwargs())

    metadata = result["metadata"]
    assert transport.calls == 3, "page 1 plus two follow-up requests"
    assert len(result["data"]) == 4
    assert (
        "total_pages_fetched" in metadata
    ), f"sync run() reports no page count: {sorted(metadata)}"
    assert metadata["total_pages_fetched"] == 2


# --------------------------------------------------------------------------
# F2 — NO-FALSE-POSITIVE poles. Nothing is stripped when nothing went stale.
# --------------------------------------------------------------------------


def test_single_page_result_keeps_every_navigation_pointer():
    """CONTROL — with one page fetched, page 1's metadata still describes ``data``.

    Without this, the stripping tests above would also pass an implementation
    that deleted ``Link``/``links``/``pagination`` unconditionally.
    """
    node, transport = _build_sync_node(
        headers={"Link": _NEXT_LINK},
        total=_PER_PAGE,  # one page's worth => no follow-up is issued
        links={"next": _NEXT_URL},
    )

    result = node.run(**_run_kwargs())
    metadata = result["metadata"]

    assert transport.calls == 1, "no follow-up page should have been requested"
    assert len(result["data"]) == _PER_PAGE
    assert "Link" in metadata["headers"], (
        "a single-page result's Link header still describes data exactly, but "
        f"it was stripped anyway: {metadata['headers']!r}"
    )
    assert metadata["headers"]["Link"] == _NEXT_LINK
    assert "links" in metadata, (
        "a single-page result's HATEOAS links still describe data exactly, "
        f"but they were stripped anyway: {sorted(metadata)}"
    )
    assert metadata["links"]["next"] == _NEXT_URL
    assert "pagination" in metadata, (
        "a single-page result's pagination block still describes data "
        f"exactly, but it was stripped anyway: {sorted(metadata)}"
    )
    assert metadata["pagination"]["next"] == _NEXT_URL
    assert (
        "total_pages_fetched" in metadata
    ), f"sync run() reports no page count: {sorted(metadata)}"
    assert metadata["total_pages_fetched"] == 1


def test_non_paginated_request_keeps_its_metadata_and_reports_no_page_count():
    """``total_pages_fetched`` is a pagination fact; it is absent otherwise."""
    node, transport = _build_sync_node(
        headers={"Link": _NEXT_LINK}, links={"next": _NEXT_URL}
    )

    result = node.run(**_run_kwargs(paginate=False))
    metadata = result["metadata"]

    assert transport.calls == 1
    assert "total_pages_fetched" not in metadata
    assert metadata["headers"]["Link"] == _NEXT_LINK
    assert metadata["links"]["next"] == _NEXT_URL
    assert metadata["pagination"]["next"] == _NEXT_URL
    # Un-paginated, ``data`` is the raw envelope, not a merged item list.
    assert result["data"]["data"] == [{"id": 1}, {"id": 2}]


def test_non_get_paginate_request_keeps_its_metadata():
    """Pagination is GET-only; a POST must not be re-shaped as if it paginated."""
    node, transport = _build_sync_node(
        headers={"Link": _NEXT_LINK}, links={"next": _NEXT_URL}
    )

    result = node.run(**_run_kwargs(method="POST", data={"name": "x"}))
    metadata = result["metadata"]

    assert transport.calls == 1
    assert "total_pages_fetched" not in metadata
    assert metadata["headers"]["Link"] == _NEXT_LINK
    assert metadata["links"]["next"] == _NEXT_URL


# --------------------------------------------------------------------------
# F1 — the page-counting logic exists in exactly ONE place.
# --------------------------------------------------------------------------


def test_both_clients_route_through_one_page_counter(monkeypatch):
    """Sync ``run`` and async ``async_run`` must call the SAME helper.

    Two copies of the counting proxy satisfy every behavioural assertion in
    this file on the day they are written, then drift. This asserts the shared
    callee directly, so a re-duplication is a test failure and not a silent
    regression.
    """
    assert hasattr(RESTClientNode, "_paginate_with_page_count"), (
        "no shared page-counting helper exists on RESTClientNode; the counting "
        "proxy is duplicated per client"
    )

    original = RESTClientNode._paginate_with_page_count
    callers = []

    def recording(self, *args, **kwargs):
        callers.append(type(self).__name__)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RESTClientNode, "_paginate_with_page_count", recording)

    sync_node, sync_transport = _build_sync_node()
    sync_result = sync_node.run(**_run_kwargs())

    async_node, async_transport = _build_async_node()
    async_result = asyncio.run(async_node.async_run(**_run_kwargs()))

    assert sync_transport.calls == _MAX_PAGES
    assert async_transport.calls == _MAX_PAGES - 1  # page 1 came from the async node
    assert len(sync_result["data"]) == _TOTAL_ITEMS
    assert len(async_result["data"]) == _TOTAL_ITEMS
    assert callers == ["RESTClientNode", "RESTClientNode"], (
        "expected both the sync client and the async client to reach the "
        f"shared page counter; recorded calls: {callers}"
    )


@pytest.mark.parametrize("client", ["sync", "async"])
def test_page_count_semantics_are_identical_on_both_clients(client):
    """The same trailing-empty-page case must count the same on both sides."""
    follow_ups = [
        _transport_payload([{"id": 3}, {"id": 4}]),
        _transport_payload([]),
    ]
    if client == "sync":
        node, _ = _build_sync_node(follow_ups=follow_ups)
        result = node.run(**_run_kwargs())
    else:
        node, _ = _build_async_node(follow_ups=follow_ups)
        result = asyncio.run(node.async_run(**_run_kwargs()))

    metadata = result["metadata"]
    assert len(result["data"]) == 4
    assert (
        "total_pages_fetched" in metadata
    ), f"{client} client reports no page count: {sorted(metadata)}"
    assert metadata["total_pages_fetched"] == 2


def test_sync_pagination_does_not_mutate_the_shared_transport():
    """The counting proxy is installed on a per-call copy, never on the node.

    Two concurrent paginating calls on one node instance would otherwise
    corrupt each other's counts.
    """
    node, transport = _build_sync_node()

    node.run(**_run_kwargs())

    assert node.http_node is transport


def test_sync_follow_up_pages_still_receive_the_originating_transport_kwargs():
    """Regression pin: extraction must not drop the whole-dict kwarg threading."""
    node, transport = _build_sync_node()
    seen = []

    original_execute = transport.execute

    def recording_execute(**kwargs):
        seen.append(kwargs)
        return original_execute(**kwargs)

    transport.execute = recording_execute

    node.run(**_run_kwargs(auth_type="bearer", auth_token="s3cret", verify_ssl=False))

    assert len(seen) == _MAX_PAGES, "page 1 plus three follow-ups"
    for call in seen[1:]:
        assert call["auth_type"] == "bearer"
        assert call["auth_token"] == "s3cret"
        assert call["verify_ssl"] is False
        assert call["method"] == "GET"
