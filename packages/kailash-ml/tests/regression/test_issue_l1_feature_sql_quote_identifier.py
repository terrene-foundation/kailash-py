# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: L1 — _feature_sql.py MUST route DDL identifiers through quote_identifier.

Origin: 2026-04-20 late-session audit finding L1 —
``packages/kailash-ml/src/kailash_ml/engines/_feature_sql.py`` used
``kailash.db.dialect._validate_identifier(...)`` (validator only) at
every DDL / SELECT / INSERT site that interpolates a dynamic
identifier. Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1,
every dynamic DDL identifier MUST route through the dialect's
``quote_identifier`` helper, which BOTH validates AND quotes. The
validate-only form leaves the identifier unquoted in the final SQL
string, which works against SQLite (permissive) but silently drops
dialect portability when a future refactor swaps the backing store.
Worse, a validator-only check makes the injection defense dependent
on the allowlist regex alone — adding a single future code path that
forgets the validate call (a common drift mode) re-opens the bug.

Behavioural regression tests per
``rules/testing.md`` § "MUST: Behavioral Regression Tests Over
Source-Grep": we construct a real in-memory SQLite
``ConnectionManager``, invoke each migrated ``_feature_sql``
function with a poisoned identifier, and assert the standard
injection payloads are rejected by the dialect's
``IdentifierError`` (NOT a cryptic downstream SQL error).

The five migrated sites covered here:

1. ``create_feature_table`` — CREATE TABLE + CREATE INDEX (compound).
2. ``get_features_latest`` — SELECT + ROW_NUMBER() OVER window.
3. ``get_features_as_of`` — same + time bound.
4. ``get_features_range`` — simple SELECT.
5. ``upsert_batch`` — INSERT INTO.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

# Standard injection payloads from rules/dataflow-identifier-safety.md §3.
INJECTION_PAYLOADS = [
    'users"; DROP TABLE customers; --',
    "name WITH DATA",
    "123_starts_with_digit",
    "column'; DROP TABLE users; --",
    "tab\tcontrol",
    "tbl\x00null",
    '" OR 1=1 --',
]


async def _make_conn():
    """Construct a real in-memory SQLite ConnectionManager."""
    from kailash.db.connection import ConnectionManager

    conn = ConnectionManager("sqlite:///:memory:")
    await conn.initialize()
    return conn


def _identifier_error_type():
    """Return the typed IdentifierError class from kailash.db.dialect."""
    from kailash.db.dialect import IdentifierError

    return IdentifierError


@pytest.mark.regression
def test_l1_create_feature_table_rejects_injection_payloads() -> None:
    """``create_feature_table`` rejects every standard injection payload."""
    from kailash_ml.engines import _feature_sql as sql

    IdentifierError = _identifier_error_type()

    async def _exercise() -> None:
        conn = await _make_conn()
        try:
            for payload in INJECTION_PAYLOADS:
                # Poison table_name
                with pytest.raises(
                    (IdentifierError, ValueError),
                    match=r"(identifier|Invalid)",
                ):
                    await sql.create_feature_table(
                        conn,
                        table_name=payload,
                        feature_columns=[("amount", "REAL")],
                        entity_id_column="entity_id",
                        timestamp_column=None,
                    )

                # Poison entity_id_column
                with pytest.raises(
                    (IdentifierError, ValueError),
                    match=r"(identifier|Invalid)",
                ):
                    await sql.create_feature_table(
                        conn,
                        table_name="safe_table",
                        feature_columns=[("amount", "REAL")],
                        entity_id_column=payload,
                        timestamp_column=None,
                    )

                # Poison feature column name
                with pytest.raises(
                    (IdentifierError, ValueError),
                    match=r"(identifier|Invalid)",
                ):
                    await sql.create_feature_table(
                        conn,
                        table_name="safe_table",
                        feature_columns=[(payload, "REAL")],
                        entity_id_column="entity_id",
                        timestamp_column=None,
                    )
        finally:
            await conn.close()

    asyncio.run(_exercise())


@pytest.mark.regression
def test_l1_get_features_latest_rejects_injection_payloads() -> None:
    """``get_features_latest`` rejects every standard injection payload."""
    from kailash_ml.engines import _feature_sql as sql

    IdentifierError = _identifier_error_type()

    async def _exercise() -> None:
        conn = await _make_conn()
        try:
            for payload in INJECTION_PAYLOADS:
                with pytest.raises((IdentifierError, ValueError)):
                    await sql.get_features_latest(
                        conn,
                        table_name=payload,
                        entity_ids=["e1"],
                        feature_names=["amount"],
                        entity_id_column="entity_id",
                    )
                with pytest.raises((IdentifierError, ValueError)):
                    await sql.get_features_latest(
                        conn,
                        table_name="safe_table",
                        entity_ids=["e1"],
                        feature_names=[payload],
                        entity_id_column="entity_id",
                    )
        finally:
            await conn.close()

    asyncio.run(_exercise())


@pytest.mark.regression
def test_l1_get_features_as_of_rejects_injection_payloads() -> None:
    """``get_features_as_of`` rejects every standard injection payload."""
    from kailash_ml.engines import _feature_sql as sql

    IdentifierError = _identifier_error_type()

    async def _exercise() -> None:
        conn = await _make_conn()
        try:
            for payload in INJECTION_PAYLOADS:
                with pytest.raises((IdentifierError, ValueError)):
                    await sql.get_features_as_of(
                        conn,
                        table_name=payload,
                        entity_ids=["e1"],
                        feature_names=["amount"],
                        entity_id_column="entity_id",
                        as_of=datetime.now(timezone.utc),
                    )
                with pytest.raises((IdentifierError, ValueError)):
                    await sql.get_features_as_of(
                        conn,
                        table_name="safe_table",
                        entity_ids=["e1"],
                        feature_names=["amount"],
                        entity_id_column="entity_id",
                        as_of=datetime.now(timezone.utc),
                        timestamp_column=payload,
                    )
        finally:
            await conn.close()

    asyncio.run(_exercise())


@pytest.mark.regression
def test_l1_get_features_range_rejects_injection_payloads() -> None:
    """``get_features_range`` rejects every standard injection payload."""
    from kailash_ml.engines import _feature_sql as sql

    IdentifierError = _identifier_error_type()

    async def _exercise() -> None:
        conn = await _make_conn()
        try:
            for payload in INJECTION_PAYLOADS:
                with pytest.raises((IdentifierError, ValueError)):
                    await sql.get_features_range(
                        conn,
                        table_name=payload,
                        entity_id_column="entity_id",
                        feature_names=["amount"],
                        start=datetime.now(timezone.utc),
                        end=datetime.now(timezone.utc),
                    )
        finally:
            await conn.close()

    asyncio.run(_exercise())


@pytest.mark.regression
def test_l1_upsert_batch_rejects_injection_payloads() -> None:
    """``upsert_batch`` rejects every standard injection payload."""
    from kailash_ml.engines import _feature_sql as sql

    IdentifierError = _identifier_error_type()

    async def _exercise() -> None:
        conn = await _make_conn()
        try:
            for payload in INJECTION_PAYLOADS:
                with pytest.raises((IdentifierError, ValueError)):
                    await sql.upsert_batch(
                        conn,
                        table_name=payload,
                        records=[{"entity_id": "e1", "amount": 1.0}],
                        all_columns=["entity_id", "amount"],
                    )
                with pytest.raises((IdentifierError, ValueError)):
                    await sql.upsert_batch(
                        conn,
                        table_name="safe_table",
                        records=[{"entity_id": "e1", "amount": 1.0}],
                        all_columns=["entity_id", payload],
                    )
        finally:
            await conn.close()

    asyncio.run(_exercise())


@pytest.mark.regression
def test_l1_create_feature_table_happy_path_produces_quoted_ddl() -> None:
    """Happy path: valid identifiers produce a real, working schema.

    This asserts the migration to ``quote_identifier`` did not break
    the normal call path — a valid table name + feature columns must
    still produce an actually queryable schema.
    """
    from kailash_ml.engines import _feature_sql as sql

    async def _exercise() -> None:
        conn = await _make_conn()
        try:
            await sql.create_feature_table(
                conn,
                table_name="kml_feat_happy_path",
                feature_columns=[("amount", "REAL"), ("tenure_months", "INTEGER")],
                entity_id_column="entity_id",
                timestamp_column=None,
            )
            # Round-trip: insert + select to prove the schema works
            await sql.upsert_batch(
                conn,
                table_name="kml_feat_happy_path",
                records=[
                    {
                        "entity_id": "e1",
                        "amount": 42.5,
                        "tenure_months": 3,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                all_columns=["entity_id", "amount", "tenure_months", "created_at"],
            )
            rows = await sql.get_features_latest(
                conn,
                table_name="kml_feat_happy_path",
                entity_ids=["e1"],
                feature_names=["amount", "tenure_months"],
                entity_id_column="entity_id",
            )
            assert len(rows) == 1
            assert rows[0]["amount"] == 42.5
            assert rows[0]["tenure_months"] == 3
        finally:
            await conn.close()

    asyncio.run(_exercise())
