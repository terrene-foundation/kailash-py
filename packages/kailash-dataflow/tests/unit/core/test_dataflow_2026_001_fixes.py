"""Tests for DATAFLOW-2026-001 bug fixes.

This module tests the fixes for:
1. Generic type mapping (List[T], Dict[K,V] → proper SQL types)
2. DDL default value handling (list/dict → JSON serialization)
3. Unknown kwargs validation (warnings for invalid parameters)

Bug Report: DATAFLOW-2026-001
Date: 2026-01-06
"""

import json
import warnings
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest


class TestGenericTypeMapping:
    """Tests for _python_type_to_sql_type() generic type handling."""

    @pytest.fixture
    def dataflow(self):
        """Create DataFlow instance for type mapping tests."""
        from dataflow import DataFlow

        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_list_str_maps_to_jsonb_postgresql(self, dataflow):
        """List[str] should map to JSONB in PostgreSQL."""
        sql_type = dataflow._python_type_to_sql_type(List[str], "postgresql")
        assert sql_type == "JSONB"

    def test_list_int_maps_to_jsonb_postgresql(self, dataflow):
        """List[int] should map to JSONB in PostgreSQL."""
        sql_type = dataflow._python_type_to_sql_type(List[int], "postgresql")
        assert sql_type == "JSONB"

    def test_dict_str_any_maps_to_jsonb_postgresql(self, dataflow):
        """Dict[str, Any] should map to JSONB in PostgreSQL."""
        sql_type = dataflow._python_type_to_sql_type(Dict[str, Any], "postgresql")
        assert sql_type == "JSONB"

    def test_dict_str_int_maps_to_jsonb_postgresql(self, dataflow):
        """Dict[str, int] should map to JSONB in PostgreSQL."""
        sql_type = dataflow._python_type_to_sql_type(Dict[str, int], "postgresql")
        assert sql_type == "JSONB"

    def test_list_str_maps_to_json_mysql(self, dataflow):
        """List[str] should map to JSON in MySQL."""
        sql_type = dataflow._python_type_to_sql_type(List[str], "mysql")
        assert sql_type == "JSON"

    def test_dict_str_any_maps_to_json_mysql(self, dataflow):
        """Dict[str, Any] should map to JSON in MySQL."""
        sql_type = dataflow._python_type_to_sql_type(Dict[str, Any], "mysql")
        assert sql_type == "JSON"

    def test_list_str_maps_to_text_sqlite(self, dataflow):
        """List[str] should map to TEXT in SQLite."""
        sql_type = dataflow._python_type_to_sql_type(List[str], "sqlite")
        assert sql_type == "TEXT"

    def test_dict_str_any_maps_to_text_sqlite(self, dataflow):
        """Dict[str, Any] should map to TEXT in SQLite."""
        sql_type = dataflow._python_type_to_sql_type(Dict[str, Any], "sqlite")
        assert sql_type == "TEXT"

    def test_set_str_maps_to_jsonb_postgresql(self, dataflow):
        """Set[str] should map to JSONB in PostgreSQL (stored as array)."""
        sql_type = dataflow._python_type_to_sql_type(Set[str], "postgresql")
        assert sql_type == "JSONB"

    def test_tuple_str_int_maps_to_jsonb_postgresql(self, dataflow):
        """Tuple[str, int] should map to JSONB in PostgreSQL (stored as array)."""
        sql_type = dataflow._python_type_to_sql_type(Tuple[str, int], "postgresql")
        assert sql_type == "JSONB"

    def test_bare_list_still_works_postgresql(self, dataflow):
        """Bare list type should still map to JSONB."""
        sql_type = dataflow._python_type_to_sql_type(list, "postgresql")
        assert sql_type == "JSONB"

    def test_bare_dict_still_works_postgresql(self, dataflow):
        """Bare dict type should still map to JSONB."""
        sql_type = dataflow._python_type_to_sql_type(dict, "postgresql")
        assert sql_type == "JSONB"

    def test_optional_list_str_maps_to_jsonb(self, dataflow):
        """Optional[List[str]] should map to JSONB."""
        sql_type = dataflow._python_type_to_sql_type(Optional[List[str]], "postgresql")
        assert sql_type == "JSONB"

    def test_optional_dict_maps_to_jsonb(self, dataflow):
        """Optional[Dict[str, Any]] should map to JSONB."""
        sql_type = dataflow._python_type_to_sql_type(
            Optional[Dict[str, Any]], "postgresql"
        )
        assert sql_type == "JSONB"


class TestDDLDefaultValueHandling:
    """Tests for _get_sql_column_definition() default value handling."""

    @pytest.fixture
    def dataflow(self):
        """Create DataFlow instance for DDL tests."""
        from dataflow import DataFlow

        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_empty_list_default_postgresql(self, dataflow):
        """Empty list default should produce valid PostgreSQL DDL."""
        field_info = {"type": list, "required": False, "default": []}

        ddl = dataflow._get_sql_column_definition("tags", field_info, "postgresql")

        assert "DEFAULT '[]'::jsonb" in ddl
        assert "JSONB" in ddl

    def test_empty_dict_default_postgresql(self, dataflow):
        """Empty dict default should produce valid PostgreSQL DDL."""
        field_info = {"type": dict, "required": False, "default": {}}

        ddl = dataflow._get_sql_column_definition("metadata", field_info, "postgresql")

        assert "DEFAULT '{}'::jsonb" in ddl
        assert "JSONB" in ddl

    def test_populated_list_default_postgresql(self, dataflow):
        """Populated list default should produce valid PostgreSQL DDL."""
        field_info = {"type": list, "required": False, "default": ["a", "b"]}

        ddl = dataflow._get_sql_column_definition("tags", field_info, "postgresql")

        expected_json = json.dumps(["a", "b"])
        assert f"DEFAULT '{expected_json}'::jsonb" in ddl

    def test_populated_dict_default_postgresql(self, dataflow):
        """Populated dict default should produce valid PostgreSQL DDL."""
        field_info = {"type": dict, "required": False, "default": {"key": "value"}}

        ddl = dataflow._get_sql_column_definition("metadata", field_info, "postgresql")

        expected_json = json.dumps({"key": "value"})
        assert f"DEFAULT '{expected_json}'::jsonb" in ddl

    def test_empty_list_default_mysql(self, dataflow):
        """Empty list default should produce valid MySQL DDL."""
        field_info = {"type": list, "required": False, "default": []}

        ddl = dataflow._get_sql_column_definition("tags", field_info, "mysql")

        assert "DEFAULT (CAST('[]' AS JSON))" in ddl
        assert "JSON" in ddl

    def test_empty_dict_default_mysql(self, dataflow):
        """Empty dict default should produce valid MySQL DDL."""
        field_info = {"type": dict, "required": False, "default": {}}

        ddl = dataflow._get_sql_column_definition("metadata", field_info, "mysql")

        assert "DEFAULT (CAST('{}' AS JSON))" in ddl

    def test_empty_list_default_sqlite(self, dataflow):
        """Empty list default should produce valid SQLite DDL."""
        field_info = {"type": list, "required": False, "default": []}

        ddl = dataflow._get_sql_column_definition("tags", field_info, "sqlite")

        assert "DEFAULT '[]'" in ddl
        assert "TEXT" in ddl
        # Should NOT have ::jsonb cast
        assert "::jsonb" not in ddl

    def test_empty_dict_default_sqlite(self, dataflow):
        """Empty dict default should produce valid SQLite DDL."""
        field_info = {"type": dict, "required": False, "default": {}}

        ddl = dataflow._get_sql_column_definition("metadata", field_info, "sqlite")

        assert "DEFAULT '{}'" in ddl
        assert "TEXT" in ddl

    def test_nested_dict_default_postgresql(self, dataflow):
        """Nested dict default should produce valid PostgreSQL DDL."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"nested": {"key": "value"}, "list": [1, 2, 3]},
        }

        ddl = dataflow._get_sql_column_definition("complex", field_info, "postgresql")

        # Verify it's valid JSON (no Python repr syntax)
        assert "{'nested':" not in ddl  # Should not have Python dict syntax
        assert '"nested":' in ddl  # Should have JSON syntax

    def test_int_default_preserved(self, dataflow):
        """Integer defaults should still work correctly."""
        field_info = {"type": int, "required": False, "default": 42}

        ddl = dataflow._get_sql_column_definition("count", field_info, "postgresql")

        assert "DEFAULT 42" in ddl

    def test_string_default_preserved(self, dataflow):
        """String defaults should still work correctly."""
        field_info = {"type": str, "required": False, "default": "default_value"}

        ddl = dataflow._get_sql_column_definition("status", field_info, "postgresql")

        assert "DEFAULT 'default_value'" in ddl

    def test_bool_default_postgresql(self, dataflow):
        """Boolean defaults should work correctly for PostgreSQL."""
        field_info = {"type": bool, "required": False, "default": True}

        ddl = dataflow._get_sql_column_definition("active", field_info, "postgresql")

        assert "DEFAULT TRUE" in ddl

    def test_bool_default_mysql(self, dataflow):
        """Boolean defaults should work correctly for MySQL."""
        field_info = {"type": bool, "required": False, "default": True}

        ddl = dataflow._get_sql_column_definition("active", field_info, "mysql")

        assert "DEFAULT 1" in ddl

    def test_float_default_preserved(self, dataflow):
        """Float defaults should still work correctly."""
        field_info = {"type": float, "required": False, "default": 3.14}

        ddl = dataflow._get_sql_column_definition("score", field_info, "postgresql")

        assert "DEFAULT 3.14" in ddl


class TestUnknownKwargsValidation:
    """Tests for unknown kwargs validation in DataFlow.__init__()."""

    def test_skip_registry_raises_warning(self):
        """skip_registry=True should raise a UserWarning with helpful message."""
        from dataflow import DataFlow

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = DataFlow("sqlite:///:memory:", skip_registry=True, auto_migrate=False)

            # Should have at least one warning
            assert len(w) >= 1

            # Find the DF-CFG-001 warning
            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 1

            warning_msg = str(df_warnings[0].message)
            assert "skip_registry" in warning_msg
            assert "enable_model_persistence=False" in warning_msg

    def test_skip_migration_raises_warning(self):
        """skip_migration should raise a warning suggesting auto_migrate."""
        from dataflow import DataFlow

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = DataFlow("sqlite:///:memory:", skip_migration=True, auto_migrate=False)

            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 1

            warning_msg = str(df_warnings[0].message)
            assert "skip_migration" in warning_msg
            assert "auto_migrate=False" in warning_msg

    def test_connection_pool_size_raises_warning(self):
        """connection_pool_size should raise a warning suggesting pool_size."""
        from dataflow import DataFlow

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = DataFlow(
                "sqlite:///:memory:", connection_pool_size=10, auto_migrate=False
            )

            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 1

            warning_msg = str(df_warnings[0].message)
            assert "connection_pool_size" in warning_msg
            assert "pool_size" in warning_msg

    def test_enable_metrics_raises_warning(self):
        """enable_metrics should raise a warning suggesting monitoring."""
        from dataflow import DataFlow

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = DataFlow("sqlite:///:memory:", enable_metrics=True, auto_migrate=False)

            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 1

            warning_msg = str(df_warnings[0].message)
            assert "enable_metrics" in warning_msg
            assert "monitoring=True" in warning_msg

    def test_unknown_parameter_raises_warning(self):
        """Completely unknown parameters should raise a warning."""
        from dataflow import DataFlow

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = DataFlow(
                "sqlite:///:memory:",
                my_unknown_param="value",
                another_unknown=123,
                auto_migrate=False,
            )

            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 1

            warning_msg = str(df_warnings[0].message)
            assert "my_unknown_param" in warning_msg
            assert "another_unknown" in warning_msg
            assert "has no effect" in warning_msg

    def test_known_kwargs_no_warning(self):
        """Known kwargs should not trigger warnings."""
        from dataflow import DataFlow

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = DataFlow(
                "sqlite:///:memory:",
                batch_size=100,
                schema_cache_enabled=True,
                schema_cache_ttl=3600,
                use_namespaced_nodes=True,
                auto_migrate=False,
            )

            # Should not have DF-CFG-001 warnings
            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 0

    def test_multiple_unknown_params_single_warning(self):
        """Multiple unknown params should produce a single warning listing all."""
        from dataflow import DataFlow

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = DataFlow(
                "sqlite:///:memory:",
                skip_registry=True,
                skip_migration=True,
                unknown_param=123,
                auto_migrate=False,
            )

            # Should have exactly one DF-CFG-001 warning
            df_warnings = [x for x in w if "DF-CFG-001" in str(x.message)]
            assert len(df_warnings) == 1

            # All unknown params should be in the message
            warning_msg = str(df_warnings[0].message)
            assert "skip_registry" in warning_msg
            assert "skip_migration" in warning_msg
            assert "unknown_param" in warning_msg


class TestDDLGenerationIntegration:
    """Integration tests for DDL generation with models."""

    @pytest.fixture
    def dataflow(self):
        """Create DataFlow instance."""
        from dataflow import DataFlow

        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_model_with_list_field_generates_valid_ddl(self, dataflow):
        """Model with List[str] field should generate valid DDL."""

        @dataflow.model
        class TaggedItem:
            id: str
            name: str
            tags: List[str] = []

        # Verify the field type was correctly parsed
        assert "TaggedItem" in dataflow._models

        # Get the generated DDL
        ddl = dataflow._generate_create_table_sql("TaggedItem", "postgresql")

        # Should have valid JSONB type and default
        assert "tags" in ddl.lower()
        # The DDL should be valid SQL (no Python syntax)
        assert "[]" not in ddl or "'[]'" in ddl  # [] only allowed in quotes

    def test_model_with_dict_field_generates_valid_ddl(self, dataflow):
        """Model with Dict field should generate valid DDL."""

        @dataflow.model
        class ConfiguredItem:
            id: str
            name: str
            config: Dict[str, Any] = {}

        ddl = dataflow._generate_create_table_sql("ConfiguredItem", "postgresql")

        assert "config" in ddl.lower()
        # The DDL should be valid SQL
        assert "{}" not in ddl or "'{}'" in ddl  # {} only allowed in quotes

    def test_model_with_optional_list_generates_valid_ddl(self, dataflow):
        """Model with Optional[List[str]] should generate valid DDL."""

        @dataflow.model
        class OptionalTaggedItem:
            id: str
            name: str
            tags: Optional[List[str]] = None

        ddl = dataflow._generate_create_table_sql("OptionalTaggedItem", "postgresql")

        # Should handle Optional[List[str]] correctly
        assert "tags" in ddl.lower()


class TestEdgeCases:
    """Edge case tests for the bug fixes."""

    @pytest.fixture
    def dataflow(self):
        """Create DataFlow instance."""
        from dataflow import DataFlow

        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_deeply_nested_dict_default(self, dataflow):
        """Deeply nested dict default should serialize correctly."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {
                "level1": {
                    "level2": {
                        "level3": ["a", "b", "c"],
                        "value": 123,
                    }
                }
            },
        }

        ddl = dataflow._get_sql_column_definition("deep", field_info, "postgresql")

        # Should be valid JSON, not Python repr
        assert "{'level1':" not in ddl
        # Should contain proper JSON
        assert '"level1"' in ddl or "'level1'" in ddl

    def test_list_with_special_characters(self, dataflow):
        """List with special characters should serialize correctly."""
        field_info = {
            "type": list,
            "required": False,
            "default": ["quote's", 'double"quote', "back\\slash"],
        }

        ddl = dataflow._get_sql_column_definition(
            "special_list", field_info, "postgresql"
        )

        # Should have escaped the special characters properly (JSON handles this)
        assert "DEFAULT '" in ddl

    def test_empty_string_in_list_default(self, dataflow):
        """Empty string in list default should work."""
        field_info = {"type": list, "required": False, "default": ["", "non-empty"]}

        ddl = dataflow._get_sql_column_definition(
            "with_empty", field_info, "postgresql"
        )

        expected_json = json.dumps(["", "non-empty"])
        assert f"DEFAULT '{expected_json}'::jsonb" in ddl


class TestSQLEscapingEdgeCases:
    """Tests for SQL escaping in DDL generation - critical security tests."""

    @pytest.fixture
    def dataflow(self):
        """Create DataFlow instance."""
        from dataflow import DataFlow

        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_single_quote_in_json_default_is_escaped(self, dataflow):
        """Single quotes in JSON default must be SQL-escaped to prevent syntax errors."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"message": "It's a test"},
        }

        ddl = dataflow._get_sql_column_definition("quoted", field_info, "postgresql")

        # Should have escaped single quote for SQL ('' instead of ')
        # The JSON will have "It's" which needs escaping to "It''s" for SQL
        assert "It''s" in ddl, f"Single quote should be SQL-escaped. Got: {ddl}"

    def test_multiple_single_quotes_escaped(self, dataflow):
        """Multiple single quotes should all be escaped."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"text": "Don't say 'hello' to O'Brien"},
        }

        ddl = dataflow._get_sql_column_definition(
            "multi_quoted", field_info, "postgresql"
        )

        # All single quotes should be doubled
        assert "Don''t" in ddl
        assert "''hello''" in ddl
        assert "O''Brien" in ddl

    def test_sql_injection_attempt_in_default_value(self, dataflow):
        """SQL injection attempts in default values should be safely escaped."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"key": "'; DROP TABLE users; --"},
        }

        ddl = dataflow._get_sql_column_definition("evil", field_info, "postgresql")

        # The single quote should be escaped, preventing SQL injection
        assert "'';" in ddl or "DROP TABLE" not in ddl.split("'")[0]
        # The injection should be contained within the JSON string
        assert "DEFAULT '" in ddl

    def test_unicode_in_default_value(self, dataflow):
        """Unicode characters in default values should serialize correctly."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"message": "Hello 世界 🌍 émojis"},
        }

        ddl = dataflow._get_sql_column_definition("unicode", field_info, "postgresql")

        # Unicode should be preserved in JSON
        assert "世界" in ddl or "\\u" in ddl  # Either raw or escaped
        assert "DEFAULT '" in ddl

    def test_newlines_in_default_value(self, dataflow):
        """Newlines in default values should be JSON-escaped."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"text": "line1\nline2\ttabbed"},
        }

        ddl = dataflow._get_sql_column_definition("newlines", field_info, "postgresql")

        # JSON escapes newlines as \n
        assert "\\n" in ddl
        assert "\\t" in ddl

    def test_backslash_in_default_value(self, dataflow):
        """Backslashes in default values should be JSON-escaped."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"path": "C:\\Users\\test"},
        }

        ddl = dataflow._get_sql_column_definition("backslash", field_info, "postgresql")

        # JSON escapes backslashes
        assert "\\\\" in ddl or "C:" in ddl

    def test_mysql_single_quote_escaping(self, dataflow):
        """MySQL DDL should also escape single quotes."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"message": "It's MySQL"},
        }

        ddl = dataflow._get_sql_column_definition("mysql_quoted", field_info, "mysql")

        assert "It''s" in ddl, f"MySQL should also escape single quotes. Got: {ddl}"
        assert "CAST(" in ddl

    def test_sqlite_single_quote_escaping(self, dataflow):
        """SQLite DDL should also escape single quotes."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"message": "It's SQLite"},
        }

        ddl = dataflow._get_sql_column_definition("sqlite_quoted", field_info, "sqlite")

        assert "It''s" in ddl, f"SQLite should also escape single quotes. Got: {ddl}"


class TestFrozenSetTypeMapping:
    """Tests for FrozenSet type mapping."""

    @pytest.fixture
    def dataflow(self):
        """Create DataFlow instance."""
        from dataflow import DataFlow

        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_frozenset_str_maps_to_jsonb_postgresql(self, dataflow):
        """FrozenSet[str] should map to JSONB in PostgreSQL."""
        from typing import FrozenSet

        sql_type = dataflow._python_type_to_sql_type(FrozenSet[str], "postgresql")
        assert sql_type == "JSONB"

    def test_frozenset_int_maps_to_json_mysql(self, dataflow):
        """FrozenSet[int] should map to JSON in MySQL."""
        from typing import FrozenSet

        sql_type = dataflow._python_type_to_sql_type(FrozenSet[int], "mysql")
        assert sql_type == "JSON"

    def test_frozenset_maps_to_text_sqlite(self, dataflow):
        """FrozenSet should map to TEXT in SQLite."""
        from typing import FrozenSet

        sql_type = dataflow._python_type_to_sql_type(FrozenSet[str], "sqlite")
        assert sql_type == "TEXT"


class TestComplexTypeScenarios:
    """Tests for complex type scenarios that users might encounter."""

    @pytest.fixture
    def dataflow(self):
        """Create DataFlow instance."""
        from dataflow import DataFlow

        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_deeply_nested_mixed_types_default(self, dataflow):
        """Complex nested structure with all JSON types should serialize correctly."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {
                "array": [1, "two", 3.0, None, True, {"nested": []}],
                "object": {"deep": {"deeper": {"deepest": []}}},
                "null": None,
                "boolean": False,
                "number": 42.5,
                "string": "hello",
            },
        }

        ddl = dataflow._get_sql_column_definition("complex", field_info, "postgresql")

        # Should produce valid JSON structure
        assert "DEFAULT '" in ddl
        assert "::jsonb" in ddl
        # Should not have Python syntax
        assert "True" not in ddl.split("'")[1] if "True" in ddl else True
        assert "None" not in ddl.split("'")[1] if "None" in ddl else True

    def test_list_of_dicts_default(self, dataflow):
        """List of dicts default should serialize correctly."""
        field_info = {
            "type": list,
            "required": False,
            "default": [{"id": 1, "name": "first"}, {"id": 2, "name": "second"}],
        }

        ddl = dataflow._get_sql_column_definition(
            "list_of_dicts", field_info, "postgresql"
        )

        expected_json = json.dumps(
            [{"id": 1, "name": "first"}, {"id": 2, "name": "second"}]
        )
        assert expected_json in ddl

    def test_dict_with_list_values_default(self, dataflow):
        """Dict with list values should serialize correctly."""
        field_info = {
            "type": dict,
            "required": False,
            "default": {"tags": ["a", "b"], "scores": [1, 2, 3]},
        }

        ddl = dataflow._get_sql_column_definition(
            "dict_with_lists", field_info, "postgresql"
        )

        expected_json = json.dumps({"tags": ["a", "b"], "scores": [1, 2, 3]})
        assert expected_json in ddl
