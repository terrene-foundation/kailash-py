"""
Comprehensive Bug FIX Verification Tests: DATAFLOW-2026-001

This file was originally created to reproduce bugs. It has been updated
to verify the fixes now that they've been implemented.

Tests verify fixes for:
- Issue 1: skip_registry parameter now emits helpful warning
- Issue 2a: DDL default value generation for list/dict types now works correctly
- Issue 2b: Generic type mapping (List[T], Dict[K,V]) now maps to JSONB/JSON
- Issue 3: Configuration validation now warns about unknown kwargs
"""

import json
import warnings
from typing import Any, Dict, List

import pytest

from dataflow import DataFlow


class TestIssue1SkipRegistryParameterFixed:
    """Issue 1: skip_registry parameter now emits a warning."""

    def test_skip_registry_emits_warning(self):
        """Verify skip_registry=True now emits a helpful UserWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            db = DataFlow(
                database_url="sqlite:///:memory:",
                auto_migrate=False,
                skip_registry=True,
            )

            # Should have a DF-CFG-001 warning
            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert (
                len(df_warnings) == 1
            ), "FIX VERIFIED: skip_registry now emits DF-CFG-001 warning"

            # Warning should suggest the correct parameter
            warning_msg = str(df_warnings[0].message)
            assert (
                "enable_model_persistence=False" in warning_msg
            ), "Warning should suggest enable_model_persistence=False"

            db.close()

    def test_skip_registry_still_captured_in_init_kwargs(self):
        """Verify skip_registry is still captured (for backwards compat analysis)."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            db = DataFlow(
                database_url="sqlite:///:memory:",
                auto_migrate=False,
                skip_registry=True,
            )

            # skip_registry should still be in _init_kwargs
            assert hasattr(db, "_init_kwargs"), "DataFlow should have _init_kwargs"
            assert "skip_registry" in db._init_kwargs

            db.close()

    def test_skip_registry_does_not_prevent_model_registration(self):
        """Verify models ARE registered even when skip_registry=True."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            db = DataFlow(
                database_url="sqlite:///:memory:",
                auto_migrate=False,
                skip_registry=True,
            )

            @db.model
            class TestUser:
                id: str
                name: str

            # Model SHOULD be registered
            assert "TestUser" in db._models, "Model should still register"
            assert len(db._models) == 1

            db.close()

    def test_skip_registry_not_in_explicit_parameters(self):
        """Verify skip_registry is NOT in __init__ signature (by design)."""
        import inspect

        sig = inspect.signature(DataFlow.__init__)
        param_names = list(sig.parameters.keys())

        assert "skip_registry" not in param_names, (
            "skip_registry should NOT be in __init__ signature - "
            "it was never implemented and now emits a warning"
        )


class TestIssue2aDDLDefaultValuesFixed:
    """Issue 2a: DDL generation for default values now works correctly."""

    @pytest.fixture
    def db(self):
        db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
        yield db
        db.close()

    def test_empty_list_default_produces_valid_sql_postgresql(self, db):
        """Empty list default [] now produces valid PostgreSQL DDL."""

        @db.model
        class TestListDefault:
            id: str
            tags: List[str] = []

        ddl = db._generate_create_table_sql("TestListDefault", "postgresql")

        # FIX VERIFIED: Should contain proper JSONB default syntax
        assert (
            "DEFAULT '[]'::jsonb" in ddl
        ), f"FIX VERIFIED: DDL contains valid JSONB default. Generated: {ddl}"
        # Should NOT contain bare DEFAULT []
        assert "DEFAULT []" not in ddl or "DEFAULT '[]'" in ddl

    def test_empty_dict_default_produces_valid_sql_postgresql(self, db):
        """Empty dict default {} now produces valid PostgreSQL DDL."""

        @db.model
        class TestDictDefault:
            id: str
            metadata: Dict[str, Any] = {}

        ddl = db._generate_create_table_sql("TestDictDefault", "postgresql")

        # FIX VERIFIED: Should contain proper JSONB default syntax
        assert (
            "DEFAULT '{}'::jsonb" in ddl
        ), f"FIX VERIFIED: DDL contains valid JSONB default. Generated: {ddl}"

    def test_empty_list_default_produces_valid_sql_mysql(self, db):
        """Empty list default [] now produces valid MySQL DDL."""

        @db.model
        class TestMySQLListDefault:
            id: str
            tags: List[str] = []

        ddl = db._generate_create_table_sql("TestMySQLListDefault", "mysql")

        # FIX VERIFIED: Should contain MySQL JSON cast syntax
        assert (
            "DEFAULT (CAST('[]' AS JSON))" in ddl
        ), f"FIX VERIFIED: DDL contains valid MySQL JSON default. Generated: {ddl}"

    def test_empty_list_default_produces_valid_sql_sqlite(self, db):
        """Empty list default [] now produces valid SQLite DDL."""

        @db.model
        class TestSQLiteListDefault:
            id: str
            tags: List[str] = []

        ddl = db._generate_create_table_sql("TestSQLiteListDefault", "sqlite")

        # FIX VERIFIED: Should contain TEXT default (SQLite stores JSON as TEXT)
        assert (
            "DEFAULT '[]'" in ddl
        ), f"FIX VERIFIED: DDL contains valid SQLite TEXT default. Generated: {ddl}"
        # Should NOT have JSONB cast (SQLite doesn't support it)
        assert "::jsonb" not in ddl


class TestIssue2bGenericTypeMappingFixed:
    """Issue 2b: Generic type mapping now works correctly."""

    @pytest.fixture
    def db(self):
        db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
        yield db
        db.close()

    def test_list_str_maps_to_jsonb_postgresql(self, db):
        """List[str] now correctly maps to JSONB in PostgreSQL."""
        sql_type = db._python_type_to_sql_type(List[str], "postgresql")
        assert (
            sql_type == "JSONB"
        ), f"FIX VERIFIED: List[str] maps to JSONB, got: {sql_type}"

    def test_dict_str_any_maps_to_jsonb_postgresql(self, db):
        """Dict[str, Any] now correctly maps to JSONB in PostgreSQL."""
        sql_type = db._python_type_to_sql_type(Dict[str, Any], "postgresql")
        assert (
            sql_type == "JSONB"
        ), f"FIX VERIFIED: Dict[str, Any] maps to JSONB, got: {sql_type}"

    def test_list_str_maps_to_json_mysql(self, db):
        """List[str] now correctly maps to JSON in MySQL."""
        sql_type = db._python_type_to_sql_type(List[str], "mysql")
        assert (
            sql_type == "JSON"
        ), f"FIX VERIFIED: List[str] maps to JSON in MySQL, got: {sql_type}"

    def test_list_str_maps_to_text_sqlite(self, db):
        """List[str] now correctly maps to TEXT in SQLite."""
        sql_type = db._python_type_to_sql_type(List[str], "sqlite")
        assert (
            sql_type == "TEXT"
        ), f"FIX VERIFIED: List[str] maps to TEXT in SQLite, got: {sql_type}"


class TestIssue3ConfigurationValidationFixed:
    """Issue 3: Configuration validation now warns about unknown kwargs."""

    def test_unknown_kwargs_emit_warning(self):
        """Unknown kwargs now emit a DF-CFG-001 warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            db = DataFlow(
                database_url="sqlite:///:memory:",
                auto_migrate=False,
                totally_unknown_param="value",
            )

            # Should have a DF-CFG-001 warning
            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert (
                len(df_warnings) == 1
            ), "FIX VERIFIED: unknown kwargs now emit DF-CFG-001 warning"

            warning_msg = str(df_warnings[0].message)
            assert "totally_unknown_param" in warning_msg
            assert "has no effect" in warning_msg

            db.close()

    def test_multiple_unknown_kwargs_single_warning(self):
        """Multiple unknown kwargs produce a single comprehensive warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            db = DataFlow(
                database_url="sqlite:///:memory:",
                auto_migrate=False,
                skip_registry=True,
                skip_migration=True,
                unknown_param=123,
            )

            # Should have exactly one DF-CFG-001 warning
            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 1

            # All unknown params should be mentioned
            warning_msg = str(df_warnings[0].message)
            assert "skip_registry" in warning_msg
            assert "skip_migration" in warning_msg
            assert "unknown_param" in warning_msg

            db.close()

    def test_known_kwargs_no_warning(self):
        """Known kwargs do not trigger warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            db = DataFlow(
                database_url="sqlite:///:memory:",
                auto_migrate=False,
                batch_size=100,
                schema_cache_enabled=True,
            )

            # Should NOT have DF-CFG-001 warnings
            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 0, "Known kwargs should not trigger warnings"

            db.close()


if __name__ == "__main__":
    # Run quick verification
    print("=" * 60)
    print("DATAFLOW-2026-001 FIX VERIFICATION")
    print("=" * 60)

    print("\n--- Issue 1: skip_registry (FIXED) ---")
    test1 = TestIssue1SkipRegistryParameterFixed()
    test1.test_skip_registry_emits_warning()
    print("  [PASS] skip_registry now emits DF-CFG-001 warning")
    test1.test_skip_registry_does_not_prevent_model_registration()
    print("  [PASS] skip_registry does NOT prevent model registration")
    test1.test_skip_registry_not_in_explicit_parameters()
    print("  [PASS] skip_registry is NOT in __init__ signature")

    print("\n--- Issue 2a: DDL Default Values (FIXED) ---")
    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
    test2 = TestIssue2aDDLDefaultValuesFixed()
    test2.test_empty_list_default_produces_valid_sql_postgresql(db)
    print("  [PASS] List default produces valid PostgreSQL DDL")
    test2.test_empty_dict_default_produces_valid_sql_postgresql(db)
    print("  [PASS] Dict default produces valid PostgreSQL DDL")
    test2.test_empty_list_default_produces_valid_sql_mysql(db)
    print("  [PASS] List default produces valid MySQL DDL")
    test2.test_empty_list_default_produces_valid_sql_sqlite(db)
    print("  [PASS] List default produces valid SQLite DDL")
    db.close()

    print("\n--- Issue 2b: Generic Type Mapping (FIXED) ---")
    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
    test2b = TestIssue2bGenericTypeMappingFixed()
    test2b.test_list_str_maps_to_jsonb_postgresql(db)
    print("  [PASS] List[str] maps to JSONB in PostgreSQL")
    test2b.test_dict_str_any_maps_to_jsonb_postgresql(db)
    print("  [PASS] Dict[str, Any] maps to JSONB in PostgreSQL")
    test2b.test_list_str_maps_to_json_mysql(db)
    print("  [PASS] List[str] maps to JSON in MySQL")
    test2b.test_list_str_maps_to_text_sqlite(db)
    print("  [PASS] List[str] maps to TEXT in SQLite")
    db.close()

    print("\n--- Issue 3: Unknown Kwargs Validation (FIXED) ---")
    test3 = TestIssue3ConfigurationValidationFixed()
    test3.test_unknown_kwargs_emit_warning()
    print("  [PASS] Unknown kwargs emit DF-CFG-001 warning")
    test3.test_multiple_unknown_kwargs_single_warning()
    print("  [PASS] Multiple unknown kwargs produce single comprehensive warning")
    test3.test_known_kwargs_no_warning()
    print("  [PASS] Known kwargs do not trigger warnings")

    print("\n" + "=" * 60)
    print("ALL DATAFLOW-2026-001 FIXES VERIFIED!")
    print("=" * 60)
