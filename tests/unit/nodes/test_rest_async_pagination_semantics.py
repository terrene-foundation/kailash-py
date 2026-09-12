"""Async pagination loop semantics: page counting, cycle safety, unresolvable page 1.

Three correctness defects in ``RESTClientNode._handle_async_pagination``. All
three share one root shape -- the async loop was written as "fetch until the
links or the budget run out", while the SYNC sibling (``_handle_pagination`` /
``_paginate_with_page_count``) was written as "merge until a page contributes
nothing". Where the two disagree, the OUTPUT KEY they both populate --
``metadata["total_pages_fetched"]`` -- means two different things.

C-F2 -- ``total_pages_fetched`` counted FETCHES, not MERGES.
    The async loop incremented ``page_count`` on any successful fetch, even one
    that contributed zero items, and never stopped for an empty page. The sync
    sibling breaks on the FIRST empty page and documents that "a trailing empty
    page -- which ends the loop WITHOUT merging -- is not counted"
    (``_paginate_with_page_count`` docstring). A server handing back empty pages
    forever therefore burned the whole ``max_pages`` budget and reported every
    wasted round-trip as a merged page.

C-F3 -- the cursor seen-set was never carried across to the link-follow loop.
    The sync path grew ``seen_cursors`` (#2231) because a single-slot
    "compare to the previous one" check never catches a server alternating
    A -> B -> A -> B. The async loop, whose next-URL comes from the response
    BODY and is therefore MORE attacker-influenced, had no protection at all:
    a two-link cycle re-merged the same pages until the budget ran out.

C-F5 -- an unresolvable page 1 silently suppressed every merge.
    When ``items_path`` does not resolve in page 1's body, ``all_data`` was set
    to the page-1 ENVELOPE (a dict), and the merge was guarded by
    ``isinstance(all_data, list)`` -- False forever. Every subsequent page was
    fetched, counted, and DISCARDED, and because the reported page count
    exceeded 1 the shared ``_drop_stale_pagination_metadata`` helper then
    stripped the very ``links`` the caller needed to walk the pages by hand.
    Strictly worse than not paginating at all.

Every test carries BOTH poles: the defect fixture AND a well-behaved fixture
that must still merge normally, so a fix that simply stops paginating cannot
pass. Transport doubles are built from the REAL declared ``HTTPResponse``
model nested under ``"response"``, the shape
``AsyncHTTPRequestNode.async_run`` actually returns -- see
``test_rest_async_pagination_guard.py`` for why a hand-written shape makes
these tests a no-op.
"""

import logging
from typing import Any

from kailash.nodes.api.http import HTTPResponse
from kailash.nodes.api.rest import RESTClientNode

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"


def transport_return(content, *, status=200, headers=None, url=FULL_URL):
    """Build the REAL ``AsyncHTTPRequestNode.async_run`` return envelope."""
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


class RoutingTransport:
    """Answers by URL, so a cycling server can be modelled honestly."""

    def __init__(self, routes, default=None):
        self.routes = dict(routes)
        self.default = default
        self.calls = []

    async def async_run(self, **kwargs):
        url = kwargs.get("url")
        self.calls.append(kwargs)
        if url in self.routes:
            return self.routes[url]
        if self.default is not None:
            return self.default
        return transport_return(page([]), url=str(url))

    @property
    def urls(self):
        return [call.get("url") for call in self.calls]


def page(items, next_link=None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": list(items)}
    if next_link is not None:
        body["links"] = {"next": next_link}
    return body


def make_node(transport):
    node = RESTClientNode()
    node._async_http_node = transport  # type: ignore[attr-defined]
    return node


async def paginate(transport, first_body, *, max_pages=6, items_path=None):
    """Run the async loop over ``first_body`` as page 1."""
    node = make_node(transport)
    initial = transport_return(first_body, url=FULL_URL)
    pagination_params: dict[str, Any] = {"max_pages": max_pages}
    if items_path is not None:
        pagination_params["items_path"] = items_path
    kwargs = {
        "headers": {},
        "paginate": True,
        "pagination_params": pagination_params,
    }
    result = node._build_async_result(initial, FULL_URL, "GET")
    return await node._handle_async_pagination(result, kwargs)


# ---------------------------------------------------------------------------
# C-F2 -- total_pages_fetched must mean "pages MERGED" on BOTH paths
# ---------------------------------------------------------------------------


async def test_empty_page_ends_the_walk_and_is_not_counted():
    """A page that contributes no items ends the loop and is NOT counted.

    Defect pole. The server hands back an empty page (which RESOLVES -- the
    ``items_path`` is present, the list is just empty) with a next link,
    forever. Before the fix the loop fetched to the ``max_pages`` budget and
    reported every wasted round-trip in ``total_pages_fetched``, so the same
    output key meant "pages FETCHED" here and "pages MERGED" on the sync path.
    """
    empty = transport_return(
        page([], next_link=f"{FULL_URL}?page=3"), url=f"{FULL_URL}?page=2"
    )
    transport = RoutingTransport({}, default=empty)

    result = await paginate(
        transport, page([1, 2], next_link=f"{FULL_URL}?page=2"), max_pages=6
    )

    assert result["data"] == [1, 2]
    # "pages MERGED" -- page 1 only. The trailing empty page ends the loop
    # WITHOUT merging, exactly as `_paginate_with_page_count` documents.
    assert result["metadata"]["total_pages_fetched"] == 1
    # And the walk STOPS at the first empty page instead of burning the budget.
    assert len(transport.calls) == 1


async def test_non_empty_pages_are_all_merged_and_counted():
    """Opposite pole: a real 3-page walk still merges and counts all three."""
    transport = RoutingTransport(
        {
            f"{FULL_URL}?page=2": transport_return(
                page([3, 4], next_link=f"{FULL_URL}?page=3"), url=f"{FULL_URL}?page=2"
            ),
            f"{FULL_URL}?page=3": transport_return(
                page([5, 6]), url=f"{FULL_URL}?page=3"
            ),
        }
    )

    result = await paginate(
        transport, page([1, 2], next_link=f"{FULL_URL}?page=2"), max_pages=6
    )

    assert result["data"] == [1, 2, 3, 4, 5, 6]
    assert result["metadata"]["total_pages_fetched"] == 3


# ---------------------------------------------------------------------------
# C-F3 -- a cycling server must not re-merge pages it already served
# ---------------------------------------------------------------------------


async def test_cycling_next_links_stop_instead_of_duplicating_records(caplog):
    """Defect pole: links cycling A -> B -> A re-merged the same pages.

    The sync path closed this in #2231 with ``seen_cursors``; the async
    link-follow loop -- whose URL comes from the response BODY -- had nothing.
    """
    url_a = f"{FULL_URL}?page=A"
    url_b = f"{FULL_URL}?page=B"
    transport = RoutingTransport(
        {
            url_a: transport_return(page([3, 4], next_link=url_b), url=url_a),
            url_b: transport_return(page([5, 6], next_link=url_a), url=url_b),
        }
    )

    with caplog.at_level(logging.WARNING):
        result = await paginate(transport, page([1, 2], next_link=url_a), max_pages=6)

    # Each page appears EXACTLY once.
    assert result["data"] == [1, 2, 3, 4, 5, 6]
    assert result["metadata"]["total_pages_fetched"] == 3
    # The repeat is refused BEFORE the wasted round-trip.
    assert transport.urls == [url_a, url_b]
    assert any(
        "already requested" in record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


async def test_distinct_next_links_still_walk_every_page(caplog):
    """Opposite pole: three DISTINCT URLs must still all be walked."""
    url_a = f"{FULL_URL}?page=A"
    url_b = f"{FULL_URL}?page=B"
    transport = RoutingTransport(
        {
            url_a: transport_return(page([3, 4], next_link=url_b), url=url_a),
            url_b: transport_return(page([5, 6]), url=url_b),
        }
    )

    with caplog.at_level(logging.WARNING):
        result = await paginate(transport, page([1, 2], next_link=url_a), max_pages=6)

    assert result["data"] == [1, 2, 3, 4, 5, 6]
    assert result["metadata"]["total_pages_fetched"] == 3
    assert transport.urls == [url_a, url_b]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# C-F5 -- an unresolvable page 1 must not enter the walk at all
# ---------------------------------------------------------------------------


async def test_unresolvable_first_page_returns_page_one_with_metadata_intact(caplog):
    """Defect pole: ``items_path`` does not resolve in page 1's body.

    ``page_items`` returns ``None`` (the shape did not resolve) -- which is a
    DIFFERENT condition from returning ``[]`` (resolved, but empty, C-F2).
    Before the fix the envelope became ``all_data``, the ``isinstance(list)``
    merge guard was False forever, and the loop fetched-counted-DISCARDED the
    whole budget -- then reported >1 page, which made the shared stripper
    delete the ``links`` the caller needed to walk by hand.
    """
    envelope = {"results": [1, 2], "links": {"next": f"{FULL_URL}?page=2"}}
    transport = RoutingTransport(
        {},
        default=transport_return(page([3, 4], next_link=f"{FULL_URL}?page=3")),
    )

    with caplog.at_level(logging.WARNING):
        # items_path defaults to "data", which this body does not carry.
        result = await paginate(transport, envelope, max_pages=6)

    # Page 1 returned UNCHANGED...
    assert result["data"] == envelope
    # ...with no walk attempted at all...
    assert transport.calls == []
    # ...counted as the one page it is, so the shared stripper leaves the
    # navigation metadata alone...
    assert result["metadata"]["total_pages_fetched"] == 1
    assert result["metadata"]["links"]["next"] == f"{FULL_URL}?page=2"
    # ...and the misconfiguration is diagnosable by name.
    assert any(
        "items_path 'data'" in record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


async def test_resolvable_first_page_under_custom_items_path_still_walks():
    """Opposite pole: the SAME body walks normally when items_path resolves."""
    envelope = {"results": [1, 2], "links": {"next": f"{FULL_URL}?page=2"}}
    transport = RoutingTransport(
        {
            f"{FULL_URL}?page=2": transport_return(
                {"results": [3, 4]}, url=f"{FULL_URL}?page=2"
            )
        }
    )

    result = await paginate(transport, envelope, max_pages=6, items_path="results")

    assert result["data"] == [1, 2, 3, 4]
    assert result["metadata"]["total_pages_fetched"] == 2


async def test_empty_but_resolved_first_page_still_enters_the_walk():
    """``[]`` is RESOLVED: page 1 carrying zero items must still paginate.

    This is the discrimination C-F5's fix must not over-reach on. ``None``
    (shape did not resolve) stops the walk; ``[]`` (resolved, empty) does not.
    """
    transport = RoutingTransport(
        {f"{FULL_URL}?page=2": transport_return(page([1, 2]), url=f"{FULL_URL}?page=2")}
    )

    result = await paginate(
        transport, page([], next_link=f"{FULL_URL}?page=2"), max_pages=6
    )

    assert result["data"] == [1, 2]
    assert result["metadata"]["total_pages_fetched"] == 2
