"""Regression: a cached tool result MUST NOT cross principals.

ROUND-3 traded one defect for another
-------------------------------------
``71eb63790`` stopped writing transport credentials into cache keys by keying on
``clean_kwargs``. That half is correct. Its JUSTIFICATION is not::

    # Safe by construction: authorization is decided ABOVE this
    # block, and the tool body is called with clean_kwargs — so
    # the stripped set is exactly the set the result can depend on.

The tool body has a per-caller channel that does NOT travel through kwargs:

* ``server.py`` defines module-level ``_CURRENT_TOOL_CLIENT: ContextVar``.
* ``_handle_call_tool`` binds it to the invoking ``client_id`` for the tool
  body's duration (``token = _CURRENT_TOOL_CLIENT.set(client_id)``).
* ``_execute_tool`` dispatches to ``tool_info["handler"]`` — the enhanced,
  CACHED wrapper — so the cached path runs inside that binding.
* ``ElicitationSystem`` is constructed with
  ``client_id_provider=lambda: _CURRENT_TOOL_CLIENT.get()``, and the file's own
  comment calls the resulting scoping a security property: an elicitation is
  "dispatched to — and resolvable ONLY by — the invoking client (FINDING 3 —
  elicitation client-scoping)".

So a tool body CAN read the invoking client, and its result CAN depend on it —
which makes the "stripped set is exactly the set the result can depend on"
claim false, and makes a cache keyed only on arguments a cross-principal
result-sharing channel:

    Client A calls ask(question=X) -> elicitation dispatched to A -> A answers
    R_A -> R_A cached under the argument-only key.
    Client B calls ask(question=X) -> CACHE HIT -> R_A returned to B, and no
    elicitation is ever raised.

B receives A's elicited input, and the client-scoping that FINDING 3 exists to
establish is bypassed by the cache layer sitting ABOVE it.

WHY THE INSTRUMENT USES THE REAL ContextVar
-------------------------------------------
The tests below bind ``_CURRENT_TOOL_CLIENT`` exactly as ``_handle_call_tool``
does, rather than duck-typing a per-caller channel. That ContextVar IS the
channel; a stand-in would prove something about the stand-in.

Every test carries a CONTROL asserting the channel is genuinely live (the tool
really did observe a per-client value), so a server that simply stopped caching,
or a tool body that never read the client at all, cannot make this suite pass.
"""

import asyncio

import pytest
from kailash_mcp.server import _CURRENT_TOOL_CLIENT, MCPServer

CACHE_NAME = "answers"
QUESTION = "approve-the-q3-release?"


async def _maybe_await(value):
    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await value
    return value


def _eliciting_server():
    """A server whose cached tools' results depend on the INVOKING CLIENT.

    The body reads the same ContextVar the elicitation system reads through
    ``client_id_provider``, so ``f"answer-from-{client}"`` stands in for "the
    answer THIS client gave to the elicitation" without needing a live
    client transport.
    """
    server = MCPServer("cross-principal", enable_cache=True, enable_metrics=False)

    @server.tool(cache_key=CACHE_NAME, cache_ttl=60)
    def ask_sync(question: str) -> str:
        """Ask the invoking client and return their answer."""
        return f"answer-from-{_CURRENT_TOOL_CLIENT.get()}"

    @server.tool(cache_key=CACHE_NAME, cache_ttl=60)
    async def ask_async(question: str) -> str:
        """Ask the invoking client and return their answer."""
        return f"answer-from-{_CURRENT_TOOL_CLIENT.get()}"

    return server


async def _call_as(server, client_id, tool_name, arguments):
    """Invoke a tool with the invoking client bound as _handle_call_tool binds it."""
    token = _CURRENT_TOOL_CLIENT.set(client_id)
    try:
        return await _maybe_await(server._execute_tool(tool_name, dict(arguments)))
    finally:
        _CURRENT_TOOL_CLIENT.reset(token)


def _recording_cache(server, cache_name=CACHE_NAME):
    """Record every key string handed to the cache BACKEND.

    ``CacheManager.get_cache`` memoises by name, so pre-creating the cache here
    guarantees the wrapper's own ``get_cache`` call returns THIS instance.
    """
    keys: list = []
    cache = server.cache.get_cache(cache_name)

    def record(original):
        def wrapper(key, *args, **kwargs):
            keys.append(key)
            return original(key, *args, **kwargs)

        return wrapper

    for method in ("get", "set", "aget", "aset", "get_or_compute"):
        setattr(cache, method, record(getattr(cache, method)))

    return keys


TOOLS = [
    pytest.param("ask_sync", id="sync_wrapper"),
    pytest.param("ask_async", id="async_wrapper"),
]


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", TOOLS)
async def test_one_clients_answer_is_never_served_to_another_client(tool_name):
    """The cache MUST NOT return client A's elicited answer to client B."""
    server = _eliciting_server()

    first = await _call_as(server, "client-A", tool_name, {"question": QUESTION})

    # CONTROL: the per-caller channel is genuinely live. If the tool body never
    # observed the invoking client this would be "answer-from-None", and the
    # assertion below would pass for a reason that has nothing to do with the
    # cache.
    assert first == "answer-from-client-A", (
        "the tool body did not observe the invoking client, so this test is not "
        f"exercising the per-caller channel at all: {first!r}"
    )

    second = await _call_as(server, "client-B", tool_name, {"question": QUESTION})

    assert second == "answer-from-client-B", (
        "client B received client A's result from the cache "
        f"({second!r}): the cache key does not carry the principal, so a cached "
        "elicited answer crosses principals and the FINDING 3 elicitation "
        "client-scoping is bypassed by the cache layer above it."
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", TOOLS)
async def test_the_same_client_still_hits_cache(tool_name):
    """CONTROL/correctness: per-principal keying must not disable caching.

    A fix that keyed on something per-CALL (a uuid, a timestamp, the session id)
    would pass the isolation test above while making the cache useless. Here the
    SAME client repeats the SAME call and must reach ONE key.
    """
    server = _eliciting_server()
    keys = _recording_cache(server)

    await _call_as(server, "client-A", tool_name, {"question": QUESTION})
    first = set(keys)
    keys.clear()

    await _call_as(server, "client-A", tool_name, {"question": QUESTION})

    assert first, (
        "the cache backend was never reached, so this test observed nothing "
        "about the key; the instrument, not the code, is at fault"
    )
    assert first == set(keys), (
        "the same client repeating the same call produced DIFFERENT cache keys, "
        f"so the cache never hits for anyone: {first!r} vs {set(keys)!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", TOOLS)
async def test_distinct_clients_get_distinct_cache_keys(tool_name):
    """The key itself must partition by principal, not merely by result."""
    server = _eliciting_server()
    keys = _recording_cache(server)

    await _call_as(server, "client-A", tool_name, {"question": QUESTION})
    first = set(keys)
    keys.clear()

    await _call_as(server, "client-B", tool_name, {"question": QUESTION})
    second = set(keys)

    assert first and second, (
        "the cache backend was never reached, so this test observed nothing "
        "about the key; the instrument, not the code, is at fault"
    )
    assert not (first & second), (
        "two DIFFERENT clients issuing the same call landed on a shared cache "
        f"key: {first!r} vs {second!r}. The first caller's result is served to "
        "the second."
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sharing_across_callers_is_available_but_never_the_default():
    """``cache_shared_across_callers`` must actually do something, opt-IN only.

    A documented kwarg with no effect on the body is its own defect, so the
    flag is exercised rather than merely declared. The default is asserted in
    the SAME test, so a change that flipped the default to sharing (restoring
    the leak) cannot pass by satisfying only the opt-in half.
    """
    server = MCPServer("opt-in-sharing", enable_cache=True, enable_metrics=False)

    @server.tool(cache_key="shared", cache_ttl=60, cache_shared_across_callers=True)
    def public_rate(pair: str) -> str:
        """A result that genuinely does not depend on who asked."""
        return f"rate:{pair}"

    @server.tool(cache_key="shared", cache_ttl=60)
    def default_scoped(pair: str) -> str:
        """Same shape, default (per-principal) keying."""
        return f"rate:{pair}"

    keys = _recording_cache(server, "shared")

    await _call_as(server, "client-A", "public_rate", {"pair": "EURUSD"})
    shared_a = set(keys)
    keys.clear()
    await _call_as(server, "client-B", "public_rate", {"pair": "EURUSD"})
    shared_b = set(keys)
    keys.clear()

    assert shared_a and shared_b, (
        "the cache backend was never reached, so this test observed nothing "
        "about the key; the instrument, not the code, is at fault"
    )
    assert shared_a == shared_b, (
        "cache_shared_across_callers=True had no effect: two clients still "
        f"landed on different keys ({shared_a!r} vs {shared_b!r}), so the "
        "documented kwarg is inert."
    )

    await _call_as(server, "client-A", "default_scoped", {"pair": "EURUSD"})
    default_a = set(keys)
    keys.clear()
    await _call_as(server, "client-B", "default_scoped", {"pair": "EURUSD"})
    default_b = set(keys)

    assert default_a and default_b, "the cache backend was never reached"
    assert not (default_a & default_b), (
        "the DEFAULT shared one cache entry across two clients "
        f"({default_a!r} vs {default_b!r}): sharing must be opt-IN, never the "
        "default, or every tool silently reopens the cross-principal leak."
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", TOOLS)
async def test_distinct_arguments_still_partition_within_one_client(tool_name):
    """CONTROL: the key must still discriminate on the BUSINESS argument.

    A fix that keyed ONLY on the principal would pass every assertion above
    while collapsing all of one client's distinct requests onto one entry —
    serving the wrong answer to the same caller.
    """
    server = _eliciting_server()
    keys = _recording_cache(server)

    await _call_as(server, "client-A", tool_name, {"question": QUESTION})
    first = set(keys)
    keys.clear()

    await _call_as(server, "client-A", tool_name, {"question": "a-different-question"})
    second = set(keys)

    assert first and second, (
        "the cache backend was never reached, so this test observed nothing "
        "about the key; the instrument, not the code, is at fault"
    )
    assert not (first & second), (
        "two DIFFERENT questions from the same client landed on a shared cache "
        f"key: {first!r} vs {second!r}. The cache no longer distinguishes "
        "requests and returns the wrong answer."
    )
