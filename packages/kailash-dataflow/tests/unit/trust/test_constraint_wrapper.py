#!/usr/bin/env python3
"""
Unit Tests for ConstraintEnvelopeWrapper (CARE-019).

Tests the constraint translation logic for DataFlow trust integration.
These tests verify that EATP constraints are correctly translated to
SQL filter components.

Test Coverage:
- Data scope constraint translation
- Column access filtering
- Time window translation
- Row limit extraction
- PII column detection
- Sensitive column detection
- Combined constraint application
"""

from datetime import datetime, timedelta, timezone

import pytest

from dataflow.trust.query_wrapper import ConstraintEnvelopeWrapper, QueryAccessResult


class TestTranslateDataScope:
    """Tests for translate_data_scope method."""

    def test_translate_data_scope_simple(self):
        """Test simple data scope constraint translation.

        "department:finance" should translate to {"department": "finance"}
        """
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_data_scope("department:finance")

        assert result == {"department": "finance"}

    def test_translate_data_scope_multiple(self):
        """Test multiple data scope constraints in single value.

        "department:finance,region:us" should translate to multiple filters.
        """
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_data_scope("department:finance,region:us")

        assert result == {"department": "finance", "region": "us"}

    def test_translate_data_scope_empty(self):
        """Test empty data scope returns empty dict."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_data_scope("")

        assert result == {}

    def test_translate_data_scope_invalid_format(self):
        """Test invalid format returns empty dict."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_data_scope("invalid_format")

        assert result == {}

    def test_translate_data_scope_with_spaces(self):
        """Test data scope with spaces is handled correctly."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_data_scope(" department : finance , region : us ")

        assert result == {"department": "finance", "region": "us"}


class TestTranslateColumnAccess:
    """Tests for translate_column_access method."""

    def test_translate_column_access_allowed(self):
        """Test column filtering based on allowed columns constraint."""
        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email", "ssn", "salary", "department"]
        constraint = "allowed:id,name,email,department"

        result = wrapper.translate_column_access(constraint, model_columns)

        assert set(result) == {"id", "name", "email", "department"}
        assert "ssn" not in result
        assert "salary" not in result

    def test_translate_column_access_denied(self):
        """Test column filtering based on denied columns constraint."""
        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email", "ssn", "salary", "department"]
        constraint = "denied:ssn,salary"

        result = wrapper.translate_column_access(constraint, model_columns)

        assert set(result) == {"id", "name", "email", "department"}
        assert "ssn" not in result
        assert "salary" not in result

    def test_translate_column_access_empty_constraint(self):
        """Test empty constraint returns all columns."""
        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email"]

        result = wrapper.translate_column_access("", model_columns)

        assert result == model_columns

    def test_translate_column_access_all_columns(self):
        """Test wildcard constraint returns all columns."""
        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email"]

        result = wrapper.translate_column_access("allowed:*", model_columns)

        assert result == model_columns


class TestTranslateTimeWindow:
    """Tests for translate_time_window method."""

    def test_translate_time_window_30_days(self):
        """Test 30-day time window generates correct timestamp filter."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_time_window("last_30_days")

        assert "created_at" in result
        assert "$gte" in result["created_at"]

        # Verify the timestamp is approximately 30 days ago
        expected_min = datetime.now(timezone.utc) - timedelta(days=31)
        expected_max = datetime.now(timezone.utc) - timedelta(days=29)
        actual = result["created_at"]["$gte"]

        assert expected_min <= actual <= expected_max

    def test_translate_time_window_7_days(self):
        """Test 7-day time window generates correct timestamp filter."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_time_window("last_7_days")

        assert "created_at" in result
        assert "$gte" in result["created_at"]

        # Verify the timestamp is approximately 7 days ago
        expected_min = datetime.now(timezone.utc) - timedelta(days=8)
        expected_max = datetime.now(timezone.utc) - timedelta(days=6)
        actual = result["created_at"]["$gte"]

        assert expected_min <= actual <= expected_max

    def test_translate_time_window_24_hours(self):
        """Test 24-hour time window generates correct timestamp filter."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_time_window("last_24_hours")

        assert "created_at" in result
        assert "$gte" in result["created_at"]

        # Verify the timestamp is approximately 24 hours ago
        expected_min = datetime.now(timezone.utc) - timedelta(hours=25)
        expected_max = datetime.now(timezone.utc) - timedelta(hours=23)
        actual = result["created_at"]["$gte"]

        assert expected_min <= actual <= expected_max

    def test_translate_time_window_empty(self):
        """Test empty time window returns empty dict."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_time_window("")

        assert result == {}

    def test_translate_time_window_invalid(self):
        """Test invalid time window returns empty dict."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_time_window("invalid_window")

        assert result == {}


class TestTranslateRowLimit:
    """Tests for translate_row_limit method."""

    def test_translate_row_limit_valid(self):
        """Test valid row limit extraction."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_row_limit("row_limit:1000")

        assert result == 1000

    def test_translate_row_limit_just_number(self):
        """Test row limit with just a number."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_row_limit("500")

        assert result == 500

    def test_translate_row_limit_invalid(self):
        """Test invalid row limit returns None."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_row_limit("row_limit:invalid")

        assert result is None

    def test_translate_row_limit_empty(self):
        """Test empty row limit returns None."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_row_limit("")

        assert result is None

    def test_translate_row_limit_negative(self):
        """Test negative row limit returns None."""
        wrapper = ConstraintEnvelopeWrapper()
        result = wrapper.translate_row_limit("row_limit:-100")

        assert result is None


class TestDetectPIIColumns:
    """Tests for detect_pii_columns method."""

    def test_detect_pii_columns_finds_ssn(self):
        """Test PII detection finds SSN-related columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "name", "ssn", "social_security", "email"]

        result = wrapper.detect_pii_columns(columns)

        assert "ssn" in result
        assert "social_security" in result
        assert "id" not in result
        assert "name" not in result

    def test_detect_pii_columns_finds_dob(self):
        """Test PII detection finds date of birth columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "dob", "date_of_birth", "email"]

        result = wrapper.detect_pii_columns(columns)

        assert "dob" in result
        assert "date_of_birth" in result

    def test_detect_pii_columns_finds_tax_id(self):
        """Test PII detection finds tax ID columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "tax_id", "taxpayer_id", "email"]

        result = wrapper.detect_pii_columns(columns)

        assert "tax_id" in result
        assert "taxpayer_id" in result

    def test_detect_pii_columns_finds_passport(self):
        """Test PII detection finds passport columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "passport", "passport_number", "email"]

        result = wrapper.detect_pii_columns(columns)

        assert "passport" in result
        assert "passport_number" in result

    def test_detect_pii_columns_finds_drivers_license(self):
        """Test PII detection finds driver's license columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "drivers_license", "driver_license_number", "email"]

        result = wrapper.detect_pii_columns(columns)

        assert "drivers_license" in result
        assert "driver_license_number" in result

    def test_detect_pii_no_match(self):
        """Test PII detection returns empty list when no PII columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "name", "email", "department", "created_at"]

        result = wrapper.detect_pii_columns(columns)

        assert result == []

    def test_detect_pii_session_id_no_false_positive(self):
        """Test CARE-056: 'session_id' does NOT match as PII.

        This test verifies the fix for CARE-056 security finding.
        Previously, patterns without word boundaries could cause
        'session_id' to incorrectly match 'ssn' (se-ssn substring).
        With proper letter boundaries, 'session' is recognized as
        a single word and does not match the 'ssn' PII pattern.
        """
        wrapper = ConstraintEnvelopeWrapper()
        # These column names contain PII pattern substrings but should NOT match
        # because the patterns appear within larger words, not as standalone terms
        columns = [
            "session_id",  # Contains letters around where 'ssn' might appear
            "doberman_breed",  # Contains 'dob' as substring in 'doberman'
            "adobe_software",  # Contains 'dob' as reverse substring
            "lesson_plan",  # Contains no PII patterns
        ]

        result = wrapper.detect_pii_columns(columns)

        # None of these should match - they are false positives
        assert result == [], (
            f"CARE-056 regression: expected no matches for non-PII columns, "
            f"but got {result}"
        )

    def test_detect_pii_user_ssn_true_positive(self):
        """Test CARE-056: 'user_ssn' DOES match as PII.

        This test verifies that columns with PII terms separated by
        underscores are still correctly detected. The pattern 'ssn'
        should match in 'user_ssn' because underscores are not letters,
        allowing the pattern to match at word/term boundaries.
        """
        wrapper = ConstraintEnvelopeWrapper()
        # These column names have PII terms separated by underscores
        columns = [
            "user_ssn",  # 'ssn' is a separate term after underscore
            "employee_dob",  # 'dob' is a separate term after underscore
            "primary_tax_id",  # 'tax_id' is a separate term after underscore
            "ssn_value",  # 'ssn' is a separate term before underscore
            "my_passport_number",  # 'passport_number' is a separate term
        ]

        result = wrapper.detect_pii_columns(columns)

        # All of these should match as PII
        assert "user_ssn" in result, "user_ssn should be detected as PII"
        assert "employee_dob" in result, "employee_dob should be detected as PII"
        assert "primary_tax_id" in result, "primary_tax_id should be detected as PII"
        assert "ssn_value" in result, "ssn_value should be detected as PII"
        assert (
            "my_passport_number" in result
        ), "my_passport_number should be detected as PII"


class TestDetectSensitiveColumns:
    """Tests for detect_sensitive_columns method."""

    def test_detect_sensitive_columns_salary(self):
        """Test sensitive column detection finds salary."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "name", "salary", "annual_salary", "email"]

        result = wrapper.detect_sensitive_columns(columns)

        assert "salary" in result
        assert "annual_salary" in result

    def test_detect_sensitive_columns_password(self):
        """Test sensitive column detection finds password columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "password", "password_hash", "email"]

        result = wrapper.detect_sensitive_columns(columns)

        assert "password" in result
        assert "password_hash" in result

    def test_detect_sensitive_columns_api_key(self):
        """Test sensitive column detection finds API key columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "api_key", "api_secret", "email"]

        result = wrapper.detect_sensitive_columns(columns)

        assert "api_key" in result
        assert "api_secret" in result

    def test_detect_sensitive_columns_secret(self):
        """Test sensitive column detection finds secret columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "secret", "client_secret", "email"]

        result = wrapper.detect_sensitive_columns(columns)

        assert "secret" in result
        assert "client_secret" in result

    def test_detect_sensitive_columns_token(self):
        """Test sensitive column detection finds token columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "token", "access_token", "refresh_token", "email"]

        result = wrapper.detect_sensitive_columns(columns)

        assert "token" in result
        assert "access_token" in result
        assert "refresh_token" in result

    def test_detect_sensitive_columns_credential(self):
        """Test sensitive column detection finds credential columns."""
        wrapper = ConstraintEnvelopeWrapper()
        columns = ["id", "credential", "credentials", "user_credentials", "email"]

        result = wrapper.detect_sensitive_columns(columns)

        assert "credential" in result
        assert "credentials" in result
        assert "user_credentials" in result


class TestApplyConstraints:
    """Tests for apply_constraints method."""

    def test_apply_constraints_read_only(self, sample_constraints):
        """Test ACTION_RESTRICTION "read_only" blocks writes."""
        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email"]

        # Filter to just the read_only constraint
        read_only_constraints = [
            c for c in sample_constraints if c.value == "read_only"
        ]

        result = wrapper.apply_constraints(
            read_only_constraints,
            model_columns,
            operation="write",
        )

        assert isinstance(result, QueryAccessResult)
        assert result.allowed is False
        assert "read_only" in result.denied_reason.lower()

    def test_apply_constraints_no_pii(self, sample_columns_with_pii):
        """Test ACTION_RESTRICTION "no_pii" filters PII columns."""
        wrapper = ConstraintEnvelopeWrapper()

        # Create no_pii constraint
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        no_pii_constraint = MockConstraint(
            id="con-test",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="no_pii",
            source="test",
        )

        result = wrapper.apply_constraints(
            [no_pii_constraint],
            sample_columns_with_pii,
            operation="read",
        )

        assert isinstance(result, QueryAccessResult)
        assert result.allowed is True
        # PII columns should be filtered out
        assert "ssn" not in result.filtered_columns
        assert "social_security_number" not in result.filtered_columns
        assert "dob" not in result.filtered_columns
        assert "date_of_birth" not in result.filtered_columns
        assert "tax_id" not in result.filtered_columns
        # Non-PII columns should be present
        assert "id" in result.filtered_columns
        assert "name" in result.filtered_columns
        # PII columns should be in the filtered list
        assert len(result.pii_columns_filtered) > 0

    def test_apply_constraints_combined(self, sample_constraints):
        """Test multiple constraints applied together."""
        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email", "department", "created_at"]

        result = wrapper.apply_constraints(
            sample_constraints,
            model_columns,
            operation="read",
        )

        assert isinstance(result, QueryAccessResult)
        # With combined constraints, should still allow read
        assert result.allowed is True
        # Should have applied constraints list
        assert len(result.applied_constraints) > 0
        # Should have additional filters from data scope
        assert "department" in result.additional_filters

    def test_apply_constraints_empty(self):
        """Test empty constraints result in full access."""
        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email"]

        result = wrapper.apply_constraints(
            [],
            model_columns,
            operation="read",
        )

        assert isinstance(result, QueryAccessResult)
        assert result.allowed is True
        assert result.filtered_columns == model_columns
        assert result.additional_filters == {}
        assert result.row_limit is None
        assert result.denied_reason is None


class TestQueryAccessResultStructure:
    """Tests for QueryAccessResult dataclass structure."""

    def test_query_access_result_fields(self):
        """Test QueryAccessResult has all required fields."""
        result = QueryAccessResult(
            allowed=True,
            filtered_columns=["id", "name"],
            additional_filters={"department": "finance"},
            row_limit=100,
            denied_reason=None,
            applied_constraints=["data_scope:department:finance"],
            pii_columns_filtered=["ssn"],
            sensitive_columns_flagged=["salary"],
        )

        assert result.allowed is True
        assert result.filtered_columns == ["id", "name"]
        assert result.additional_filters == {"department": "finance"}
        assert result.row_limit == 100
        assert result.denied_reason is None
        assert result.applied_constraints == ["data_scope:department:finance"]
        assert result.pii_columns_filtered == ["ssn"]
        assert result.sensitive_columns_flagged == ["salary"]

    def test_query_access_result_denied(self):
        """Test QueryAccessResult with denied access."""
        result = QueryAccessResult(
            allowed=False,
            filtered_columns=[],
            additional_filters={},
            row_limit=None,
            denied_reason="Read-only constraint violated",
            applied_constraints=["action_restriction:read_only"],
            pii_columns_filtered=[],
            sensitive_columns_flagged=[],
        )

        assert result.allowed is False
        assert result.denied_reason == "Read-only constraint violated"


# === Test Group: CARE-055 Read-Only Allowlist (Security Fix) ===


class TestReadOnlyAllowlist:
    """Tests for CARE-055: read_only constraint uses allowlist approach.

    Security fix: Instead of denying specific operations (denylist),
    we now only allow explicitly permitted operations (allowlist).
    """

    def test_read_only_allows_read_operations(self):
        """Test that read_only constraint allows read, select, list, count, get.

        CARE-055: Allowlist approach - only these operations are permitted.
        """
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email"]

        read_only_constraint = MockConstraint(
            id="con-readonly",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="test",
        )

        # All these operations should be allowed under read_only
        allowed_operations = ["read", "select", "list", "count", "get"]

        for operation in allowed_operations:
            result = wrapper.apply_constraints(
                [read_only_constraint],
                model_columns,
                operation=operation,
            )
            assert result.allowed is True, f"Operation '{operation}' should be allowed"
            assert result.denied_reason is None

    def test_read_only_denies_unlisted_operations(self):
        """Test that read_only constraint denies operations not in allowlist.

        CARE-055: Allowlist approach - anything not explicitly allowed is denied.
        """
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email"]

        read_only_constraint = MockConstraint(
            id="con-readonly",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="test",
        )

        # These operations should be denied under read_only
        denied_operations = [
            "write",
            "create",
            "update",
            "delete",
            "insert",
            "upsert",
            "bulk_create",
            "bulk_delete",
            "truncate",
            "drop",
            "alter",
            "execute",
            "unknown_operation",
        ]

        for operation in denied_operations:
            result = wrapper.apply_constraints(
                [read_only_constraint],
                model_columns,
                operation=operation,
            )
            assert result.allowed is False, f"Operation '{operation}' should be denied"
            assert "read_only" in result.denied_reason.lower()

    def test_read_only_case_insensitive(self):
        """Test that read_only operation matching is case-insensitive.

        CARE-055: Operations should match regardless of case.
        """
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        wrapper = ConstraintEnvelopeWrapper()
        model_columns = ["id", "name", "email"]

        read_only_constraint = MockConstraint(
            id="con-readonly",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="test",
        )

        # Test case variations of allowed operations
        case_variations = ["READ", "Read", "SELECT", "Select", "LIST", "Count", "GET"]

        for operation in case_variations:
            result = wrapper.apply_constraints(
                [read_only_constraint],
                model_columns,
                operation=operation,
            )
            assert (
                result.allowed is True
            ), f"Operation '{operation}' should be allowed (case-insensitive)"
