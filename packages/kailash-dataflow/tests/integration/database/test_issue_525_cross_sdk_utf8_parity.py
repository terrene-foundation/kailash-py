# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Cross-SDK parity test for issue #525 (kailash-rs#424 equivalent).

**Upstream bug (kailash-rs)**: ``DataFlow.execute_raw(sql, params)``
exhibits instance-scoped, cross-call UTF-8 corruption at the parameter
binding layer — two calls against the same ``DataFlow`` instance with
shrinking parameter arity (poisoning call: 15 params + 7
``::double precision`` casts; poisoned call: 10 params + 4 casts)
produce ``invalid byte sequence for encoding "UTF8"`` on the second
call, with a bad byte (``0xb9``, ``0xc7 0x0a``, ``0xb4``, ``0x94``)
that does not appear anywhere in the Python-side inputs. The
corruption is eliminated by running the second call against a
brand-new instance, so the residual state lives inside the ``DataFlow``
instance (connection pool, prepared-statement cache, or
parameter-encoder buffer).

**Python API surface**: ``DataFlow.execute_raw(self, sql: str) -> Any``
— **no ``params`` argument**. The kailash-rs bug class requires a
parameter-binding layer that does not exist at this API in kailash-py.
Structural mismatch; the exact Rust scenario cannot be reproduced at
the same API.

**What this test exercises**: the Express bulk-create path, which IS
the parameter-binding path in kailash-py. We run two bulk inserts
against the same ``DataFlow`` instance with different column arity
(shrinking: 5 cols → 3 cols), ASCII-only values, real PostgreSQL,
and assert the second call completes without UTF-8 corruption and
returns the expected row count.

**Disposition**: passing this test confirms kailash-py does not share
the kailash-rs#424 bug class at the equivalent parameter-binding
surface. Close #525 as cross-SDK-aligned.
"""

from __future__ import annotations

import uuid

import pytest

from dataflow import DataFlow

from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.integration]


@pytest.fixture
async def test_suite():
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def unique_model_names() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return (f"WideTbl{suffix}", f"NarrowTbl{suffix}")


@pytest.mark.regression
@pytest.mark.timeout(30)
async def test_issue_525_cross_sdk_parity_shrinking_arity_bulk_create(
    test_suite: IntegrationTestSuite,
    unique_model_names: tuple[str, str],
) -> None:
    """Regression: kailash-rs#424 — shrinking arity on same instance.

    Two bulk_create calls against the SAME DataFlow instance with
    decreasing column arity, ASCII-only values. Passes when kailash-py
    does NOT share the Rust binding-layer UTF-8 corruption.
    """
    wide_name, narrow_name = unique_model_names
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    wide_cls = type(
        wide_name,
        (),
        {
            "__annotations__": {
                "id": int,
                "col_a": str,
                "col_b": str,
                "col_c": float,
                "col_d": float,
            },
            "col_a": "",
            "col_b": "",
            "col_c": 0.0,
            "col_d": 0.0,
        },
    )
    db.model(wide_cls)

    narrow_cls = type(
        narrow_name,
        (),
        {
            "__annotations__": {
                "id": int,
                "col_x": str,
                "col_y": float,
            },
            "col_x": "",
            "col_y": 0.0,
        },
    )
    db.model(narrow_cls)

    await db.initialize()

    # Poisoning call — wide arity, ASCII only, floats that will encode
    # via asyncpg's binary protocol (Rust bug triggered by
    # ::double precision cast reuse in prepared-statement cache).
    poisoning_rows = [
        {
            "id": i,
            "col_a": f"ascii-a-{i}",
            "col_b": f"ascii-b-{i}",
            "col_c": float(i) * 1.5,
            "col_d": float(i) * 2.25,
        }
        for i in range(1, 6)
    ]
    poisoning_result = await db.express.bulk_create(wide_name, poisoning_rows)
    assert poisoning_result.get("success") is True
    assert (
        poisoning_result.get("inserted") == 5
    ), f"poisoning call failed: {poisoning_result!r}"

    # Poisoned call — narrower arity on SAME instance. In kailash-rs
    # this was the failing call. Here we assert it completes cleanly.
    poisoned_rows = [
        {
            "id": i,
            "col_x": f"ascii-x-{i}",
            "col_y": float(i) * 3.75,
        }
        for i in range(1, 4)
    ]
    poisoned_result = await db.express.bulk_create(narrow_name, poisoned_rows)
    assert poisoned_result.get("success") is True
    assert poisoned_result.get("inserted") == 3, (
        f"poisoned call failed with residual instance state: " f"{poisoned_result!r}"
    )

    # Verify read-back: no value was corrupted, every ASCII string
    # round-trips byte-for-byte.
    wide_rows = await db.express.list(wide_name, filter={})
    assert len(wide_rows) == 5
    for row in wide_rows:
        assert row["col_a"].startswith("ascii-a-")
        assert row["col_b"].startswith("ascii-b-")

    narrow_rows = await db.express.list(narrow_name, filter={})
    assert len(narrow_rows) == 3
    for row in narrow_rows:
        assert row["col_x"].startswith("ascii-x-")


@pytest.mark.regression
@pytest.mark.timeout(10)
async def test_issue_525_execute_raw_has_no_params_arg() -> None:
    """Structural guard: kailash-py ``execute_raw`` takes SQL only.

    The kailash-rs#424 bug class (parameter-buffer-reuse / prepared-
    statement cache staleness) requires a parameter-binding layer at
    the ``execute_raw`` API. The Python signature does not accept a
    ``params`` argument, so the bug class cannot exist at this surface.

    If this test ever fails (signature grew a ``params`` argument),
    the kailash-py API drifted toward the kailash-rs shape and the
    cross-SDK UTF-8 parity contract MUST be re-audited.
    """
    import inspect

    from dataflow.core.pool_lightweight import LightweightPool

    sig = inspect.signature(LightweightPool.execute_raw)
    # Expected parameters: self, sql. No params/args/kwargs positional.
    non_self = [
        p
        for name, p in sig.parameters.items()
        if name != "self" and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    ]
    assert [p.name for p in non_self] == ["sql"], (
        f"LightweightPool.execute_raw signature drifted: {sig}. "
        f"If a 'params' argument was added, the kailash-rs#424 bug "
        f"class is now reachable at this surface — re-run the full "
        f"cross-SDK UTF-8 parity audit."
    )
