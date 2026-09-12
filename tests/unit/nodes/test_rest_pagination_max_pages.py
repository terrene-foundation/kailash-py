"""Regression test for issue #1406 gap #2 — REST pagination max_pages cap.

The stub inventory flagged ``rest.py`` as "max_pages silently ignored" because
of a commented-out ``# max_pages = ... # TODO`` line. Ground truth: the cap IS
read and enforced in the remaining-pages fetch loop (``while pages_fetched <
max_pages``). This test pins that behaviour so the cap cannot regress, and the
misleading comment was removed in the same change.
"""

from unittest.mock import Mock

from kailash.nodes.api.rest import RESTClientNode


def test_max_pages_caps_fetch_loop():
    """With pages that never run dry, only ``max_pages`` is the stop condition;
    the loop MUST fetch at most ``max_pages - 1`` additional pages."""
    node = RESTClientNode()

    # Every follow-up request returns a non-empty page, so the ONLY thing that
    # can stop the loop is the max_pages cap.
    node.http_node.execute = Mock(  # type: ignore[method-assign]
        return_value={"success": True, "response": {"content": {"data": [3, 4]}}}
    )

    initial_response = {"data": [1, 2]}
    query_params = {"page": "1", "per_page": "2"}
    pagination_params = {
        "type": "page",
        "items_path": "data",
        "page_param": "page",
        "limit_param": "per_page",
        # no total_path → no early total-based exit; max_pages is the gate
        "max_pages": 3,
    }

    all_items = node._handle_pagination(
        initial_response,
        query_params,
        pagination_params,
        request_url="https://api.example.com/v1/items",
        request_headers={},
        request_timeout=30,
    )

    # pages_fetched starts at 1 (the initial page), loop runs while < 3 → 2 fetches.
    assert node.http_node.execute.call_count == 2
    # initial [1, 2] + two fetched pages [3, 4] each.
    #
    # The repeated [3, 4] is the stub returning identical CONTENT for every
    # page, not a pagination defect: each request carries a distinct ?page=N,
    # so the loop-control token advances every iteration. Cursor dedup (see
    # test_rest_pagination_request_target.py) keys on the CURSOR the server
    # hands back, which is the only protocol-level "I am not advancing"
    # signal. Page-based pagination has no such signal, and content-equality
    # dedup would wrongly discard legitimately-identical pages, so this
    # assertion is deliberately UNCHANGED.
    assert all_items == [1, 2, 3, 4, 3, 4]


def test_max_pages_one_disables_followup_fetches():
    """max_pages=1 means only the initial page is kept; no follow-up fetch."""
    node = RESTClientNode()
    node.http_node.execute = Mock(  # type: ignore[method-assign]
        return_value={"success": True, "response": {"content": {"data": [9]}}}
    )

    all_items = node._handle_pagination(
        {"data": [1, 2]},
        {"page": "1", "per_page": "2"},
        {"type": "page", "items_path": "data", "max_pages": 1},
        request_url="https://api.example.com/v1/items",
        request_headers={},
        request_timeout=30,
    )

    assert node.http_node.execute.call_count == 0
    assert all_items == [1, 2]
