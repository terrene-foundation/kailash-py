"""Regression: Issue #1058 Shards 3 + 4.

**Shard 3** — ``upsert``→``OperationType.UPSERT`` enum gap.

Pre-Shard-3, the generated UpsertNode ran with ``self.operation ==
"upsert"`` but no ``OperationType.UPSERT`` member existed, so the
operation fell through to ``OperationType.CUSTOM_QUERY`` (the
``_operation_mapping.get`` default). Under
``read_only_global`` / ``production_safe`` (which allow only
``{READ}``) the single-record upsert was correctly BLOCKED — but only
because those defaults also block ``CUSTOM_QUERY``. A configuration
that allow-listed specific write ops without ``CUSTOM_QUERY``
over-blocked ``upsert``. Shard 3 promotes UPSERT to a first-class
write op so allowlist semantics work as users would expect.

**Shard 4** — ``Express.import_file`` ProtectionViolation swallow
(same bug class as the ``bulk_update`` swallow Shard 1 closed).

Pre-Shard-4, the per-record ``import_file`` upsert loop AND the
non-upsert ``bulk_create`` branch wrapped the call in a generic
``except Exception as exc: errors.append(...)``. A write-protection
block on a read-only-protected DataFlow would surface inside that
loop as a ``ProtectionViolation``, be caught by the generic clause,
and folded into the ``errors`` list with NO exception propagating to
the caller — silently bypassing write-protection at the
``import_file`` Express surface, just like the closed ``bulk_update``
hole. Shard 4 adds the same ``except ProtectionViolation: raise``
shim ahead of the generic catch.

Spec anchor: ``specs/dataflow-protection.md`` §2 path 1 + I5 — every
Express mutation surface MUST surface protection violations as
exceptions, never fold them into a result dict.

Tier 2 per ``rules/testing.md`` — real backend, no mocking.
File-SQLite (mirroring the Shard-1 sibling regression at
``test_issue_1058_bulk_update_propagates_not_swallowed.py``) because
the contract is dialect-independent and the test must run in any CI
lane without the shared Docker stack.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import (
    GlobalProtection,
    OperationType,
    ProtectionLevel,
    ProtectionViolation,
    WriteProtectionConfig,
)

# ---------------------------------------------------------------------------
# Shard 3 — UPSERT enum gap
# ---------------------------------------------------------------------------


def test_shard3_operation_type_upsert_is_first_class_write_op():
    """``OperationType.UPSERT`` MUST exist as a discrete enum member.

    Pre-Shard-3, this member was absent; ``upsert`` resolved to
    ``CUSTOM_QUERY`` via the ``_operation_mapping.get`` default. This
    structural-invariant test pins the enum so a future refactor that
    removes UPSERT (re-opening the over-block gap) fails loudly.
    """
    # Existence + canonical value
    assert OperationType.UPSERT.value == "upsert"

    # Distinct from CUSTOM_QUERY — that's the exact failure mode this
    # shard closes. CUSTOM_QUERY is reserved for unrecognised ops; UPSERT
    # is a first-class write op.
    assert OperationType.UPSERT is not OperationType.CUSTOM_QUERY


def test_shard3_operation_mapping_routes_upsert_to_upsert_enum():
    """The ``_operation_mapping`` MUST route ``"upsert"`` → UPSERT.

    Pre-Shard-3, ``upsert`` was NOT in the mapping, so
    ``self._operation_mapping.get("upsert", OperationType.CUSTOM_QUERY)``
    returned CUSTOM_QUERY. This test asserts the mapping now points at
    the dedicated write-typed op.
    """
    engine_config = WriteProtectionConfig.read_only_global("test guard")
    from dataflow.core.protection import WriteProtectionEngine

    engine = WriteProtectionEngine(engine_config)
    assert engine._operation_mapping["upsert"] is OperationType.UPSERT


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_shard3_upsert_blocked_under_read_only_global():
    """``enable_read_only_mode`` MUST still BLOCK single-record upsert.

    Pre-Shard-3 this worked accidentally (CUSTOM_QUERY blocked). Post-
    Shard-3 it works by design (UPSERT not in ``{READ}`` allowlist).
    Either way the user-visible behavior MUST be: ProtectionViolation
    raised, no row written.
    """
    tmpdir = tempfile.mkdtemp(prefix="issue1058_shard3_upsert_blocked_")
    db = ProtectedDataFlow(
        database_url=f"sqlite:///{tmpdir}/test.db",
        enable_protection=True,
    )

    @db.model  # noqa: B903 — DataFlow model decorator
    class Issue1058UpsertDoc:
        id: str
        title: str

    try:
        await db.initialize()
        db.enable_read_only_mode("issue #1058 Shard 3 upsert-block guard")

        with pytest.raises(ProtectionViolation):
            await db.express.upsert(
                "Issue1058UpsertDoc",
                {"id": "u-1", "title": "must-not-land"},
            )

        # Read-back: zero rows written. The blocked upsert MUST NOT
        # have created the row.
        rows = await db.express.list("Issue1058UpsertDoc", {})
        assert rows == [], (
            "upsert wrote a row despite read-only protection — "
            "Shard 3 enum mapping bypassed or over-permissive default"
        )
    finally:
        await db.close_async()
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_shard3_allowlist_with_upsert_permits_upsert_blocks_create():
    """A config allow-listing ``{READ, UPSERT}`` MUST permit upsert AND block create.

    This is the user-visible reason Shard 3 exists. Pre-Shard-3, such a
    config would over-block upsert (which fell through to CUSTOM_QUERY,
    not in the allowlist). Post-Shard-3, the allowlist semantics work
    as users expect: every write op the allowlist names is permitted;
    every write op it omits is blocked.
    """
    tmpdir = tempfile.mkdtemp(prefix="issue1058_shard3_allowlist_")
    db = ProtectedDataFlow(
        database_url=f"sqlite:///{tmpdir}/test.db",
        enable_protection=True,
    )

    @db.model  # noqa: B903 — DataFlow model decorator
    class Issue1058AllowDoc:
        id: str
        title: str

    try:
        await db.initialize()

        # Configure protection that allow-lists exactly {READ, UPSERT}.
        # Create MUST be blocked; upsert MUST be permitted.
        config = WriteProtectionConfig(
            global_protection=GlobalProtection(
                protection_level=ProtectionLevel.BLOCK,
                allowed_operations={OperationType.READ, OperationType.UPSERT},
                reason="issue #1058 Shard 3 allowlist guard",
            )
        )
        db.set_protection_config(config)

        # Permitted: upsert lands.
        await db.express.upsert(
            "Issue1058AllowDoc",
            {"id": "ok-1", "title": "upsert-allowed"},
        )
        row = await db.express.read("Issue1058AllowDoc", "ok-1")
        assert row is not None and row["title"] == "upsert-allowed", (
            "upsert was over-blocked despite the allowlist naming UPSERT "
            "explicitly — the Shard 3 enum gap is regressing"
        )

        # Blocked: create raises.
        with pytest.raises(ProtectionViolation):
            await db.express.create(
                "Issue1058AllowDoc",
                {"id": "blocked-1", "title": "must-not-land"},
            )
    finally:
        await db.close_async()
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Shard 4 — Express.import_file ProtectionViolation swallow
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_shard4_import_file_upsert_protection_violation_propagates_not_swallowed():
    """``import_file(upsert=True)`` MUST re-raise ProtectionViolation.

    Pre-Shard-4 the per-record upsert loop wrapped the call in
    ``except Exception as exc: errors.append(...)``. A write-protection
    block surfaced as ProtectionViolation, got swallowed into the
    errors list, and ``import_file`` returned ``{"imported": 0,
    "errors": [...]}`` with NO exception — silently bypassing write-
    protection at the import_file surface (specs/dataflow-protection.md
    §2 path 1 + I5).
    """
    tmpdir = tempfile.mkdtemp(prefix="issue1058_shard4_import_upsert_")
    db = ProtectedDataFlow(
        database_url=f"sqlite:///{tmpdir}/test.db",
        enable_protection=True,
    )

    @db.model  # noqa: B903 — DataFlow model decorator
    class Issue1058ImportUpsertDoc:
        id: str
        title: str

    try:
        await db.initialize()
        db.enable_read_only_mode("issue #1058 Shard 4 import_file upsert guard")

        # Write a 1-row CSV the import_file path will consume. The
        # mutation it triggers (single-record upsert) MUST raise
        # through the import_file surface, not fold into the errors
        # list.
        csv_path = os.path.join(tmpdir, "input.csv")
        with open(csv_path, "w", encoding="utf-8") as fh:
            fh.write("id,title\n")
            fh.write("imp-1,must-not-land\n")

        with pytest.raises(ProtectionViolation):
            await db.express.import_file(
                "Issue1058ImportUpsertDoc",
                csv_path,
                upsert=True,
            )

        # Read-back: zero rows written. The blocked import MUST NOT
        # have created the row.
        rows = await db.express.list("Issue1058ImportUpsertDoc", {})
        assert rows == [], (
            "import_file wrote a row despite read-only protection — "
            "ProtectionViolation was swallowed into the errors list "
            "(Shard 4 propagation contract regressed)"
        )
    finally:
        await db.close_async()
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_shard4_import_file_bulk_create_protection_violation_propagates_not_swallowed():
    """``import_file(upsert=False)`` MUST re-raise ProtectionViolation.

    Same swallow shape as the upsert branch above, on the
    ``bulk_create`` branch. The pre-Shard-4 ``except Exception as exc:
    errors.append(f"Bulk create failed: {exc}")`` line caught the
    ProtectionViolation and silently folded the import into a "soft
    failure" result.
    """
    tmpdir = tempfile.mkdtemp(prefix="issue1058_shard4_import_bulk_create_")
    db = ProtectedDataFlow(
        database_url=f"sqlite:///{tmpdir}/test.db",
        enable_protection=True,
    )

    @db.model  # noqa: B903 — DataFlow model decorator
    class Issue1058ImportBulkCreateDoc:
        id: str
        title: str

    try:
        await db.initialize()
        db.enable_read_only_mode("issue #1058 Shard 4 import_file bulk_create guard")

        csv_path = os.path.join(tmpdir, "input.csv")
        with open(csv_path, "w", encoding="utf-8") as fh:
            fh.write("id,title\n")
            fh.write("imp-1,must-not-land-1\n")
            fh.write("imp-2,must-not-land-2\n")

        with pytest.raises(ProtectionViolation):
            await db.express.import_file(
                "Issue1058ImportBulkCreateDoc",
                csv_path,
                upsert=False,
            )

        # Read-back: zero rows written.
        rows = await db.express.list("Issue1058ImportBulkCreateDoc", {})
        assert rows == [], (
            "import_file (bulk_create branch) wrote rows despite "
            "read-only protection — ProtectionViolation was swallowed "
            "into the errors list (Shard 4 propagation contract regressed)"
        )
    finally:
        await db.close_async()
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
