# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for mutation-return classification redaction.

Issue #490 — DataFlowExpress mutation-return paths leak classified
fields. Before this fix, ``create()``, ``update()``, ``upsert()``,
``upsert_advanced()``, ``bulk_create()``, and ``bulk_upsert()`` echoed
the mutated row back to the caller as a plain ``row_to_dict``, leaking
PII / SECRET / HIGHLY_CONFIDENTIAL field values regardless of caller
clearance. The read path (``read()`` / ``list()`` / ``find_one()``)
already applied masking via ``ClassificationPolicy.apply_masking_to_record``;
the leak was in the mutation return paths.

These tests pin the contract mandated by
``.claude/rules/dataflow-classification.md`` MUST Rule 1: every public
mutation path that echoes a row back to the caller MUST apply the same
read-path redaction policy. A low-clearance caller that creates,
updates, upserts, or bulk-inserts a record with a classified field MUST
see ``[REDACTED]`` in the return value, not the plaintext.

The tests use real PostgreSQL via ``IntegrationTestSuite`` (no mocks
per testing.md § Tier 2) and exercise the full dialect code path
(``$N`` placeholders, ``RETURNING``, ``ON CONFLICT``) where a
dialect-specific divergence from the SQLite path would surface.

Cross-SDK reference: kailash-rs commit ``2e9dbf94`` closed the same
bug in Rust (``crates/kailash-dataflow/tests/hardening_292_295_296_299.rs``
§ ``gh-coc-claude-rs#51 item 3e``).
"""

from __future__ import annotations

import uuid

import pytest

from dataflow import DataFlow
from dataflow.classification import (
    DataClassification,
    MaskingStrategy,
    classify,
)
from dataflow.core.agent_context import async_clearance_context

from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with real PostgreSQL."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def unique_model_name() -> str:
    """Unique DataFlow model name per test — avoids registry collisions."""
    return f"Doc{uuid.uuid4().hex[:10]}"


def _make_db_with_named_pii_model(db_url: str, model_name: str) -> DataFlow:
    """Cleaner variant: produce a uniquely-named class via a factory.

    This is the form actually used by the tests. The model has:
      - ``id`` (primary key)
      - ``title`` (unclassified, sanity check for non-redaction)
      - ``body`` (PII, REDACT — the field that MUST be masked)

    Pool sizes are intentionally small (pool_size=2, max_overflow=2) so
    the suite's 9 independent DataFlow instances do not saturate the
    PostgreSQL ``max_connections`` budget when tests run back-to-back.
    """
    db = DataFlow(
        db_url,
        auto_migrate=True,
        pool_size=2,
        max_overflow=2,
    )

    # Build a fresh class per test, named ``model_name``. We cannot use
    # ``@classify`` + ``@db.model`` directly on a dynamically-named
    # class without ``type()``, so use ``type()`` to build the class
    # with the unique name, apply ``@classify`` manually, then register
    # via ``@db.model``.
    cls = type(
        model_name,
        (),
        {
            "__annotations__": {"id": int, "title": str, "body": str},
            "id": 0,
            "title": "",
            "body": "",
        },
    )
    cls = classify(
        "body", DataClassification.PII, masking=MaskingStrategy.REDACT
    )(cls)
    db.model(cls)
    return db


# ---------------------------------------------------------------------------
# create() — mutation return path redaction
# ---------------------------------------------------------------------------


async def test_create_redacts_classified_field_for_public_caller(
    test_suite, unique_model_name
):
    """create() return dict MUST redact PII body for a PUBLIC caller.

    Covers the core leak fixed by issue #490: ``create()`` used to
    echo the raw row from CreateNode, leaking classified values.
    """
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        # No clearance bound → treated as PUBLIC (most restrictive).
        returned = await db.express.create(
            unique_model_name,
            {"title": "public-title", "body": "leak-me"},
        )
        assert returned is not None
        assert returned["title"] == "public-title"
        assert returned["body"] == "[REDACTED]", (
            "PUBLIC caller MUST NOT see plaintext 'body' on create() return; "
            "would leak classified field to any downstream API echoing it."
        )
    finally:
        db.close()


async def test_create_unmasked_for_pii_clearance_caller(
    test_suite, unique_model_name
):
    """create() return dict passes through raw values for a PII caller.

    Sanity check: the fix does not over-redact — callers with
    sufficient clearance see the raw value.
    """
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        async with async_clearance_context(DataClassification.PII):
            returned = await db.express.create(
                unique_model_name,
                {"title": "pii-title", "body": "visible-to-pii"},
            )
        assert returned["body"] == "visible-to-pii"


        # The raw value WAS persisted — the fix is at return, not at write.
        # Read back at high clearance to verify.
        record_id = returned.get("id")
        assert record_id is not None
        async with async_clearance_context(DataClassification.HIGHLY_CONFIDENTIAL):
            admin_read = await db.express.read(
                unique_model_name, str(record_id), cache_ttl=0
            )
        assert admin_read is not None
        assert admin_read["body"] == "visible-to-pii"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# update() — mutation return path redaction
# ---------------------------------------------------------------------------


async def test_update_redacts_classified_field_for_public_caller(
    test_suite, unique_model_name
):
    """update() return dict MUST redact PII body for a PUBLIC caller."""
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        # Seed at PII clearance so the raw value lands in storage.
        async with async_clearance_context(DataClassification.PII):
            seeded = await db.express.create(
                unique_model_name,
                {"title": "seed", "body": "before"},
            )
        record_id = seeded["id"]

        # PUBLIC caller updates and receives the updated row.
        updated = await db.express.update(
            unique_model_name,
            str(record_id),
            {"title": "updated-title", "body": "after"},
        )
        assert isinstance(updated, dict)
        assert updated.get("body") == "[REDACTED]", (
            "PUBLIC caller MUST NOT see plaintext 'body' on update() return"
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# upsert() — mutation return path redaction
# ---------------------------------------------------------------------------


async def test_upsert_insert_branch_redacts_classified_field(
    test_suite, unique_model_name
):
    """upsert() INSERT branch return MUST redact PII body for PUBLIC."""
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        # Generate a fresh id to force the INSERT branch.
        new_id = 1001
        returned = await db.express.upsert(
            unique_model_name,
            {"id": new_id, "title": "ins", "body": "secret-ins"},
        )
        assert isinstance(returned, dict)
        assert returned.get("body") == "[REDACTED]", (
            "PUBLIC caller MUST NOT see plaintext 'body' on upsert() insert return"
        )
    finally:
        db.close()


async def test_upsert_update_branch_redacts_classified_field(
    test_suite, unique_model_name
):
    """upsert() UPDATE-on-conflict branch return MUST redact PII body."""
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        # Seed at PII clearance.
        async with async_clearance_context(DataClassification.PII):
            seeded = await db.express.create(
                unique_model_name,
                {"title": "seed", "body": "seed-body"},
            )
        record_id = seeded["id"]

        # PUBLIC caller upserts the same PK → conflict → update branch.
        returned = await db.express.upsert(
            unique_model_name,
            {"id": record_id, "title": "updated", "body": "updated-body"},
        )
        assert isinstance(returned, dict)
        assert returned.get("body") == "[REDACTED]", (
            "PUBLIC caller MUST NOT see plaintext 'body' on upsert() update return"
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# upsert_advanced() — mutation return path redaction
# ---------------------------------------------------------------------------


async def test_upsert_advanced_redacts_record_dict(test_suite, unique_model_name):
    """upsert_advanced() ``record`` field MUST be redacted for PUBLIC."""
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        result = await db.express.upsert_advanced(
            unique_model_name,
            where={"id": 2001},
            create={"id": 2001, "title": "adv", "body": "adv-secret"},
            update={"title": "adv-upd", "body": "adv-secret-upd"},
        )
        # Contract: {"created": bool, "action": str, "record": dict}
        assert isinstance(result, dict)
        if "record" in result and isinstance(result["record"], dict):
            assert result["record"].get("body") == "[REDACTED]", (
                "upsert_advanced() record.body MUST be redacted for PUBLIC caller"
            )
        # Tolerate alternative shapes (node-layer variance): if the
        # return dict itself has the row fields, body MUST still be
        # redacted.
        if "body" in result:
            assert result["body"] == "[REDACTED]", (
                "upsert_advanced() top-level body MUST be redacted for PUBLIC"
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# bulk_create() — mutation return path redaction
# ---------------------------------------------------------------------------


async def test_bulk_create_redacts_returned_records(test_suite, unique_model_name):
    """bulk_create() MUST redact 'body' on every returned row for PUBLIC.

    The BulkCreate node in the Python SDK may return one of:
      - a ``list`` of row dicts (when RETURNING is supported)
      - a summary ``dict`` with a ``records`` / ``items`` list
      - a summary ``dict`` with only counts (``inserted``, ``total``, …)

    In the first two cases, classified fields MUST be redacted for a
    low-clearance caller. The third case carries no row values so
    there is no leak surface — we verify the dict contains no
    plaintext ``body`` value anywhere. This is the negative form of
    the redaction contract: no leak, no matter the return shape.

    Separately, the read-back at PII clearance confirms the raw
    values WERE persisted — the redaction fix is at return, not at
    write.
    """
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        result = await db.express.bulk_create(
            unique_model_name,
            [
                {"title": "bulk-1", "body": "secret-1"},
                {"title": "bulk-2", "body": "secret-2"},
                {"title": "bulk-3", "body": "secret-3"},
            ],
        )

        def _assert_no_plaintext_body(obj):
            """Walk the return value and assert no ``body`` holds raw secret-*.

            Dicts at any depth with a ``body`` key MUST carry the
            redaction sentinel ``[REDACTED]`` (if they hold any
            string). This matches the rule's contract: classified
            fields MUST NOT echo plaintext.
            """
            if isinstance(obj, dict):
                if "body" in obj and isinstance(obj["body"], str):
                    assert not obj["body"].startswith("secret-"), (
                        f"bulk_create() return leaked plaintext 'body'={obj['body']!r}"
                    )
                for v in obj.values():
                    _assert_no_plaintext_body(v)
            elif isinstance(obj, list):
                for item in obj:
                    _assert_no_plaintext_body(item)

        _assert_no_plaintext_body(result)

        # When the return shape contains rows, every row MUST have body
        # explicitly redacted (not merely absent).
        records_list = None
        if isinstance(result, list):
            records_list = result
        elif isinstance(result, dict):
            records_list = (
                result.get("records")
                or result.get("items")
                or result.get("data")
            )
        if isinstance(records_list, list) and records_list:
            # Only assert when rows are actually echoed — the count-only
            # return shape is already covered by the walk above.
            for row in records_list:
                if isinstance(row, dict) and "body" in row:
                    assert row["body"] == "[REDACTED]", (
                        "bulk_create() MUST redact 'body' on every returned row"
                    )

        # Confirm writes actually persisted the raw value (the fix is at
        # return, not at write).
        async with async_clearance_context(DataClassification.PII):
            persisted = await db.express.list(unique_model_name, cache_ttl=0)
        persisted_bodies = {r.get("body") for r in persisted}
        assert {"secret-1", "secret-2", "secret-3"} <= persisted_bodies, (
            "bulk_create() must have persisted raw values under PII clearance"
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# bulk_update() — delegation-based redaction
# ---------------------------------------------------------------------------


async def test_bulk_update_redacts_via_update_delegation(
    test_suite, unique_model_name
):
    """bulk_update() MUST redact 'body' on every returned row for PUBLIC.

    bulk_update delegates per-record to ``update()``; this test pins
    the delegation contract (dataflow-classification.md MUST Rule 2).
    A refactor that replaces per-record delegation with an inline
    bulk UPDATE RETURNING without re-applying the redaction call
    would fail this test.
    """
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        async with async_clearance_context(DataClassification.PII):
            seeded = [
                await db.express.create(
                    unique_model_name,
                    {"title": f"seed-{i}", "body": f"seed-body-{i}"},
                )
                for i in range(3)
            ]
        ids = [r["id"] for r in seeded]

        updates = [
            {"id": rid, "title": f"upd-{i}", "body": f"upd-body-{i}"}
            for i, rid in enumerate(ids)
        ]
        rows = await db.express.bulk_update(unique_model_name, updates)
        assert isinstance(rows, list)
        # Accept partial success per `bulk_update`'s contract; assert
        # that EVERY returned row is redacted (zero tolerance for leaks).
        for row in rows:
            assert isinstance(row, dict)
            assert row.get("body") == "[REDACTED]", (
                "bulk_update() MUST redact 'body' on every returned row for PUBLIC"
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# bulk_upsert() — mutation return path redaction
# ---------------------------------------------------------------------------


async def test_bulk_upsert_redacts_every_returned_record(
    test_suite, unique_model_name
):
    """bulk_upsert() MUST redact 'body' on every ``records`` row for PUBLIC.

    The ``{"created", "updated", "total"}`` counts are scalar and
    exempt under dataflow-classification.md MUST Rule 4; the
    ``records`` list MUST have classified fields masked.
    """
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        result = await db.express.bulk_upsert(
            unique_model_name,
            [
                {"id": 3001, "title": "u1", "body": "up-secret-1"},
                {"id": 3002, "title": "u2", "body": "up-secret-2"},
            ],
            conflict_on=["id"],
        )
        assert isinstance(result, dict)
        assert "records" in result
        records_out = result["records"]
        # bulk_upsert may return an empty records list on some backends
        # (ON CONFLICT ... DO NOTHING without RETURNING) — in that case
        # there's nothing to redact and nothing to leak. When rows are
        # returned, every one of them MUST have body redacted.
        for row in records_out:
            assert isinstance(row, dict)
            if "body" in row:
                assert row["body"] == "[REDACTED]", (
                    "bulk_upsert() MUST redact 'body' on every returned row for PUBLIC"
                )
    finally:
        db.close()
