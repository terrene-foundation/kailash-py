# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Phase 7.2 — correlation ID ContextVar contract.

Verifies the per-task scoping, nesting, reset-on-exit, and None
sentinel behavior documented in ``rules/observability.md`` § Rule 2
(Correlation ID on Every Log Line).
"""
from __future__ import annotations

import asyncio

import pytest

from dataflow.observability import (
    clear_correlation_id,
    get_correlation_id,
    set_correlation_id,
    with_correlation_id,
)

pytestmark = pytest.mark.unit


class TestCorrelationIdSyncContract:
    """ContextVar-based get / set / clear in a sync scope."""

    def test_default_is_none(self):
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_set_then_get(self):
        clear_correlation_id()
        set_correlation_id("req-42")
        assert get_correlation_id() == "req-42"

    def test_clear_resets_to_none(self):
        set_correlation_id("req-42")
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_empty_string_is_literal_not_none(self):
        """Passing '' must bind the literal empty string, NOT clear.

        Downstream log aggregators distinguish ``null`` from ``""``;
        this test locks the semantics so operators can tell "upstream
        middleware supplied an empty ID" apart from "no middleware
        supplied an ID".
        """
        clear_correlation_id()
        set_correlation_id("")
        assert get_correlation_id() == ""
        clear_correlation_id()


class TestCorrelationIdContextManager:
    """``with_correlation_id`` binds + restores on exit."""

    def test_with_block_binds_value(self):
        clear_correlation_id()
        with with_correlation_id("outer") as cid:
            assert cid == "outer"
            assert get_correlation_id() == "outer"

    def test_with_block_restores_on_exit(self):
        set_correlation_id("outer")
        with with_correlation_id("inner"):
            assert get_correlation_id() == "inner"
        assert get_correlation_id() == "outer"
        clear_correlation_id()

    def test_with_block_restores_on_exception(self):
        set_correlation_id("outer")
        with pytest.raises(RuntimeError):
            with with_correlation_id("inner"):
                assert get_correlation_id() == "inner"
                raise RuntimeError("oops")
        assert get_correlation_id() == "outer"
        clear_correlation_id()

    def test_nested_blocks_stack_and_unwind(self):
        clear_correlation_id()
        with with_correlation_id("a"):
            with with_correlation_id("b"):
                with with_correlation_id("c"):
                    assert get_correlation_id() == "c"
                assert get_correlation_id() == "b"
            assert get_correlation_id() == "a"
        assert get_correlation_id() is None


class TestCorrelationIdAsyncIsolation:
    """Concurrent asyncio tasks MUST not see each other's IDs.

    This is the whole point of using ``ContextVar`` over module-level
    state — two requests handled concurrently by the same worker
    process see different correlation IDs.
    """

    @pytest.mark.asyncio
    async def test_concurrent_tasks_have_isolated_ids(self):
        results: dict[str, str | None] = {}

        async def handler(request_id: str) -> None:
            with with_correlation_id(request_id):
                # Yield control so the sibling task interleaves here.
                await asyncio.sleep(0)
                # After the sibling ran, our own binding MUST still
                # be what we set — this is the isolation assertion.
                results[request_id] = get_correlation_id()

        await asyncio.gather(
            handler("req-A"),
            handler("req-B"),
            handler("req-C"),
        )

        assert results == {
            "req-A": "req-A",
            "req-B": "req-B",
            "req-C": "req-C",
        }

    @pytest.mark.asyncio
    async def test_task_inherits_parent_id(self):
        """An asyncio task spawned inside a with_correlation_id
        block inherits the parent's binding."""
        clear_correlation_id()

        async def child() -> str | None:
            return get_correlation_id()

        with with_correlation_id("parent-42"):
            child_id = await asyncio.create_task(child())

        assert child_id == "parent-42"
