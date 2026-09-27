# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: the four ``db.express.bulk_*`` surfaces MUST fire NO side
effects when handed an empty record / id list (RT-6a).

Pre-fix, every one of ``bulk_create`` / ``bulk_update`` / ``bulk_delete`` /
``bulk_upsert`` ran its tail unconditionally on an empty input:

  * a model-scoped cache flush (``_invalidate_model_cache``) — wasted work;
  * a ``DomainEvent`` (``_emit_write_event``) announcing a write that never
    happened — subscribers were told rows changed when none did;
  * and for three of the four, an actual NODE DISPATCH
    (``node.async_run(data=[])`` / ``filter={"id": {"$in": []}}``) —
    a round trip to the bulk node for a batch with nothing in it.

``bulk_update`` is the exception on the third point only: it is a
per-record loop delegating to ``self.update()``, so an empty list already
executed no query — but its cache flush and write event still fired.

Severity is LOW and deliberately not inflated: a wasted flush plus a
spurious event. Neither is a security issue. The defensible concern is the
event — an event bus subscriber (audit tailer, cache warmer, CDC bridge)
that acts on ``dataflow.<Model>.bulk_update`` was being woken for a no-op.

GUARD PLACEMENT IS PART OF THE CONTRACT. Each early return is placed
AFTER ``_check_append_only`` and AFTER ``_check_protection_if_enabled``,
so an empty list can never be used to slip past a fail-closed
authorization gate. ``test_empty_list_does_not_bypass_*`` below pins that
ordering; moving a guard above either check reddens them.

NOT covered by the pre-existing look-alikes: both
``tests/integration/bulk_operations/test_bulk_update_real_operations.py::
test_bulk_update_empty_data_list`` and ``...::
test_v052_bug_reproduction.py::test_bulk_create_with_empty_data_list``
drive the generated ``*BulkUpdateNode`` / ``*BulkCreateNode`` through a
``WorkflowBuilder``. They never touch ``db.express``, assert nothing about
cache invalidation or write events, and would stay green with every guard
in this file reverted.

Tier 2 per ``rules/testing.md`` — real file-backed SQLite, no mocked
database. The recorders below WRAP the real helpers and call through; they
observe call sites, they do not replace the backend.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Dict, List, Tuple

import pytest

from dataflow import DataFlow
from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import OperationType, ProtectionLevel, ProtectionViolation
from dataflow.exceptions import AppendOnlyViolationError


class SideEffectRecorder:
    """Call-through spy over the three observable bulk side effects.

    Every hook delegates to the real implementation, so the database, the
    cache and the event bus all behave exactly as they would untouched —
    this records WHETHER each was reached, it does not stub any of them.
    """

    def __init__(self, db: DataFlow) -> None:
        self.dispatches: List[str] = []
        self.invalidations: List[str] = []
        self.events: List[Tuple[str, str]] = []

        express = db.express
        real_create_node = express._create_node
        real_invalidate = express._invalidate_model_cache
        real_emit = getattr(db, "_emit_write_event")

        def spy_create_node(model: str, operation: str):
            node = real_create_node(model, operation)
            real_run = node.async_run

            async def spy_run(**kwargs: Any):
                self.dispatches.append(operation)
                return await real_run(**kwargs)

            node.async_run = spy_run
            return node

        async def spy_invalidate(model: str):
            self.invalidations.append(model)
            return await real_invalidate(model)

        def spy_emit(model_name: str, operation: str, record_id: Any = None):
            self.events.append((model_name, operation))
            return real_emit(model_name, operation, record_id=record_id)

        express._create_node = spy_create_node
        express._invalidate_model_cache = spy_invalidate
        db._emit_write_event = spy_emit

    def reset(self) -> None:
        self.dispatches.clear()
        self.invalidations.clear()
        self.events.clear()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "dispatches": list(self.dispatches),
            "invalidations": list(self.invalidations),
            "events": list(self.events),
        }

    def assert_silent(self, label: str) -> None:
        assert self.snapshot() == {
            "dispatches": [],
            "invalidations": [],
            "events": [],
        }, f"{label}: empty input fired side effects: {self.snapshot()}"


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_bulk_create_empty_list_fires_no_side_effects(sqlite_file_url):
    """``bulk_create(model, [])`` dispatches no node, flushes no cache,
    emits no event — while the 1-record CONTROL does all three."""
    db = DataFlow(database_url=sqlite_file_url)

    @db.model  # noqa: F841 — registration is the decorator's side effect
    class Rt6aCreateWidget:
        id: str
        name: str

    await db.initialize()
    spy = SideEffectRecorder(db)

    # --- SUBJECT: empty batch ---
    spy.reset()
    result = await db.express.bulk_create("Rt6aCreateWidget", [])
    spy.assert_silent("bulk_create")
    # Return shape: `[]` is the declared contract (-> List[Dict[str, Any]])
    # and is already what the three _apply_classification_mask_rows branches
    # yield for an empty batch.
    assert result == []

    # --- CONTROL: without this, a method broken outright would still pass ---
    spy.reset()
    await db.express.bulk_create("Rt6aCreateWidget", [{"id": "c1", "name": "a"}])
    assert spy.dispatches == ["BulkCreate"], spy.snapshot()
    assert spy.invalidations == ["Rt6aCreateWidget"], spy.snapshot()
    assert spy.events == [("Rt6aCreateWidget", "bulk_create")], spy.snapshot()


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_bulk_update_empty_list_fires_no_side_effects(sqlite_file_url):
    """``bulk_update(model, [])`` flushes no cache and emits no event.

    This is the RT-6a finding as originally reported: the per-record loop
    was already a no-op on an empty list, but the two side effects after
    it fired regardless.
    """
    db = DataFlow(database_url=sqlite_file_url)

    @db.model  # noqa: F841 — registration is the decorator's side effect
    class Rt6aUpdateWidget:
        id: str
        name: str

    await db.initialize()
    await db.express.create("Rt6aUpdateWidget", {"id": "c1", "name": "before"})
    spy = SideEffectRecorder(db)

    # --- SUBJECT: empty batch ---
    spy.reset()
    result = await db.express.bulk_update("Rt6aUpdateWidget", [])
    spy.assert_silent("bulk_update")
    # Matches the non-empty path's `return results` (a list).
    assert result == []

    # --- CONTROL ---
    spy.reset()
    updated = await db.express.bulk_update(
        "Rt6aUpdateWidget", [{"id": "c1", "name": "after"}]
    )
    assert len(updated) == 1, updated
    assert spy.invalidations, spy.snapshot()
    assert ("Rt6aUpdateWidget", "bulk_update") in spy.events, spy.snapshot()


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_bulk_delete_empty_list_fires_no_side_effects(sqlite_file_url):
    """``bulk_delete(model, [])`` no longer dispatches BulkDelete with the
    degenerate filter ``{"id": {"$in": []}}``."""
    db = DataFlow(database_url=sqlite_file_url)

    @db.model  # noqa: F841 — registration is the decorator's side effect
    class Rt6aDeleteWidget:
        id: str
        name: str

    await db.initialize()
    await db.express.create("Rt6aDeleteWidget", {"id": "c1", "name": "a"})
    spy = SideEffectRecorder(db)

    # --- SUBJECT: empty id list ---
    spy.reset()
    result = await db.express.bulk_delete("Rt6aDeleteWidget", [])
    spy.assert_silent("bulk_delete")
    # Matches the non-empty path's bool contract: "True if all deletions
    # succeeded" is vacuously true when there are none.
    assert result is True

    # --- CONTROL ---
    spy.reset()
    await db.express.bulk_delete("Rt6aDeleteWidget", ["c1"])
    assert spy.dispatches == ["BulkDelete"], spy.snapshot()
    assert spy.invalidations == ["Rt6aDeleteWidget"], spy.snapshot()
    assert spy.events == [("Rt6aDeleteWidget", "bulk_delete")], spy.snapshot()


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_bulk_upsert_empty_list_fires_no_side_effects(sqlite_file_url):
    """``bulk_upsert(model, [])`` dispatches no node and fires no side
    effects, returning the same counts dict the non-empty path produced
    for an empty batch pre-fix."""
    db = DataFlow(database_url=sqlite_file_url)

    @db.model  # noqa: F841 — registration is the decorator's side effect
    class Rt6aUpsertWidget:
        id: str
        name: str

    await db.initialize()
    spy = SideEffectRecorder(db)

    # --- SUBJECT: empty batch ---
    spy.reset()
    result = await db.express.bulk_upsert("Rt6aUpsertWidget", [])
    spy.assert_silent("bulk_upsert")
    # Byte-identical to the measured pre-fix empty return — no new shape.
    assert result == {"records": [], "created": 0, "updated": 0, "total": 0}

    # --- CONTROL ---
    spy.reset()
    control = await db.express.bulk_upsert(
        "Rt6aUpsertWidget", [{"id": "u1", "name": "a"}]
    )
    assert control["total"] == 1, control
    assert spy.dispatches == ["BulkUpsert"], spy.snapshot()
    assert spy.invalidations == ["Rt6aUpsertWidget"], spy.snapshot()
    assert spy.events == [("Rt6aUpsertWidget", "bulk_upsert")], spy.snapshot()


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_empty_list_does_not_bypass_append_only_guard(sqlite_file_url):
    """An empty list MUST NOT be a way past ``_check_append_only``.

    Reddens if any RT-6a guard is hoisted above the append-only check.
    """
    db = DataFlow(database_url=sqlite_file_url)

    @db.model  # noqa: F841 — registration is the decorator's side effect
    class Rt6aLedger:
        id: str
        amount: int

    db._models["Rt6aLedger"]["append_only"] = True
    await db.initialize()

    with pytest.raises(AppendOnlyViolationError):
        await db.express.bulk_update("Rt6aLedger", [])
    with pytest.raises(AppendOnlyViolationError):
        await db.express.bulk_delete("Rt6aLedger", [])
    with pytest.raises(AppendOnlyViolationError):
        await db.express.bulk_upsert("Rt6aLedger", [])

    # CONTROL: bulk_create is permitted on append-only models by design,
    # so an empty bulk_create must NOT raise.
    assert await db.express.bulk_create("Rt6aLedger", []) == []


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_empty_list_does_not_bypass_write_protection(sqlite_file_url):
    """An empty list MUST NOT be a way past the write-protection precheck.

    Reddens if any RT-6a guard is hoisted above
    ``_check_protection_if_enabled``.
    """
    db = ProtectedDataFlow(database_url=sqlite_file_url, enable_protection=True)

    @db.model  # noqa: F841 — registration is the decorator's side effect
    class Rt6aProtectedDoc:
        id: str
        title: str

    await db.initialize()
    engine = db._protection_engine
    assert engine is not None, "protection engine must be wired for this test"

    calls: List[str] = []

    # The stub is DERIVED from the real callee, never hand-rolled to match
    # the call site. ``real_sig.bind`` reds with TypeError if production
    # ever calls ``check_operation`` with a shape the REAL signature would
    # reject — a hand-written ``(operation, model_name, connection_string,
    # context)`` stub silently binds the 3rd positional to ``field_name``
    # and is unfalsifiable by construction.
    real_check = engine.check_operation
    real_sig = inspect.signature(real_check)

    @functools.wraps(real_check)
    def blocked(*args: Any, **kwargs: Any):
        bound = real_sig.bind(*args, **kwargs)
        bound.apply_defaults()
        operation = bound.arguments["operation"]
        model_name = bound.arguments.get("model_name")
        calls.append(str(operation))
        raise ProtectionViolation(
            f"blocked: {operation} on {model_name}",
            operation=OperationType.BULK_CREATE,
            level=ProtectionLevel.BLOCK,
            model=model_name,
        )

    engine.check_operation = blocked

    for call in (
        lambda: db.express.bulk_create("Rt6aProtectedDoc", []),
        lambda: db.express.bulk_delete("Rt6aProtectedDoc", []),
        lambda: db.express.bulk_upsert("Rt6aProtectedDoc", []),
    ):
        with pytest.raises(ProtectionViolation):
            await call()

    assert calls == ["bulk_create", "bulk_delete", "bulk_upsert"], calls
