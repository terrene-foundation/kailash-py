"""Regression: non-numeric pagination params escaped the node as raw builtins.

`_handle_pagination` coerces the page and per-page query params with `int()`.
Both callers were deliberately narrowed to catch `NodeExecutionError` only, so
a mis-configured request surfaces instead of being silently swallowed into a
page-1 result. But `NodeValidationError` is a SIBLING of `NodeExecutionError`,
not a subclass, and a bare `int("abc")` raises neither — it raises a builtin
`ValueError` that escapes `run()` entirely, outside the documented `Raises:`
taxonomy, discarding page 1's data along with it.

Measured before the fix:
    page='abc'     -> RAW ValueError: invalid literal for int() with base 10: 'abc'
    per_page='x'   -> RAW ValueError: invalid literal for int() with base 10: 'x'

The fix wraps both coercions (and the untrusted server-supplied `total_path`
value) into `NodeValidationError` naming the offending parameter and value.
Surfacing is correct — a non-numeric page number is a caller configuration
error — but it must surface as a typed SDK error, not a raw builtin.
"""

from __future__ import annotations

import pytest

from kailash.nodes.api.rest import RESTClientNode
from kailash.sdk_exceptions import NodeValidationError


class _StubTransport:
    """Deterministic transport: always a valid two-item first page."""

    def execute(self, **kwargs) -> dict:
        return {
            "content": {"items": [1, 2], "meta": {"total": 10}},
            "status_code": 200,
            "success": True,
            "headers": {},
            "response_time_ms": 1,
        }


def _run(query_params: dict, pagination_params: dict | None = None):
    node = RESTClientNode()
    node.http_node = _StubTransport()
    params = {"type": "page", "max_pages": 3}
    params.update(pagination_params or {})
    return node.run(
        base_url="https://api.example.com",
        resource="items",
        method="GET",
        paginate=True,
        query_params=query_params,
        pagination_params=params,
    )


@pytest.mark.regression
@pytest.mark.parametrize(
    "query_params, offending",
    [
        ({"page": "abc"}, "page"),
        ({"page": "1", "per_page": "x"}, "per_page"),
    ],
)
def test_non_numeric_pagination_param_raises_typed_error(
    query_params: dict, offending: str
) -> None:
    """A builtin ValueError must not escape; it must arrive typed and named."""
    with pytest.raises(NodeValidationError) as excinfo:
        _run(query_params)

    message = str(excinfo.value)
    assert offending in message, f"error must name the offending param: {message}"
    assert (
        repr(query_params[offending]) in message
    ), f"error must quote the offending value: {message}"


@pytest.mark.regression
def test_non_numeric_server_total_raises_typed_error() -> None:
    """A server-supplied total is untrusted and must not reach the comparison.

    Driven at `_handle_pagination` directly rather than through `run()`. That is
    deliberate and is the honest boundary: `run()` extracts `data` from the
    response BEFORE calling this helper, so `initial_response` arrives as the
    items list and a `meta.total` sibling key is not reachable from there —
    measured, `initial_response` is `[]` for a `{"items": ..., "meta": ...}`
    body. The untrusted total is a property of the value this helper receives,
    so this is where it can be exercised at all.
    """
    node = RESTClientNode()
    node.http_node = _StubTransport()

    with pytest.raises(NodeValidationError) as excinfo:
        node._handle_pagination(
            {"data": [1, 2], "meta": {"total": "many"}},
            {"page": "1"},
            {"type": "page", "max_pages": 3, "total_path": "meta.total"},
            request_url="https://api.example.com/items",
            request_headers={},
            request_timeout=30,
        )
    assert "total_path" in str(excinfo.value)


@pytest.mark.regression
def test_numeric_server_total_is_accepted() -> None:
    """No-false-positive pole for the total guard: a real number must not raise."""
    node = RESTClientNode()
    node.http_node = _StubTransport()

    result = node._handle_pagination(
        {"data": [1, 2], "meta": {"total": 2}},
        {"page": "1"},
        {"type": "page", "max_pages": 3, "total_path": "meta.total"},
        request_url="https://api.example.com/items",
        request_headers={},
        request_timeout=30,
    )
    assert result == [1, 2]


@pytest.mark.regression
def test_numeric_pagination_params_still_work() -> None:
    """No-false-positive pole: valid numeric params must NOT raise.

    Without this, a fix that rejected every value would pass the tests above.
    """
    result = _run({"page": "1", "per_page": "20"}, {"total_path": "meta.total"})
    assert result["success"] is True
    assert result["data"] is not None
