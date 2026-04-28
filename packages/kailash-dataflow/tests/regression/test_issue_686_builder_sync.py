# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #686 — DataFlowEngineBuilder.build sync.

Pre-fix: ``DataFlowEngineBuilder.build()`` was ``async def`` but the
body had no ``await``s. Module-import-time patterns (``@lru_cache``
factories, top-level ``DataFlow`` setup, fixtures running before any
event loop is bound) had to wrap the call in ``asyncio.run()``, which
then crashed with ``RuntimeError: This event loop is already running``
inside Nexus / FastAPI handlers, pytest-asyncio, and Jupyter kernels.

Post-fix:
1. ``build_sync()`` is the canonical body — synchronous, no event loop
   required.
2. The async ``build()`` becomes a thin wrapper that calls
   ``build_sync()`` so both surfaces share a single body and cannot
   drift.
3. The async signature is preserved for cross-SDK parity with
   kailash-rs (where the equivalent IS legitimately async).

Per rules/cross-sdk-inspection.md § 3a, this file also includes a
**structural API-divergence test** that pins the async signature so a
future refactor that mistakenly drops the async surface (or grows
``build()`` body to use ``asyncio.run``) fails loudly.
"""

from __future__ import annotations

import asyncio
import inspect
from functools import lru_cache

import pytest

from dataflow import DataFlowEngine
from dataflow.engine import DataFlowEngineBuilder


@pytest.mark.regression
def test_build_sync_works_at_module_import_time(sqlite_file_url):
    """Repro from issue #686.

    The ``@lru_cache get_db()`` pattern is the canonical
    module-import-time use case. Before the fix this required either
    ``asyncio.run(builder.build())`` (RuntimeError under any running
    loop) OR awaiting in an async wrapper (crashes top-level imports).

    Post-fix: ``build_sync()`` works synchronously with no event loop
    required and is safe to call from any caller context.
    """
    factory_url = sqlite_file_url

    @lru_cache(maxsize=1)
    def get_engine() -> DataFlowEngine:
        return (
            DataFlowEngine.builder(factory_url).slow_query_threshold(0.5).build_sync()
        )

    engine_a = get_engine()
    engine_b = get_engine()

    assert engine_a is engine_b  # lru_cache works
    assert engine_a.dataflow is not None
    assert engine_a.query_engine.slow_query_threshold == 0.5


@pytest.mark.regression
def test_build_sync_and_build_async_produce_identical_state(sqlite_file_url):
    """Both paths produce identical engine state.

    Per the DPI-C2 contract, ``build()`` is implemented as a thin
    wrapper that calls ``build_sync()``. Both paths MUST yield engines
    with structurally equivalent internal state — same DataFlow
    config, same QueryEngine threshold, same validate_on_write flag,
    same fabric config carried through.
    """
    builder_factory = lambda: (  # noqa: E731 — concise factory
        DataFlowEngine.builder(sqlite_file_url)
        .slow_query_threshold(0.7)
        .validate_on_write(True)
    )

    sync_engine = builder_factory().build_sync()
    async_engine = asyncio.run(builder_factory().build())

    # Top-level structural equality across both surfaces.
    assert sync_engine.query_engine.slow_query_threshold == (
        async_engine.query_engine.slow_query_threshold
    )
    assert sync_engine.validate_on_write == async_engine.validate_on_write
    assert sync_engine.validation == async_engine.validation
    assert sync_engine.classification == async_engine.classification

    # Both engines wrap a real DataFlow instance with the same URL.
    assert sync_engine.dataflow.config.database.url == (
        async_engine.dataflow.config.database.url
    )


@pytest.mark.regression
def test_async_build_signature_invariant():
    """Structural invariant — async ``build()`` signature is preserved.

    Per rules/cross-sdk-inspection.md § 3a: pinning the async signature
    means that a future refactor which "simplifies" by removing the
    ``async`` keyword (and so breaks cross-SDK parity with kailash-rs)
    fails this test loudly with a direct pointer back to the
    cross-SDK contract.

    The async surface is intentionally kept even though the kailash-py
    body is sync, because the Rust DataFlowEngineBuilder.build IS
    legitimately async and downstream cross-SDK code expects to
    ``await`` build() regardless of language.
    """
    # build() MUST stay async.
    assert inspect.iscoroutinefunction(DataFlowEngineBuilder.build), (
        "DataFlowEngineBuilder.build MUST remain async for cross-SDK "
        "parity with kailash-rs (rules/cross-sdk-inspection.md § 3a). "
        "If you intentionally removed async, you have broken the "
        "cross-SDK contract and MUST file a kailash-rs issue first."
    )

    # build_sync() MUST stay sync — that's the entire point of having it.
    assert not inspect.iscoroutinefunction(DataFlowEngineBuilder.build_sync), (
        "DataFlowEngineBuilder.build_sync MUST remain synchronous. "
        "If async was added, the build_sync companion has lost its "
        "purpose (module-import-time patterns)."
    )

    # Signature pin: build() returns DataFlowEngine; build_sync() returns
    # DataFlowEngine. Both signatures must accept only ``self``.
    build_sig = inspect.signature(DataFlowEngineBuilder.build)
    build_sync_sig = inspect.signature(DataFlowEngineBuilder.build_sync)
    build_params = [n for n in build_sig.parameters if n != "self"]
    build_sync_params = [n for n in build_sync_sig.parameters if n != "self"]
    assert build_params == [], f"build() signature drifted: {build_sig}"
    assert build_sync_params == [], f"build_sync() signature drifted: {build_sync_sig}"


@pytest.mark.regression
def test_build_sync_works_under_running_event_loop(sqlite_file_url):
    """``build_sync()`` works even when called from inside a running loop.

    The original issue #686 failure mode: callers wrapped
    ``asyncio.run(builder.build())`` and crashed under pytest-asyncio /
    Nexus handlers / Jupyter. ``build_sync()`` MUST work in any caller
    context — sync, async, nested.
    """

    async def _build_inside_loop() -> DataFlowEngine:
        # Inside a running loop. asyncio.run would raise RuntimeError.
        # build_sync must work without any wrapping.
        return DataFlowEngine.builder(sqlite_file_url).build_sync()

    engine = asyncio.run(_build_inside_loop())
    assert engine is not None
    assert engine.dataflow is not None
