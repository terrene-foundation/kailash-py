# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests: LlmClient lifecycle surface (#1388).

`LlmClient` exposed no `close()`/`aclose()`/`__aexit__` lifecycle method, so a
persistent HTTP transport was released only at GC -> `ResourceWarning: unclosed
<socket.socket ...>`, failing any run under `-W error::ResourceWarning`. These
tests pin the new additive lifecycle API:

* `dir(LlmClient)` now exposes `aclose` / `__aenter__` / `__aexit__`.
* `aclose()` is idempotent and a no-op when no transport was created.
* `async with` sets `_managed`, eagerly pools `_http_client`, and drops it on exit.
* Backward-compat: an unmanaged client holds no transport and emits NO
  ResourceWarning at GC.

No network: these construct deployments but never call `embed()`, so they run
without credentials. `sk-test-...` is a placeholder, never sent over the wire.
"""

from __future__ import annotations

import gc
import warnings

import pytest

from kaizen.llm import LlmClient
from kaizen.llm.deployment import LlmDeployment

# A model-key-consistent placeholder. No network call is made by any test in
# this file (no embed()), so the key is never validated or transmitted.
_PLACEHOLDER_KEY = "sk-test-1234567890abcdef"
_EMBED_MODEL = "text-embedding-3-small"


def _deployment() -> LlmDeployment:
    return LlmDeployment.openai(api_key=_PLACEHOLDER_KEY, model=_EMBED_MODEL)


# ---------------------------------------------------------------------------
# Structural: the lifecycle surface exists
# ---------------------------------------------------------------------------


def test_llmclient_exposes_lifecycle_methods() -> None:
    """dir(LlmClient) includes aclose / __aenter__ / __aexit__ (#1388 AC-1)."""
    surface = dir(LlmClient)
    for name in ("aclose", "__aenter__", "__aexit__"):
        assert name in surface, f"LlmClient missing lifecycle method {name!r}"


def test_lifecycle_methods_are_coroutines() -> None:
    """aclose / __aenter__ / __aexit__ are async — deterministic close."""
    import inspect

    assert inspect.iscoroutinefunction(LlmClient.aclose)
    assert inspect.iscoroutinefunction(LlmClient.__aenter__)
    assert inspect.iscoroutinefunction(LlmClient.__aexit__)


# ---------------------------------------------------------------------------
# aclose() idempotence on a never-pooled client (no-op path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_is_noop_idempotent_when_no_transport() -> None:
    """aclose() on a client that never created a transport is a safe no-op.

    Calling it twice MUST NOT raise — covers the one-shot caller who builds a
    client, never enters a managed scope, and (harmlessly) closes it.
    """
    client = LlmClient.from_deployment(_deployment())
    assert client._http_client is None

    await client.aclose()  # no transport -> no-op
    await client.aclose()  # idempotent: still no-op, no error
    assert client._http_client is None


# ---------------------------------------------------------------------------
# Managed (async-context-manager) pooling + deterministic close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_with_pools_then_closes_and_drops_transport() -> None:
    """`async with` sets _managed, eagerly pools _http_client, drops it on exit.

    Inside the scope the persistent transport exists and is open; after the
    block it is closed AND the reference is dropped (so __del__ sees None and a
    re-entered managed embed() re-pools a fresh transport).
    """
    deployment = _deployment()
    async with LlmClient.from_deployment(deployment) as client:
        assert client._managed is True
        assert client._http_client is not None
        assert client._http_client.is_closed is False
        pooled = client._http_client

    # After the block: transport closed and reference dropped.
    assert pooled.is_closed is True
    assert client._http_client is None


@pytest.mark.asyncio
async def test_aclose_idempotent_after_managed_scope() -> None:
    """A second aclose() after the managed scope already closed is a no-op."""
    deployment = _deployment()
    async with LlmClient.from_deployment(deployment) as client:
        assert client._http_client is not None
    # __aexit__ already called aclose(); calling again MUST NOT raise.
    await client.aclose()
    assert client._http_client is None


# ---------------------------------------------------------------------------
# Backward-compat: unmanaged client holds nothing, warns nothing at GC
# ---------------------------------------------------------------------------


def test_unmanaged_client_holds_no_transport_and_warns_nothing_at_gc() -> None:
    """An unmanaged LlmClient.from_deployment(d) emits NO ResourceWarning at GC.

    This is the additive-API guarantee: one-shot callers who never enter a
    managed scope hold `_http_client is None`, so __del__ short-circuits and
    emits no warning — zero behavior change vs the pre-#1388 surface.
    """
    client = LlmClient.from_deployment(_deployment())
    assert client._http_client is None

    # Drain finalizers for any unrelated garbage from prior tests BEFORE the
    # recording window, so this assertion is scoped to THIS client only. Without
    # the pre-drain, a sibling test that leaked a managed client would finalize
    # inside our catch_warnings and be mis-attributed here (GC-order flake).
    gc.collect()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        del client
        gc.collect()

    resource_warnings = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert resource_warnings == [], (
        "unmanaged LlmClient emitted a ResourceWarning at GC; the additive "
        f"lifecycle must not warn for one-shot callers: {[str(w.message) for w in resource_warnings]}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_complete_closes_owned_client_on_non_httpx_send_error(
    monkeypatch,
) -> None:
    """F1: a NON-httpx send-phase failure (SSRF InvalidEndpoint, or a GcpOauth
    token-refresh error from _prepare_auth_headers) happens before `resp` exists
    and escapes the httpx-only excepts. The owned (unmanaged) client MUST still
    be closed — no leaked transport, no ResourceWarning at GC.
    """
    client = LlmClient.from_deployment(_deployment())

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated non-httpx auth-refresh failure")

    # Forces the failure AFTER the owned LlmHttpClient (with a live transport) is
    # created inside complete(), but before the response phase.
    monkeypatch.setattr(client, "_prepare_auth_headers", _boom)

    gc.collect()  # drain unrelated finalizers before the recording window
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(RuntimeError, match="simulated non-httpx"):
            await client.complete([{"role": "user", "content": "hi"}])
        gc.collect()

    resource_warnings = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert resource_warnings == [], (
        "complete() leaked the owned HTTP client on a non-httpx send-phase error "
        f"(F1): {[str(w.message) for w in resource_warnings]}"
    )
