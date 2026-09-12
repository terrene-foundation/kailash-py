"""Regression: RESTClientNode.async_run never populated the pagination metadata.

`_handle_async_pagination` looks for the next page at
``metadata["links"]["next"]`` or ``metadata["pagination"]["next_url"]``. Those
keys are produced by ``_extract_metadata``, which the SYNC path calls when it
assembles its result but which ``async_run`` did not — it hand-built
``metadata`` as ``{url, method, headers}`` only.

So ``next_url`` was unconditionally ``None``, the loop broke on its first
iteration, and ``paginate=True`` on the async path returned page 1 as success
with a transport standing by to serve more: truncated data presented as
complete. Same failure class as the ``url=None`` defect on the sync path, on a
different path, and with no test coverage anywhere in the repo.

Both poles are pinned deliberately. A test asserting only that follow-up pages
are fetched would also pass if the node fetched pages unconditionally, so the
no-more-links case is asserted too.
"""

from __future__ import annotations

import pytest

from kailash.nodes.api.rest import RESTClientNode


class _RecordingHTTP:
    """Deterministic transport that advertises a next link for `link_pages` pages.

    Not a mock: it satisfies the async_run contract with fixed output, so it is a
    protocol-satisfying deterministic adapter per rules/testing.md Tier-1.
    """

    def __init__(self, link_pages: int = 1) -> None:
        self.calls: list[str | None] = []
        self._link_pages = link_pages

    async def async_run(self, **kwargs) -> dict:
        self.calls.append(kwargs.get("url"))
        n = len(self.calls)
        content: dict = {"items": [n]}
        content["links"] = (
            {"next": f"https://api.example.com/x?page={n + 1}"}
            if n <= self._link_pages
            else {}
        )
        return {
            "content": content,
            "status_code": 200,
            "success": True,
            "headers": {},
            "response_time_ms": 1,
        }


def _node(transport: _RecordingHTTP) -> RESTClientNode:
    node = RESTClientNode()
    # The adapter deliberately substitutes for AsyncHTTPRequestNode, so the
    # assignment is not type-compatible. Per rules/testing.md § duck-typed
    # collaborator, a double written to match the CALL SITE is unfalsifiable —
    # so the contract is pinned against the REAL declared type below rather
    # than assumed.
    node._async_http_node = transport  # type: ignore[assignment]
    return node


def test_recording_adapter_matches_the_real_transport_contract() -> None:
    """Pin the double against the REAL declared type, not the call site.

    If AsyncHTTPRequestNode.async_run stops accepting the keywords async_run
    passes it, this reds here instead of letting every test above keep passing
    against a double that agrees with the caller's stale belief.
    """
    import inspect

    from kailash.nodes.api.http import AsyncHTTPRequestNode

    real = inspect.signature(AsyncHTTPRequestNode.async_run)
    double = inspect.signature(_RecordingHTTP.async_run)

    # Both must accept the keyword set async_run actually sends.
    sent = {"url", "method", "headers", "params", "response_format", "timeout"}
    accepts_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in real.parameters.values()
    )
    assert accepts_kwargs or sent <= set(real.parameters), (
        f"AsyncHTTPRequestNode.async_run no longer accepts {sorted(sent)}; "
        f"it takes {sorted(real.parameters)} — the double and the caller are "
        "now both wrong together"
    )
    assert any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in double.parameters.values()
    ), "the double must accept the same keyword set the real transport does"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_async_pagination_discovers_the_next_link() -> None:
    """The defect pole: metadata carries links, so the follow-up page is fetched."""
    transport = _RecordingHTTP(link_pages=1)
    result = await _node(transport).async_run(
        base_url="https://api.example.com",
        resource="x",
        method="GET",
        paginate=True,
        pagination_params={"max_pages": 5},
    )

    metadata = result["metadata"]
    # Without _extract_metadata wired in, this key is absent and next_url is None.
    assert "links" in metadata, (
        "async_run must populate pagination metadata via _extract_metadata; "
        f"got keys {sorted(metadata)}"
    )
    assert (
        len(transport.calls) == 2
    ), f"expected a follow-up request, got {transport.calls}"
    assert transport.calls[1] == "https://api.example.com/x?page=2"
    assert metadata.get("total_pages_fetched") == 2


@pytest.mark.regression
@pytest.mark.asyncio
async def test_async_pagination_stops_when_no_next_link() -> None:
    """The no-false-positive pole: absent a next link, exactly one request."""
    transport = _RecordingHTTP(link_pages=0)
    result = await _node(transport).async_run(
        base_url="https://api.example.com",
        resource="x",
        method="GET",
        paginate=True,
        pagination_params={"max_pages": 5},
    )

    assert (
        len(transport.calls) == 1
    ), f"no next link was advertised, so no follow-up is legal; got {transport.calls}"
    assert result["metadata"].get("total_pages_fetched") == 1


@pytest.mark.regression
@pytest.mark.asyncio
async def test_async_pagination_respects_max_pages() -> None:
    """An always-advertising server is bounded by max_pages, not unbounded."""
    transport = _RecordingHTTP(link_pages=99)
    await _node(transport).async_run(
        base_url="https://api.example.com",
        resource="x",
        method="GET",
        paginate=True,
        pagination_params={"max_pages": 3},
    )

    assert (
        len(transport.calls) == 3
    ), f"max_pages=3 must cap total requests at 3; got {len(transport.calls)}"
