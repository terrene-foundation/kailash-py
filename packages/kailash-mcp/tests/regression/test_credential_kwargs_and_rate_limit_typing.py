"""Regression: transport-level credentials MUST NOT leak into cache keys, and a
provider rate-limit denial MUST survive the tool wrapper with its own type.

Both defects live in ``MCPServer._create_enhanced_tool``'s two wrappers.

DEFECT 1 — credentials written verbatim into the cache key
----------------------------------------------------------
``_CREDENTIAL_KWARGS`` was introduced with the claim "ONE constant, read by
every call site", but the CACHE call sites read RAW ``kwargs``::

    cache_lookup_key = self.cache._create_cache_key(tool_name, args, kwargs)

and ``CacheManager._create_cache_key`` interpolates them verbatim::

    kwargs_str = str(sorted(kwargs.items())) if kwargs else ""
    return f"{func_name}:{args_str}:{kwargs_str}"

So ``api_key`` / ``password`` / ``token`` / ``jwt`` / ``authorization`` landed
in the key in PLAINTEXT. That key is then

* logged — ``utils/cache.py`` ``logger.debug("cache.get_or_compute.start
  key=%s", key)`` and the ``waiting`` line above it, and
* used as a REDIS KEY NAME — ``f"{self.redis_prefix}{self.name}:{key}"``,

so the credential shows up in ``KEYS mcp:*``, in ``MONITOR``, in the slowlog,
and in RDB/AOF on disk. Any principal with log-read or Redis-read access
(SRE, support, a log-aggregation vendor, a co-tenant on shared Redis) recovers
other users' live credentials for every cached gated tool. This is
``security.md`` § "No secrets in logs" and § Multi-Site Kwarg Plumbing.

Keying on the STRIPPED kwargs is safe: authorization is decided strictly BEFORE
the cache block on both wrappers, and the tool body never receives credentials
anyway — so the stripped set is exactly the set the result actually depends on.
It also fixes a latent correctness defect: keyed on the raw set, the key varied
per credential, so a shared-result tool never hit cache across callers.

WHY THE ASSERTIONS ARE ON THE KEY STRING
----------------------------------------
"the call returned the right answer" is consistent with both "the key omits the
credential" and "the key contains it" — only the key STRING distinguishes them.
The instrument records every key handed to the cache BACKEND (``get`` / ``set``
/ ``aget`` / ``aset`` / ``get_or_compute``), which is the string that reaches
the log line and the Redis key name. Each test carries a CONTROL asserting the
BUSINESS argument IS still in the key, so a fix that stopped keying on the
arguments altogether (which would collide every distinct call onto one entry)
cannot make this suite pass.

DEFECT 2 — ``ProviderRateLimitError`` did not survive the wrapper
------------------------------------------------------------------
Both wrappers re-raise it under a comment stating rate limiting "must keep its
own type (and retry_after) for the caller". It does not: the re-raise lands in
the enclosing ``except Exception as e:`` and ``auth.providers.RateLimitError``
subclasses ``Exception``, NOT ``MCPError`` — so ``isinstance(e, MCPError)`` is
False and it is rewrapped as ``ToolError("Tool execution failed: …")``. The
caller gets ``TOOL_EXECUTION_FAILED`` instead of ``RATE_LIMITED`` and
``retry_after`` is reachable only via ``.cause``.

The provider message is ``f"Rate limit exceeded for user {user_id}"`` and
``APIKeyAuth`` sets ``user_id = f"api_key_{fingerprint_secret(api_key)}"`` — so
the rewrap also interpolated a FINGERPRINT OF THE CALLER'S API KEY into a
caller-visible tool-error string.

The ``retry_after`` assertion below pins the PROVIDER's computed value (not the
``errors.RateLimitError`` default of 60.0), so an implementation that raised a
correctly-typed error with a defaulted ``retry_after`` — losing the provider's
value, which is the half the comment specifically claims to preserve — still
fails.
"""

import ast
import asyncio
import inspect
import textwrap

import pytest
from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.errors import MCPErrorCode, RateLimitError
from kailash_mcp.server import _CREDENTIAL_KWARGS, MCPServer

API_KEY = "live-api-key-DO-NOT-LOG"
PERMISSION = "reports.read"
CACHE_NAME = "reports"

# One distinctive sentinel per credential kwarg. Every one is a value a real
# client can put on the wire: ``_handle_call_tool`` / ``_execute_tool`` pass the
# request's ``arguments`` straight through as ``**kwargs``.
CREDENTIAL_SENTINELS = {
    "api_key": "SENTINEL-api-key-9f31",
    "token": "SENTINEL-token-4ba2",
    "username": "SENTINEL-username-77c0",
    "password": "SENTINEL-password-1d5e",
    "jwt": "SENTINEL-jwt-e0a8",
    "authorization": "Bearer SENTINEL-authz-6c14",
    "mcp_auth": {"api_key": "SENTINEL-mcp-auth-3fd9"},
}


@pytest.mark.regression
def test_only_the_credential_reader_may_touch_raw_kwargs():
    """Structural invariant: inside the wrappers, raw ``kwargs`` has ONE reader.

    ``_CREDENTIAL_KWARGS`` shipped with the claim "ONE constant, read by every
    call site" while the cache call sites still read the RAW mapping. The claim
    was prose; this test makes it mechanical.

    Every ``kwargs`` LOAD inside ``_create_enhanced_tool`` must be an argument
    to ``_extract_credentials_from_context`` (which exists precisely to CONSUME
    credentials, so it must see them) or to ``_strip_credential_kwargs`` (which
    produces the sanitised mapping). Any other read — a new cache key, a log
    line, a metrics label, an audit record — is a fresh instance of the defect
    and fails here at the moment it is written.
    """
    tree = ast.parse(
        textwrap.dedent(inspect.getsource(MCPServer._create_enhanced_tool))
    )

    sanctioned_readers = {
        "_extract_credentials_from_context",
        "_strip_credential_kwargs",
    }
    sanctioned_positions = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else getattr(node.func, "id", None)
        )
        if callee in sanctioned_readers:
            for argument in node.args:
                if isinstance(argument, ast.Name) and argument.id == "kwargs":
                    sanctioned_positions.add((argument.lineno, argument.col_offset))

    raw_loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "kwargs"
        and isinstance(node.ctx, ast.Load)
    ]

    # CONTROL: the parse actually found the reads. An empty result would make
    # the assertion below vacuously true.
    assert raw_loads, (
        "no raw `kwargs` read was found in _create_enhanced_tool at all; the "
        "AST instrument is broken, not the code"
    )
    # Exactly two sanctioned reads per wrapper: one
    # `_extract_credentials_from_context(kwargs)` and one
    # `_strip_credential_kwargs(kwargs)`. Pinned so that ADDING a sanctioned
    # read (a second strip site, a re-extraction) also has to come through
    # review rather than riding in under the allowlist.
    assert len(sanctioned_positions) == 4, (
        "expected exactly two credential-reader `kwargs` reads per wrapper "
        f"(extract + strip, sync + async), found {len(sanctioned_positions)}"
    )

    unsanctioned = [
        node
        for node in raw_loads
        if (node.lineno, node.col_offset) not in sanctioned_positions
    ]
    assert not unsanctioned, (
        "raw `kwargs` (which still carries the caller's credentials) is read "
        "outside the credential reader/stripper at "
        f"{[(n.lineno, n.col_offset) for n in unsanctioned]!r} of "
        "_create_enhanced_tool's source; use clean_kwargs"
    )


def test_sentinels_cover_every_credential_kwarg():
    """Meta-control: the sweep below must cover the WHOLE constant.

    If a name is added to ``_CREDENTIAL_KWARGS`` without a sentinel here, the
    parametrized sweep would silently stop covering it and still pass.
    """
    assert set(CREDENTIAL_SENTINELS) == set(_CREDENTIAL_KWARGS), (
        "the credential-kwarg sweep no longer covers _CREDENTIAL_KWARGS: "
        f"missing={set(_CREDENTIAL_KWARGS) - set(CREDENTIAL_SENTINELS)!r} "
        f"extra={set(CREDENTIAL_SENTINELS) - set(_CREDENTIAL_KWARGS)!r}"
    )


# ---------------------------------------------------------------------------
# Instrument: record every key string handed to the cache BACKEND.
# ---------------------------------------------------------------------------


def _recording_cache(server, cache_name=CACHE_NAME):
    """Wrap the named cache so every key reaching the backend is recorded.

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


def _cached_server():
    """A server with ONE cached sync tool and ONE cached async tool, no auth.

    Ungated so an arbitrary credential-named argument can be put on the wire
    without also having to satisfy a permission gate — the cache-key defect is
    independent of whether the tool is gated.
    """
    server = MCPServer("cache-key-cred", enable_cache=True, enable_metrics=False)

    @server.tool(cache_key=CACHE_NAME, cache_ttl=60)
    def report_sync(report_id: str) -> str:
        """Return a report."""
        return f"report:{report_id}"

    @server.tool(cache_key=CACHE_NAME, cache_ttl=60)
    async def report_async(report_id: str) -> str:
        """Return a report."""
        return f"report:{report_id}"

    return server


async def _maybe_await(value):
    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await value
    return value


def _secret_strings(value):
    """Every string that must not appear in a key, for one sentinel value."""
    if isinstance(value, dict):
        return [str(v) for v in value.values()]
    return [str(value)]


# ---------------------------------------------------------------------------
# DEFECT 1 — no credential kwarg may reach a cache key
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["report_sync", "report_async"])
@pytest.mark.parametrize("cred_name", sorted(CREDENTIAL_SENTINELS))
async def test_credential_kwarg_never_reaches_a_cache_key(tool_name, cred_name):
    """The key string handed to the cache backend carries NO credential."""
    server = _cached_server()
    keys = _recording_cache(server)

    await _maybe_await(
        server._execute_tool(
            tool_name,
            {"report_id": "q3-summary", cred_name: CREDENTIAL_SENTINELS[cred_name]},
        )
    )

    assert keys, (
        "the cache backend was never reached, so this test observed nothing "
        "about the key; the instrument, not the code, is at fault"
    )

    for secret in _secret_strings(CREDENTIAL_SENTINELS[cred_name]):
        for key in keys:
            assert secret not in key, (
                f"the {cred_name!r} credential was written verbatim into a "
                f"cache key: {key!r}. That key is logged "
                "(cache.get_or_compute.start key=%s) and used as a Redis key "
                "name, so the credential reaches KEYS/MONITOR/slowlog/RDB."
            )

    # CONTROL: the key must still discriminate on the BUSINESS argument. A fix
    # that stopped keying on arguments would pass the assertion above while
    # collapsing every distinct call onto one cache entry.
    assert any("q3-summary" in key for key in keys), (
        "no recorded cache key mentions the business argument, so the key no "
        f"longer distinguishes callers' requests: {keys!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["report_sync", "report_async"])
async def test_same_business_args_share_a_cache_key_across_credentials(tool_name):
    """CONTROL/correctness: two callers, same arguments -> ONE cache key.

    Keyed on the raw kwargs the key varied per credential, so a shared-result
    tool never hit cache across callers.
    """
    server = _cached_server()
    keys = _recording_cache(server)

    await _maybe_await(
        server._execute_tool(
            tool_name, {"report_id": "q3-summary", "api_key": "caller-one-key"}
        )
    )
    first = list(keys)
    keys.clear()

    await _maybe_await(
        server._execute_tool(
            tool_name, {"report_id": "q3-summary", "api_key": "caller-two-key"}
        )
    )

    assert set(first) == set(keys), (
        "two callers requesting the SAME report produced DIFFERENT cache keys, "
        f"so the cache is partitioned by credential: {first!r} vs {keys!r}"
    )


# ---------------------------------------------------------------------------
# DEFECT 2 — a provider rate-limit denial keeps its type and retry_after
# ---------------------------------------------------------------------------


def _rate_limited_server():
    """Gated + rate-limited server: burst of 1, 6 requests/min.

    ``RateLimiter`` computes ``retry_after = int(60.0 / limit)`` -> 10s here,
    which is distinguishable from ``errors.RateLimitError``'s 60.0 default.
    """
    server = MCPServer(
        "rate-limited",
        enable_cache=False,
        enable_metrics=False,
        auth_provider=APIKeyAuth(keys={API_KEY: {"permissions": [PERMISSION]}}),
        rate_limit_config={"default_limit": 6, "burst_limit": 1},
    )

    @server.tool(required_permission=PERMISSION)
    def fetch_report_sync(report_id: str) -> str:
        """Return a report."""
        return f"report:{report_id}"

    @server.tool(required_permission=PERMISSION)
    async def fetch_report_async(report_id: str) -> str:
        """Return a report."""
        return f"report:{report_id}"

    return server


RATE_LIMIT_TOOLS = [
    pytest.param("fetch_report_sync", id="sync_wrapper"),
    pytest.param("fetch_report_async", id="async_wrapper"),
]


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", RATE_LIMIT_TOOLS)
async def test_rate_limit_denial_keeps_its_type_and_retry_after(tool_name):
    """A throttled call raises RATE_LIMITED with the provider's retry_after."""
    server = _rate_limited_server()
    args = {"report_id": "q3-summary", "api_key": API_KEY}

    # CONTROL: the first call is inside the burst and MUST succeed, so a server
    # that refuses everything cannot make this test pass.
    first = await _maybe_await(server._execute_tool(tool_name, dict(args)))
    assert first == "report:q3-summary", f"the first call was refused: {first!r}"

    with pytest.raises(Exception) as excinfo:
        await _maybe_await(server._execute_tool(tool_name, dict(args)))

    error = excinfo.value
    assert isinstance(error, RateLimitError), (
        "a rate-limit denial did not reach the caller as a RateLimitError; the "
        f"wrapper rewrapped it as {type(error).__name__}: {error!r}"
    )
    assert (
        error.error_code == MCPErrorCode.RATE_LIMITED
    ), f"rate-limit denial carried {error.error_code!r}, not RATE_LIMITED"
    assert error.retry_after == 10, (
        "the provider's computed retry_after (10s) did not survive; the caller "
        f"cannot know when to retry: {error.retry_after!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", RATE_LIMIT_TOOLS)
async def test_rate_limit_message_names_the_tool_not_the_principal(tool_name):
    """The caller-visible message identifies the TOOL, never the caller id.

    ``APIKeyAuth`` derives ``user_id`` as a fingerprint of the API key, so the
    provider's ``"Rate limit exceeded for user {user_id}"`` put a credential
    fingerprint into a caller-visible error string.
    """
    from kailash.utils.url_credentials import fingerprint_secret

    server = _rate_limited_server()
    args = {"report_id": "q3-summary", "api_key": API_KEY}

    await _maybe_await(server._execute_tool(tool_name, dict(args)))
    with pytest.raises(Exception) as excinfo:
        await _maybe_await(server._execute_tool(tool_name, dict(args)))

    message = str(excinfo.value)
    user_id = f"api_key_{fingerprint_secret(API_KEY)}"

    assert user_id not in message, (
        "the caller-visible rate-limit message interpolated the caller's "
        f"api-key-derived user id: {message!r}"
    )
    # CONTROL: the message is still actionable — it names the throttled tool.
    assert tool_name.replace("_sync", "").replace("_async", "") in message or (
        tool_name in message
    ), f"the rate-limit message does not identify the tool: {message!r}"
