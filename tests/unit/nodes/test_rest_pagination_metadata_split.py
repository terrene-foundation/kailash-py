"""Navigation-vs-descriptive split in ``_drop_stale_pagination_metadata``.

Finding C-F4. The predecessor popped the WHOLE ``pagination`` block and the
WHOLE ``links`` block once ``pages_merged > 1``. Those blocks mix two
different kinds of thing:

* NAVIGATION pointers (``next``/``prev``/``has_next`` ...) — the merge
  genuinely made these false, because the pages they point at are ALREADY
  inside ``data``.
* DESCRIPTIVE facts about the collection (``total``/``total_pages``/``page``/
  ``per_page``/``count``) — the merge did NOT make these false. They describe
  the server-side collection, not the window that was merged.

Popping both together contradicted the helper's own stated rationale
("blanking them would discard true information") and, measured, left a caller
with ``max_pages=2`` against a 50-page resource holding ONLY
``total_pages_fetched: 2`` — no record count, and no signal at all that the
result was truncated.

Discrimination
--------------
Both poles are asserted, so the suite can return the other answer:

* ``*_survive_*`` fails on the pre-fix pop-everything implementation.
* ``*_are_still_dropped_*`` fails on a "revert the strip entirely" fix.
* ``test_single_page_merge_strips_nothing`` fails on any unconditional strip.

The helper is exercised DIRECTLY (it is a staticmethod and pure) and also
end-to-end through ``RESTClientNode.run``, so the key names the REAL producer
``_extract_pagination_metadata`` emits are covered, not only invented ones.
Every transport double is built from the REAL declared return type — an actual
``HTTPResponse(...).model_dump()`` nested under ``"response"``.
"""

from pathlib import Path

from kailash.nodes.api import rest as rest_module
from kailash.nodes.api.http import HTTPResponse
from kailash.nodes.api.rest import RESTClientNode

_WORKTREE_ROOT = Path(__file__).resolve().parents[3]

_BASE_URL = "https://api.example.test"
_PAGE_URL = f"{_BASE_URL}/items"
_NEXT_URL = f"{_PAGE_URL}?page=2"
_NEXT_LINK = f'<{_NEXT_URL}>; rel="next"'

_drop = RESTClientNode._drop_stale_pagination_metadata


def test_module_under_test_is_this_checkout():
    """Guard: pytest in a worktree can silently import a different checkout."""
    assert Path(rest_module.__file__).resolve().is_relative_to(_WORKTREE_ROOT), (
        f"rest.py imported from {rest_module.__file__}, "
        f"which is outside the checkout under test ({_WORKTREE_ROOT})"
    )


# --------------------------------------------------------------------------
# POLE A — descriptive facts SURVIVE the merge. (Red on pop-everything.)
# --------------------------------------------------------------------------


def test_descriptive_pagination_facts_survive_a_multi_page_merge():
    metadata = {
        "pagination": {
            "total": 99,
            "total_pages": 50,
            "page": 1,
            "per_page": 2,
            "count": 2,
            "next": _NEXT_URL,
            "has_next": True,
        }
    }

    result = _drop(metadata, 3)

    assert "pagination" in result, (
        "the whole pagination block was dropped, taking true descriptive facts "
        f"with it; caller is left with only {sorted(result)}"
    )
    assert result["pagination"]["total"] == 99
    assert result["pagination"]["total_pages"] == 50
    assert result["pagination"]["page"] == 1
    assert result["pagination"]["per_page"] == 2
    assert result["pagination"]["count"] == 2


def test_truncation_signal_is_derivable_from_the_surviving_metadata():
    """The reason the split is drawn where it is.

    ``total_pages`` (what exists) beside ``total_pages_fetched`` (what the
    caller got) is what tells a consumer the result is truncated. Dropping the
    former removed the only truncation signal the result carried.
    """
    metadata = {"pagination": {"total_pages": 50, "total": 99, "next": _NEXT_URL}}

    result = _drop(metadata, 2)

    assert result["total_pages_fetched"] == 2
    assert result["pagination"]["total_pages"] == 50, (
        "no truncation signal survives: the caller cannot tell a complete "
        f"2-page result from a 2-of-50 truncation. Got {result!r}"
    )
    assert result["pagination"]["total_pages"] > result["total_pages_fetched"]


def test_links_block_keeps_collection_scoped_relations():
    metadata = {
        "links": {
            "self": _PAGE_URL,
            "first": _PAGE_URL,
            "last": f"{_PAGE_URL}?page=50",
            "next": _NEXT_URL,
            "prev": _PAGE_URL,
        }
    }

    result = _drop(metadata, 3)

    assert "links" in result, (
        "the whole links block was dropped; self/first/last describe the "
        f"collection and outlive the merge. Got {sorted(result)}"
    )
    assert result["links"]["self"] == _PAGE_URL
    assert result["links"]["first"] == _PAGE_URL
    assert result["links"]["last"] == f"{_PAGE_URL}?page=50"


# --------------------------------------------------------------------------
# POLE B — navigation pointers are STILL gone. (Red on "revert the strip".)
# --------------------------------------------------------------------------


def test_navigation_pointers_are_still_dropped_from_the_pagination_block():
    metadata = {
        "pagination": {
            "total": 99,
            "next": _NEXT_URL,
            "next_url": _NEXT_URL,
            "prev": _PAGE_URL,
            "previous": _PAGE_URL,
            "prev_url": _PAGE_URL,
            "has_next": True,
            "has_prev": False,
            "has_previous": False,
        }
    }

    result = _drop(metadata, 3)

    survivors = sorted(result["pagination"])
    assert survivors == ["total"], (
        "navigation pointers survived a multi-page merge and now advertise "
        f"pages already inside data: {result['pagination']!r}"
    )


def test_navigation_pointers_are_still_dropped_from_the_links_block():
    metadata = {
        "links": {
            "self": _PAGE_URL,
            "next": _NEXT_URL,
            "prev": _PAGE_URL,
            "previous": _PAGE_URL,
        }
    }

    result = _drop(metadata, 3)

    assert sorted(result["links"]) == ["self"], (
        "a stale navigation link survived the merge: " f"{result['links']!r}"
    )


def test_navigation_keys_are_matched_case_insensitively():
    metadata = {
        "pagination": {"Next": _NEXT_URL, "HAS_NEXT": True, "Total": 99},
        "links": {"Next": _NEXT_URL, "Self": _PAGE_URL},
    }

    result = _drop(metadata, 2)

    assert sorted(result["pagination"]) == [
        "Total"
    ], f"case-variant navigation keys survived: {result['pagination']!r}"
    assert sorted(result["links"]) == [
        "Self"
    ], f"case-variant navigation link survived: {result['links']!r}"


def test_a_block_emptied_by_the_drop_is_removed_rather_than_presented_empty():
    metadata = {
        "pagination": {"next": _NEXT_URL, "has_next": True},
        "links": {"next": _NEXT_URL, "prev": _PAGE_URL},
    }

    result = _drop(metadata, 4)

    assert "pagination" not in result, (
        "an empty pagination block is presented as if it were data: "
        f"{result.get('pagination')!r}"
    )
    assert (
        "links" not in result
    ), f"an empty links block is presented as if it were data: {result.get('links')!r}"


def test_stale_link_header_is_still_stripped():
    metadata = {
        "headers": {"Link": _NEXT_LINK, "link": _NEXT_LINK, "X-Total-Count": "99"},
        "pagination": {"total": 99},
    }

    result = _drop(metadata, 2)

    assert not any(
        name.lower() == "link" for name in result["headers"]
    ), f"stale Link header survived: {result['headers']!r}"
    assert result["headers"]["X-Total-Count"] == "99"


# --------------------------------------------------------------------------
# NO-FALSE-POSITIVE POLE — a single page has nothing stale to drop.
# --------------------------------------------------------------------------


def test_single_page_merge_strips_nothing():
    metadata = {
        "headers": {"Link": _NEXT_LINK},
        "pagination": {"total": 99, "next": _NEXT_URL, "has_next": True},
        "links": {"next": _NEXT_URL, "self": _PAGE_URL},
    }

    result = _drop(metadata, 1)

    assert result["total_pages_fetched"] == 1
    assert result["headers"]["Link"] == _NEXT_LINK
    assert result["pagination"]["next"] == _NEXT_URL
    assert result["pagination"]["has_next"] is True
    assert result["links"]["next"] == _NEXT_URL


# --------------------------------------------------------------------------
# END-TO-END — the key names the REAL producer emits, through run().
# --------------------------------------------------------------------------


def _payload(items, *, headers=None, links=None, meta=None):
    content = {"data": list(items), "meta": dict(meta or {})}
    if links is not None:
        content["links"] = dict(links)
    return {
        "response": HTTPResponse(
            status_code=200,
            headers=dict(headers or {}),
            content_type="application/json",
            content=content,
            response_time_ms=1.5,
            url=_PAGE_URL,
        ).model_dump(),
        "status_code": 200,
        "success": True,
    }


class _SyncTransport:
    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        if not self._pages:
            return _payload([], meta={"total": 99})
        return self._pages.pop(0)


_MERGED_META = {
    "total": 99,
    "total_pages": 50,
    "page": 1,
    "per_page": 2,
    "has_next": True,
    "has_prev": False,
}


def test_end_to_end_truncated_run_keeps_the_record_count_and_page_total():
    """The measured regression: max_pages=3 against a 50-page resource."""
    node = RESTClientNode(base_url=_BASE_URL, resource="items")
    transport = _SyncTransport(
        [
            _payload(
                [{"id": 1}, {"id": 2}],
                headers={"Link": _NEXT_LINK},
                links={"next": _NEXT_URL, "self": _PAGE_URL, "last": _PAGE_URL},
                meta=_MERGED_META,
            ),
            _payload([{"id": 3}, {"id": 4}], meta={"total": 99}),
            _payload([{"id": 5}, {"id": 6}], meta={"total": 99}),
        ]
    )
    node.http_node = transport

    result = node.run(
        base_url=_BASE_URL,
        resource="items",
        method="GET",
        query_params={"per_page": 2},
        paginate=True,
        pagination_params={
            "type": "page",
            "page_param": "page",
            "limit_param": "per_page",
            "items_path": "data",
            "total_path": "meta.total",
            "max_pages": 3,
        },
    )
    metadata = result["metadata"]

    assert transport.calls == 3, "page 1 plus two follow-ups"
    assert len(result["data"]) == 6
    assert metadata["total_pages_fetched"] == 3

    # Descriptive facts the merge did not falsify.
    assert "pagination" in metadata, (
        "a truncated 3-of-50 result carries no record count and no truncation "
        f"signal at all; metadata keys are {sorted(metadata)}"
    )
    assert metadata["pagination"]["total"] == 99
    assert metadata["pagination"]["total_pages"] == 50
    assert metadata["pagination"]["per_page"] == 2
    assert metadata["links"]["self"] == _PAGE_URL

    # Navigation pointers the merge DID falsify.
    for stale in ("next", "prev", "has_next", "has_prev"):
        assert stale not in metadata["pagination"], (
            f"stale navigation key {stale!r} survived the merge: "
            f"{metadata['pagination']!r}"
        )
    assert "next" not in metadata["links"], f"stale next link: {metadata['links']!r}"
    assert not any(name.lower() == "link" for name in metadata["headers"])
