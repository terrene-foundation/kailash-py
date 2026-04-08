# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for Phase 5.10 — classification redaction wiring.

Before this phase, ``@classify("email", DataClassification.PII, ...,
MaskingStrategy.REDACT)`` on a DataFlow model attached metadata but
nothing in the query path consulted it — every read returned the raw
field value regardless of the caller's clearance.

These tests lock in the contract that after Phase 5.10:

1. DataFlow always exposes a ``ClassificationPolicy`` via
   ``db.classification_policy``, and ``@db.model`` auto-registers any
   ``@classify`` metadata into it.
2. The masking helpers ``caller_can_access`` and
   ``apply_masking_strategy`` implement the canonical clearance order
   and every masking strategy (NONE, REDACT, HASH, LAST_FOUR, ENCRYPT).
3. Express ``read`` / ``list`` / ``find_one`` consult the policy on
   every query and mask classified fields that the caller's clearance
   (bound via ``clearance_context``) cannot access.
4. Callers with sufficient clearance see the raw values. Callers with
   no bound clearance are treated as ``PUBLIC`` and see masked values
   for every classified field.
5. Models with no ``@classify`` metadata pay zero overhead and return
   unchanged data.
"""

import hashlib
import os
import tempfile
import uuid

import pytest

from dataflow import DataFlow
from dataflow.classification import (
    DataClassification,
    MaskingStrategy,
    RetentionPolicy,
    classify,
)
from dataflow.classification.policy import ClassificationPolicy
from dataflow.core.agent_context import async_clearance_context, clearance_context

pytestmark = pytest.mark.regression


@pytest.fixture
def sqlite_file_url():
    """Yield a file-backed SQLite URL scoped to a single test."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"tf_{uuid.uuid4().hex}.db")
        yield f"sqlite:///{path}"


# ---------------------------------------------------------------------------
# 1. Pure masking helpers — no DataFlow instance needed
# ---------------------------------------------------------------------------


def test_caller_can_access_respects_order():
    cc = ClassificationPolicy.caller_can_access
    # PUBLIC caller: only PUBLIC fields.
    assert cc(DataClassification.PUBLIC, DataClassification.PUBLIC) is True
    assert cc(DataClassification.INTERNAL, DataClassification.PUBLIC) is False
    assert cc(DataClassification.PII, DataClassification.PUBLIC) is False

    # PII caller: PUBLIC..PII ok, GDPR/HIGHLY_CONFIDENTIAL blocked.
    assert cc(DataClassification.PUBLIC, DataClassification.PII) is True
    assert cc(DataClassification.INTERNAL, DataClassification.PII) is True
    assert cc(DataClassification.SENSITIVE, DataClassification.PII) is True
    assert cc(DataClassification.PII, DataClassification.PII) is True
    assert cc(DataClassification.GDPR, DataClassification.PII) is False
    assert cc(DataClassification.HIGHLY_CONFIDENTIAL, DataClassification.PII) is False

    # HIGHLY_CONFIDENTIAL caller: everything.
    for level in DataClassification:
        assert cc(level, DataClassification.HIGHLY_CONFIDENTIAL) is True


def test_apply_masking_strategy_none():
    assert (
        ClassificationPolicy.apply_masking_strategy("plain", MaskingStrategy.NONE)
        == "plain"
    )


def test_apply_masking_strategy_redact():
    assert (
        ClassificationPolicy.apply_masking_strategy("secret", MaskingStrategy.REDACT)
        == "[REDACTED]"
    )


def test_apply_masking_strategy_encrypt():
    assert (
        ClassificationPolicy.apply_masking_strategy("secret", MaskingStrategy.ENCRYPT)
        == "[ENCRYPTED]"
    )


def test_apply_masking_strategy_hash_is_sha256():
    got = ClassificationPolicy.apply_masking_strategy(
        "alice@example.com", MaskingStrategy.HASH
    )
    expected = hashlib.sha256(b"alice@example.com").hexdigest()
    assert got == expected


def test_apply_masking_strategy_last_four_long():
    assert (
        ClassificationPolicy.apply_masking_strategy(
            "4111111111111234", MaskingStrategy.LAST_FOUR
        )
        == "************1234"
    )


def test_apply_masking_strategy_last_four_short():
    # All characters masked when value is <= 4 chars.
    assert (
        ClassificationPolicy.apply_masking_strategy("abc", MaskingStrategy.LAST_FOUR)
        == "***"
    )


def test_apply_masking_strategy_none_on_none_value():
    # Null values never get redacted — masking is a no-op on None.
    assert (
        ClassificationPolicy.apply_masking_strategy(None, MaskingStrategy.REDACT)
        is None
    )


# ---------------------------------------------------------------------------
# 2. ClassificationPolicy.apply_masking_to_record
# ---------------------------------------------------------------------------


def test_apply_masking_to_record_masks_fields_above_clearance():
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    @classify(
        "ssn", DataClassification.HIGHLY_CONFIDENTIAL, masking=MaskingStrategy.HASH
    )
    class _User:
        name: str = ""
        email: str = ""
        ssn: str = ""

    policy = ClassificationPolicy()
    policy.register_model(_User)

    record = {
        "name": "Alice",
        "email": "alice@x.io",
        "ssn": "123-45-6789",
    }

    # PUBLIC caller cannot see email or ssn.
    masked_public = policy.apply_masking_to_record(
        "_User", record, DataClassification.PUBLIC
    )
    assert masked_public["name"] == "Alice"
    assert masked_public["email"] == "[REDACTED]"
    assert masked_public["ssn"] == hashlib.sha256(b"123-45-6789").hexdigest()

    # PII caller can see email but not ssn.
    masked_pii = policy.apply_masking_to_record("_User", record, DataClassification.PII)
    assert masked_pii["email"] == "alice@x.io"
    assert masked_pii["ssn"] == hashlib.sha256(b"123-45-6789").hexdigest()

    # HIGHLY_CONFIDENTIAL caller sees everything.
    masked_hc = policy.apply_masking_to_record(
        "_User", record, DataClassification.HIGHLY_CONFIDENTIAL
    )
    assert masked_hc == record


def test_apply_masking_to_record_treats_none_clearance_as_public():
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _User:
        email: str = ""

    policy = ClassificationPolicy()
    policy.register_model(_User)
    masked = policy.apply_masking_to_record("_User", {"email": "alice@x.io"}, None)
    assert masked["email"] == "[REDACTED]"


def test_apply_masking_to_record_noop_on_unclassified_model():
    policy = ClassificationPolicy()
    record = {"name": "Alice"}
    # No registration → no classifications → unchanged.
    assert (
        policy.apply_masking_to_record("Nonexistent", record, DataClassification.PUBLIC)
        is record
    )


def test_apply_masking_to_rows_returns_per_row_masks():
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _User:
        email: str = ""

    policy = ClassificationPolicy()
    policy.register_model(_User)

    rows = [{"email": "a@x.io"}, {"email": "b@x.io"}]
    masked = policy.apply_masking_to_rows("_User", rows, DataClassification.PUBLIC)
    assert masked == [{"email": "[REDACTED]"}, {"email": "[REDACTED]"}]


# ---------------------------------------------------------------------------
# 3. DataFlow integration — auto-registration
# ---------------------------------------------------------------------------


def test_dataflow_has_classification_policy_by_default():
    db = DataFlow("sqlite:///:memory:")
    try:
        assert db.classification_policy is not None
        assert isinstance(db.classification_policy, ClassificationPolicy)
    finally:
        db.close()


def test_db_model_auto_registers_classify_metadata():
    db = DataFlow("sqlite:///:memory:")
    try:

        @db.model
        @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
        class _Person:
            id: int
            name: str
            email: str

        policy = db.classification_policy
        fields = policy.get_model_fields("_Person")
        assert "email" in fields
        assert fields["email"].classification == DataClassification.PII
        assert fields["email"].masking == MaskingStrategy.REDACT
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Express read/list/find_one apply masking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_express_read_masks_classified_fields_for_public_caller(
    sqlite_file_url,
):
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _User:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        await db.express.create(
            "_User", {"id": 1, "name": "Alice", "email": "alice@x.io"}
        )
        got = await db.express.read("_User", "1", cache_ttl=0)
        assert got is not None
        assert got["name"] == "Alice"
        assert got["email"] == "[REDACTED]"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_read_unmasks_for_pii_clearance(sqlite_file_url):
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _User:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        await db.express.create(
            "_User", {"id": 1, "name": "Alice", "email": "alice@x.io"}
        )
        async with async_clearance_context(DataClassification.PII):
            got = await db.express.read("_User", "1", cache_ttl=0)
        assert got is not None
        assert got["email"] == "alice@x.io"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_list_masks_each_row(sqlite_file_url):
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _User:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        await db.express.create(
            "_User", {"id": 1, "name": "Alice", "email": "alice@x.io"}
        )
        await db.express.create("_User", {"id": 2, "name": "Bob", "email": "bob@x.io"})
        rows = await db.express.list("_User", cache_ttl=0)
        assert len(rows) == 2
        for row in rows:
            assert row["email"] == "[REDACTED]"
        names = {r["name"] for r in rows}
        assert names == {"Alice", "Bob"}
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_find_one_masks_classified_fields(sqlite_file_url):
    db = DataFlow(sqlite_file_url)

    @db.model
    @classify("email", DataClassification.PII, masking=MaskingStrategy.REDACT)
    class _User:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        await db.express.create(
            "_User", {"id": 1, "name": "Alice", "email": "alice@x.io"}
        )
        got = await db.express.find_one("_User", filter={"name": "Alice"}, cache_ttl=0)
        assert got is not None
        assert got["email"] == "[REDACTED]"

        async with async_clearance_context(DataClassification.PII):
            got2 = await db.express.find_one(
                "_User", filter={"name": "Alice"}, cache_ttl=0
            )
        assert got2 is not None
        assert got2["email"] == "alice@x.io"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_list_unmasked_without_classify_metadata(sqlite_file_url):
    """Models without @classify decorators pay zero overhead."""
    db = DataFlow(sqlite_file_url)

    @db.model
    class _Plain:
        id: int
        name: str

    try:
        await db.initialize()
        await db.express.create("_Plain", {"id": 1, "name": "Alice"})
        rows = await db.express.list("_Plain", cache_ttl=0)
        assert rows == [{"id": 1, "name": "Alice"}] or (
            len(rows) == 1 and rows[0]["name"] == "Alice"
        )
    finally:
        db.close()
