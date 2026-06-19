# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #1388 — LlmClient ResourceWarning lifecycle.

Issue #1388: `kaizen.llm.client.LlmClient` exposed no
`close()`/`aclose()`/`__aexit__` lifecycle method. Once the client held a
persistent HTTP transport, the socket was released only at GC ->
`ResourceWarning: unclosed <socket.socket ...>`, which fails any run under
`-W error::ResourceWarning`.

Acceptance criteria (#1388):
  1. `LlmClient` exposes `aclose()` AND `__aenter__`/`__aexit__` that
     deterministically close the underlying HTTP transport.
  2. After an explicit close, no `unclosed <socket.socket ...>` ResourceWarning
     is emitted at GC.

NOTE: `packages/kailash-kaizen/pytest.ini` globally does `ignore::ResourceWarning`
(line 38). The first test below overrides that locally via
`@pytest.mark.filterwarnings("error::ResourceWarning")` so the "no warning after
close" assertion is REAL — a leaked socket would raise, not be silently swallowed.
The second test uses `warnings.catch_warnings()` + `simplefilter("always")` so the
WARN-path is observed even under the global ignore.
"""

from __future__ import annotations

import gc
import warnings

import pytest

from kaizen.llm import LlmClient
from kaizen.llm.deployment import LlmDeployment

_PLACEHOLDER_KEY = "sk-test-1388-regression-key"
_EMBED_MODEL = "text-embedding-3-small"


def _deployment() -> LlmDeployment:
    return LlmDeployment.openai(api_key=_PLACEHOLDER_KEY, model=_EMBED_MODEL)


# ---------------------------------------------------------------------------
# AC-2: after an explicit close, GC emits NO ResourceWarning
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.filterwarnings("error::ResourceWarning")
async def test_issue_1388_managed_client_no_resourcewarning_after_async_with() -> None:
    """After `async with LlmClient ...` exits, GC emits NO ResourceWarning.

    The `error::ResourceWarning` filter OVERRIDES pytest.ini's global
    `ignore::ResourceWarning` for this test, so a leaked transport socket would
    raise the warning as an error and fail the test rather than be silenced.
    """
    deployment = _deployment()
    async with LlmClient.from_deployment(deployment) as client:
        # Managed scope pooled a real LlmHttpClient transport.
        assert client._http_client is not None
    # Exited: transport closed + reference dropped. GC must not warn.
    assert client._http_client is None

    del deployment, client
    gc.collect()  # would raise ResourceWarning-as-error if a socket leaked


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.filterwarnings("error::ResourceWarning")
async def test_issue_1388_explicit_aclose_no_resourcewarning_at_gc() -> None:
    """After explicit `await client.aclose()`, GC emits NO ResourceWarning.

    Covers the non-context-manager path: a managed client closed by an explicit
    aclose() call (not via __aexit__) must also leave nothing to leak at GC.
    """
    deployment = _deployment()
    client = LlmClient.from_deployment(deployment)
    await client.__aenter__()  # enter managed mode + pool the transport
    assert client._http_client is not None

    await client.aclose()
    assert client._http_client is None

    del deployment, client
    gc.collect()  # would raise ResourceWarning-as-error if a socket leaked


# ---------------------------------------------------------------------------
# Warn-path is wired: an UNCLOSED managed client warns at __del__
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1388_unclosed_managed_client_warns_at_del() -> None:
    """An unclosed managed client that pooled a transport WARNS at __del__.

    Proves the warn-path is wired (not silently swallowed): the finalizer emits
    a ResourceWarning whose message names `aclose`, directing the caller to the
    fix. Uses `catch_warnings(record=True)` so the warning is observed even
    under pytest.ini's global `ignore::ResourceWarning`.

    Runs under `@pytest.mark.asyncio` so `__aenter__` / the pooled transport's
    `aclose()` are awaited in pytest-asyncio's own managed event loop — NO
    throwaway `asyncio.new_event_loop()` is created, so the test leaks neither
    an event loop nor its selector self-pipe sockets (the finalizer warning
    under test is LlmClient's, not the test harness's own).
    """
    client = LlmClient.from_deployment(_deployment())
    # Enter managed mode + pool a real transport, awaited in the running loop.
    await client.__aenter__()
    pooled = client._http_client
    assert pooled is not None  # a real transport was pooled

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        del client  # refcount hits 0 -> LlmClient.__del__ fires (pooled holds the transport)
        gc.collect()

    resource_warnings = [w for w in caught if issubclass(w.category, ResourceWarning)]
    # At least one ResourceWarning, naming aclose, from LlmClient.__del__.
    messages = [str(w.message) for w in resource_warnings]
    assert any("aclose" in m for m in messages), (
        "unclosed managed LlmClient did not emit a ResourceWarning naming "
        f"`aclose` at __del__; got: {messages}"
    )

    # Clean up the pooled transport we deliberately leaked so this test does not
    # itself leave a dangling socket for a sibling test to trip over.
    await pooled.aclose()
