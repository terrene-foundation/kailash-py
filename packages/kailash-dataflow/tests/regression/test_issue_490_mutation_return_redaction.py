# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #490 — DataFlowExpress mutation-return redaction.

Before the fix, ``create()``, ``update()``, ``upsert()``,
``upsert_advanced()``, and ``bulk_upsert()`` echoed the mutated row
back to the caller as a plain ``row_to_dict`` — leaking classified
field values (PII / HIGHLY_CONFIDENTIAL) regardless of caller
clearance. The read path (``read()`` / ``list()`` / ``find_one()``)
already applied masking; the leak was in the mutation return paths.

These regression tests pin the contract from
``rules/dataflow-classification.md`` MUST Rule 1: every public
mutation path that echoes a row back to the caller MUST apply the
same read-path redaction policy. They use SQLite (tempfile) for
speed so they run in the default pytest collection without
dependency on docker/postgres.

The matching Tier 2 tests against real PostgreSQL live in
``tests/integration/security/test_classification_mutation_return.py``
— this file is the always-on guardrail; the Tier 2 file exercises
the dialect-specific code paths (``$N`` placeholders, ``RETURNING``,
``ON CONFLICT``).

Cross-SDK reference: kailash-rs commit ``2e9dbf94`` closed the same
bug in Rust (``crates/kailash-dataflow/tests/hardening_292_295_296_299.rs``
§ ``gh-coc-claude-rs#51 item 3e``). EATP D6: matching semantics across
SDKs, independent implementations.
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from dataflow import DataFlow
from dataflow.classification import (
    DataClassification,
    MaskingStrategy,
    classify,
)
from dataflow.core.agent_context import async_clearance_context

pytestmark = pytest.mark.regression


@pytest.fixture
def sqlite_file_url():
    """Yield a file-backed SQLite URL scoped to a single test."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"issue_490_{uuid.uuid4().hex}.db")
        yield f"sqlite:///{path}"


@pytest.mark.asyncio
async def test_issue_490_create_redacts_classified_field(sqlite_file_url):
    """Regression #490: create() return MUST redact PII for PUBLIC caller.

    Reproduces the pre-fix leak — before the fix, ``create()``
    returned the raw row dict from CreateNode verbatim. After the fix,
    ``create()`` routes the result through
    ``_apply_classification_mask_record`` before returning.
    """
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _Person:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        # No clearance bound → treated as PUBLIC (most restrictive).
        returned = await db.express.create(
            "_Person", {"id": 1, "name": "Alice", "email": "alice@x.io"}
        )
        assert returned["email"] == "[REDACTED]", (
            "Regression #490: create() MUST NOT echo plaintext classified fields"
        )
        assert returned["name"] == "Alice", "non-classified field passes through"

        # Admin read confirms raw value WAS persisted (fix is at return, not write).
        async with async_clearance_context(DataClassification.HIGHLY_CONFIDENTIAL):
            admin_read = await db.express.read("_Person", "1", cache_ttl=0)
        assert admin_read is not None
        assert admin_read["email"] == "alice@x.io", (
            "Regression #490: write path is unaffected — raw value persisted"
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_issue_490_update_redacts_classified_field(sqlite_file_url):
    """Regression #490: update() return MUST redact PII for PUBLIC caller."""
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _Person:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        async with async_clearance_context(DataClassification.PII):
            await db.express.create(
                "_Person", {"id": 1, "name": "Alice", "email": "alice@x.io"}
            )

        updated = await db.express.update(
            "_Person", "1", {"name": "Alice2", "email": "new@x.io"}
        )
        assert isinstance(updated, dict)
        assert updated.get("email") == "[REDACTED]", (
            "Regression #490: update() MUST NOT echo plaintext classified fields"
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_issue_490_upsert_insert_redacts_classified_field(sqlite_file_url):
    """Regression #490: upsert() INSERT branch MUST redact PII for PUBLIC."""
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _Person:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        returned = await db.express.upsert(
            "_Person", {"id": 1, "name": "Alice", "email": "secret@x.io"}
        )
        assert isinstance(returned, dict)
        assert returned.get("email") == "[REDACTED]", (
            "Regression #490: upsert() INSERT MUST NOT echo plaintext classified fields"
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_issue_490_upsert_update_redacts_classified_field(sqlite_file_url):
    """Regression #490: upsert() UPDATE-on-conflict branch MUST redact PII."""
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _Person:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        async with async_clearance_context(DataClassification.PII):
            await db.express.create(
                "_Person", {"id": 1, "name": "Alice", "email": "seed@x.io"}
            )

        # PUBLIC caller upserts same PK → conflict branch
        returned = await db.express.upsert(
            "_Person", {"id": 1, "name": "Alice2", "email": "updated@x.io"}
        )
        assert isinstance(returned, dict)
        assert returned.get("email") == "[REDACTED]", (
            "Regression #490: upsert() UPDATE MUST NOT echo plaintext classified fields"
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_issue_490_upsert_advanced_redacts_record(sqlite_file_url):
    """Regression #490: upsert_advanced().record MUST redact PII for PUBLIC."""
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _Person:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        result = await db.express.upsert_advanced(
            "_Person",
            where={"id": 1},
            create={"id": 1, "name": "Alice", "email": "secret@x.io"},
            update={"name": "Alice2", "email": "new@x.io"},
        )
        assert isinstance(result, dict)
        # Contract is {"created", "action", "record"} — if "record" present
        # and it carries email, it MUST be redacted.
        if "record" in result and isinstance(result["record"], dict):
            rec = result["record"]
            if "email" in rec:
                assert rec["email"] == "[REDACTED]", (
                    "Regression #490: upsert_advanced().record MUST redact PII"
                )
        # Fallback: if top-level dict has email, it MUST also be redacted.
        if "email" in result:
            assert result["email"] == "[REDACTED]", (
                "Regression #490: upsert_advanced() top-level MUST redact PII"
            )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_issue_490_bulk_upsert_redacts_records(sqlite_file_url):
    """Regression #490: bulk_upsert().records MUST redact PII for PUBLIC."""
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _Person:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        result = await db.express.bulk_upsert(
            "_Person",
            [
                {"id": 1, "name": "Alice", "email": "a@x.io"},
                {"id": 2, "name": "Bob", "email": "b@x.io"},
            ],
            conflict_on=["id"],
        )
        assert isinstance(result, dict)
        # "created", "updated", "total" are scalar counts — exempt.
        # "records" MUST have classified fields masked when non-empty.
        for row in result.get("records", []):
            if isinstance(row, dict) and "email" in row:
                assert row["email"] == "[REDACTED]", (
                    "Regression #490: bulk_upsert().records MUST redact PII"
                )
    finally:
        db.close()
