"""Regression: the ``@server.tool(rate_limit=...)`` argument was never wired.

Surfaced while enumerating the raw-``kwargs`` consumers in the tool wrappers.
Both wrappers carried::

    self.auth_manager.rate_limiter.check_rate_limit(
        user_id,        # a STRING
        tool_name,      # a second positional
        **rate_limit,   # plus arbitrary keywords
    )

against ``RateLimiter.check_rate_limit(self, user_info: Dict[str, Any])`` — one
parameter, expecting a user-info DICT. So every call to a tool declaring the
documented ``rate_limit={"requests_per_minute": 10}`` raised::

    ToolError: Tool execution failed:
        RateLimiter.check_rate_limit() got an unexpected keyword argument 'limit'

The feature was not merely inert (``zero-tolerance.md`` Rule 3c, a documented
kwarg with no effect) — it made the tool it was applied to permanently
unusable, and the failure was reported as a generic execution error.

Three defects in one statement:

1. ``check_rate_limit`` never accepted a tool name or a per-tool limit, so
   per-tool rate limiting had no implementation at all.
2. The user identity was read as ``.get("user", {}).get("id")`` while
   ``AuthProvider`` results carry ``user_id`` — so even the argument that WAS
   of the right kind was always ``"anonymous"``.
3. The surrounding ``except RateLimitError`` named ``errors.RateLimitError``,
   which this path can never raise (``RateLimiter`` raises the ``providers``
   one), so the handler was dead — the same wrong-hierarchy defect as the
   authentication path's rate-limit clause.

The tools below are deliberately UNGATED (no ``required_permission``) so that
``AuthManager._authorize``'s own global rate-limit check does not consume the
budget under test; that isolates the per-tool bucket.
"""

import asyncio
import inspect

import pytest

from kailash_mcp.auth.providers import APIKeyAuth, RateLimiter
from kailash_mcp.errors import MCPErrorCode, RateLimitError
from kailash_mcp.server import _RATE_LIMIT_KEYS, MCPServer

API_KEY = "some-key"


async def _maybe_await(value):
    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await value
    return value


def _rate_limited_tools_server():
    """Global limit deliberately LOOSE (60/min); per-tool limit TIGHT (6/min).

    ``retry_after`` is ``int(60 / limit)``, so the per-tool limit yields 10s and
    the global default would yield 1s — the assertion on 10 therefore proves the
    PER-TOOL configuration was honoured, not merely that some limiter fired.
    """
    server = MCPServer(
        "per-tool-rate-limit",
        enable_cache=False,
        enable_metrics=False,
        auth_provider=APIKeyAuth(keys={API_KEY: {"permissions": ["p"]}}),
        rate_limit_config={"default_limit": 60, "burst_limit": 2},
    )

    @server.tool(rate_limit={"requests_per_minute": 6})
    def limited_sync(x: str) -> str:
        """A tool with a per-tool rate limit."""
        return f"ran:{x}"

    @server.tool(rate_limit={"requests_per_minute": 6})
    async def limited_async(x: str) -> str:
        """A tool with a per-tool rate limit."""
        return f"ran:{x}"

    @server.tool(rate_limit={"requests_per_minute": 6})
    def other_limited(x: str) -> str:
        """A second rate-limited tool, for bucket isolation."""
        return f"other:{x}"

    return server


TOOLS = [
    pytest.param("limited_sync", id="sync_wrapper"),
    pytest.param("limited_async", id="async_wrapper"),
]


@pytest.mark.regression
def test_accepted_rate_limit_keys_are_real_check_rate_limit_parameters():
    """Structural invariant: the accepted-key set IS the callee's signature.

    ``rate_limit`` entries are forwarded as keyword arguments to
    ``RateLimiter.check_rate_limit``. That made the two a single contract with
    nothing enforcing it — which is exactly how the original defect shipped, a
    call site passing keywords the callee never declared. Any future key added
    to one side without the other fails here instead of at the caller.
    """
    parameters = inspect.signature(RateLimiter.check_rate_limit).parameters

    keyword_kinds = (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )
    acceptable = {
        name
        for name, parameter in parameters.items()
        if parameter.kind in keyword_kinds and name != "self"
    }

    # CONTROL: the signature was actually introspected.
    assert acceptable, "no keyword parameters found on check_rate_limit"

    missing = sorted(_RATE_LIMIT_KEYS - acceptable)
    assert not missing, (
        f"rate_limit key(s) {missing} are accepted by the tool decorator but "
        "are not parameters of RateLimiter.check_rate_limit; every call to a "
        "tool using them would raise TypeError"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", TOOLS)
async def test_rate_limited_tool_is_callable_at_all(tool_name):
    """The baseline the defect broke: a rate-limited tool RUNS within budget."""
    server = _rate_limited_tools_server()

    result = await _maybe_await(server._execute_tool(tool_name, {"x": "1"}))

    assert result == "ran:1", (
        "declaring the documented rate_limit= argument made the tool unusable: "
        f"{result!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", TOOLS)
async def test_per_tool_budget_throttles_with_the_per_tool_retry_after(tool_name):
    """Exceeding the per-tool budget raises RATE_LIMITED with retry_after=10."""
    server = _rate_limited_tools_server()

    # burst_limit=2 -> two calls are inside the budget.
    for attempt in range(2):
        assert (
            await _maybe_await(server._execute_tool(tool_name, {"x": str(attempt)}))
        ) == f"ran:{attempt}", f"call {attempt} was refused while inside the budget"

    with pytest.raises(Exception) as excinfo:
        await _maybe_await(server._execute_tool(tool_name, {"x": "over"}))

    error = excinfo.value
    assert isinstance(error, RateLimitError), (
        "exceeding a per-tool rate limit did not surface as a RateLimitError: "
        f"{type(error).__name__}: {error!r}"
    )
    assert error.error_code == MCPErrorCode.RATE_LIMITED
    assert error.retry_after == 10, (
        "retry_after does not reflect the per-tool requests_per_minute (6 -> "
        f"10s); the per-tool configuration was not applied: {error.retry_after!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_per_tool_budgets_are_independent_across_tools():
    """CONTROL: exhausting one tool's budget does not throttle another.

    Without this, an implementation that shared one bucket across every tool
    would still pass the throttling test above.
    """
    server = _rate_limited_tools_server()

    for attempt in range(2):
        await _maybe_await(server._execute_tool("limited_sync", {"x": str(attempt)}))
    with pytest.raises(RateLimitError):
        await _maybe_await(server._execute_tool("limited_sync", {"x": "over"}))

    result = await _maybe_await(server._execute_tool("other_limited", {"x": "1"}))
    assert result == "other:1", (
        "exhausting one tool's per-tool budget also throttled a DIFFERENT tool, "
        f"so the buckets are shared: {result!r}"
    )


@pytest.mark.regression
def test_unknown_rate_limit_key_is_rejected_at_registration():
    """A mis-keyed rate_limit config fails at DECORATION, not on every call.

    The defect's signature was a per-call TypeError surfacing as a generic
    "Tool execution failed"; an unrecognised key must be a loud registration
    error instead.
    """
    server = MCPServer("bad-rate-limit", enable_cache=False, enable_metrics=False)

    with pytest.raises(ValueError) as excinfo:

        @server.tool(rate_limit={"limit": 10})
        def mis_keyed(x: str) -> str:
            """Tool with a mis-keyed rate limit."""
            return x

    message = str(excinfo.value)
    assert "limit" in message and "requests_per_minute" in message, (
        "the registration error does not name the offending key and the "
        f"accepted one: {message!r}"
    )


@pytest.mark.regression
def test_valid_rate_limit_key_registers_cleanly():
    """CONTROL: the documented key is accepted.

    Without this, a fix that rejected EVERY rate_limit config would pass the
    test above.
    """
    server = MCPServer("good-rate-limit", enable_cache=False, enable_metrics=False)

    @server.tool(rate_limit={"requests_per_minute": 10})
    def well_keyed(x: str) -> str:
        """Tool with the documented rate limit config."""
        return x

    assert "well_keyed" in server._tool_registry
