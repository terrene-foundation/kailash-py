"""The HATEOAS async path must not advertise pages it already merged.

``RESTClientNode._handle_async_pagination`` follows ``metadata["links"]["next"]``
until the links run out, then returns every page's items merged into ``data``.
The ``metadata`` it returns, however, is page 1's. Its ``links["next"]``,
``pagination`` block and ``Link`` header therefore point at records that are
ALREADY inside ``data`` -- a consumer that follows the pointer re-fetches what
it was just handed.

This is the third site of one defect: the sync ``run()`` and the
``AsyncRESTClientNode`` page/offset/cursor caller had it too. All three now
finalise through the SAME ``_drop_stale_pagination_metadata`` helper, so a
future change to what a merged result advertises cannot fix one path and leave
the others behind.

This module asserts the METADATA contract only. The separate defect it
originally documented -- DICT-shaped pages being walked, counted, and then
discarded, because the merge branch required the page itself to BE a list --
was fixed alongside the redirect guard; ``test_rest_pagination_redirects.py``
pins the merge behaviour, so it is deliberately not duplicated here.
"""

from typing import Any

import pytest

from kailash.nodes.api.http import HTTPResponse
from kailash.nodes.api.rest import RESTClientNode

pytestmark = pytest.mark.asyncio

BASE = "https://api.example.com"
RESOURCE = "items"
FULL_URL = f"{BASE}/{RESOURCE}"


def transport_return(content, *, status=200, headers=None, url=FULL_URL):
    """Build the REAL ``AsyncHTTPRequestNode.async_run`` return envelope.

    Constructed from the declared ``HTTPResponse`` model rather than a
    hand-written dict, so a field rename REDS here instead of silently
    agreeing with a stale shape.
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


class _Transport:
    def __init__(self, returns):
        self._returns = list(returns)
        self.calls = []

    async def async_run(self, **kwargs):
        self.calls.append(kwargs)
        return self._returns.pop(0)


def _node(transport):
    node = RESTClientNode()
    node._async_http_node = transport  # type: ignore[attr-defined]
    return node


def page(items, next_link=None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": list(items)}
    if next_link is not None:
        body["links"] = {"next": next_link, "self": FULL_URL}
    return body


async def test_merged_hateoas_result_drops_page_one_navigation_pointers():
    """The defect: page 1's ``next`` survives a 2-page merge."""
    transport = _Transport(
        [
            transport_return(
                page([1, 2], next_link=f"{FULL_URL}?page=2"),
                headers={
                    "Link": f'<{FULL_URL}?page=2>; rel="next"',
                    "Content-Type": "application/json",
                },
            ),
            transport_return(page([3, 4])),
        ]
    )
    node = _node(transport)

    result = await node.async_run(base_url=BASE, resource=RESOURCE, paginate=True)

    # Two pages were fetched, so page 1's pointers no longer describe the
    # result. (What `data` itself should contain when the HATEOAS path walks
    # DICT-shaped pages is a separate open defect -- see the module docstring;
    # this test deliberately asserts only the metadata contract it governs.)
    assert len(transport.calls) == 2, "the next link must actually be followed"
    meta = result["metadata"]
    assert meta["total_pages_fetched"] == 2
    # Finding C-F4: only the NAVIGATION relations go. ``self`` describes the
    # collection, not the merged window, so it outlives the merge.
    assert "next" not in meta.get("links", {}), (
        "metadata still advertises page 1's next link after the merge: "
        f"{meta.get('links')!r}"
    )
    assert (
        meta["links"]["self"] == FULL_URL
    ), f"the collection-scoped 'self' relation was dropped: {meta.get('links')!r}"
    # Built from the Link header alone here, so dropping `next` empties the
    # block -- and an empty block is removed rather than presented as ``{}``.
    assert (
        "pagination" not in meta
    ), f"stale pagination block: {meta.get('pagination')!r}"
    assert not any(
        name.lower() == "link" for name in meta["headers"]
    ), f"stale Link header survived: {meta['headers']!r}"


async def test_single_page_hateoas_result_keeps_its_pointers():
    """No-false-positive pole: one page means the pointers are still TRUE."""
    transport = _Transport(
        [
            transport_return(
                page([1, 2]),
                headers={
                    "Link": f'<{FULL_URL}?page=2>; rel="next"',
                    "Content-Type": "application/json",
                },
            )
        ]
    )
    node = _node(transport)

    result = await node.async_run(base_url=BASE, resource=RESOURCE, paginate=True)

    meta = result["metadata"]
    assert meta["total_pages_fetched"] == 1
    assert any(
        name.lower() == "link" for name in meta["headers"]
    ), "a single-page result's Link header still describes data exactly"


async def test_non_paginated_call_is_untouched():
    """``paginate`` defaults False; that result must be byte-identical."""
    transport = _Transport(
        [transport_return(page([1], next_link=f"{FULL_URL}?page=2"))]
    )
    node = _node(transport)

    result = await node.async_run(base_url=BASE, resource=RESOURCE)

    meta = result["metadata"]
    assert meta["links"]["next"] == f"{FULL_URL}?page=2"
    assert (
        "total_pages_fetched" not in meta
    ), "a non-paginated result must not claim a page count"
