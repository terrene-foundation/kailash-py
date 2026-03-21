# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for trust-plane exception hierarchy."""

import pytest

from kailash.trust.plane.exceptions import (
    RecordNotFoundError,
    SchemaMigrationError,
    SchemaTooNewError,
    TrustPlaneError,
    TrustPlaneStoreError,
)


class TestExceptionHierarchy:
    """Verify the exception inheritance chain."""

    def test_store_error_is_trustplane_error(self) -> None:
        assert issubclass(TrustPlaneStoreError, TrustPlaneError)

    def test_record_not_found_is_store_error(self) -> None:
        assert issubclass(RecordNotFoundError, TrustPlaneStoreError)

    def test_schema_too_new_is_store_error(self) -> None:
        assert issubclass(SchemaTooNewError, TrustPlaneStoreError)

    def test_schema_migration_is_store_error(self) -> None:
        assert issubclass(SchemaMigrationError, TrustPlaneStoreError)

    def test_catch_all_with_trustplane_error(self) -> None:
        """All exceptions can be caught with except TrustPlaneError."""
        for exc_cls in (
            TrustPlaneStoreError,
            RecordNotFoundError,
            SchemaTooNewError,
            SchemaMigrationError,
        ):
            with pytest.raises(TrustPlaneError):
                raise exc_cls.__new__(exc_cls)


class TestRecordNotFoundError:
    def test_message(self) -> None:
        exc = RecordNotFoundError("DecisionRecord", "dec-123")
        assert str(exc) == "DecisionRecord not found: dec-123"

    def test_attributes(self) -> None:
        exc = RecordNotFoundError("HoldRecord", "hold-abc")
        assert exc.record_type == "HoldRecord"
        assert exc.record_id == "hold-abc"


class TestSchemaTooNewError:
    def test_message(self) -> None:
        exc = SchemaTooNewError(db_version=5, current_version=3)
        assert "5" in str(exc)
        assert "3" in str(exc)
        assert "Upgrade trust-plane" in str(exc)

    def test_attributes(self) -> None:
        exc = SchemaTooNewError(db_version=10, current_version=2)
        assert exc.db_version == 10
        assert exc.current_version == 2


class TestSchemaMigrationError:
    def test_message(self) -> None:
        exc = SchemaMigrationError(target_version=3, reason="column already exists")
        assert "3" in str(exc)
        assert "column already exists" in str(exc)

    def test_attributes(self) -> None:
        exc = SchemaMigrationError(target_version=7, reason="timeout")
        assert exc.target_version == 7
        assert exc.reason == "timeout"
