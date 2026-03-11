"""
Unit tests for built-in constraint dimensions.

Tests cover:
- CostLimitDimension: Budget checking
- TimeDimension: Time window validation
- ResourceDimension: Glob pattern matching
- RateLimitDimension: Rate limit checking
- DataAccessDimension: PII and classification controls
- CommunicationDimension: External communication controls
- Audit requirements for sensitive dimensions
"""

from datetime import datetime, time

import pytest
from kaizen.trust.constraints.builtin import (
    CommunicationDimension,
    CostLimitDimension,
    DataAccessDimension,
    RateLimitDimension,
    ResourceDimension,
    TimeDimension,
)


class TestCostLimitDimension:
    """Tests for CostLimitDimension."""

    @pytest.fixture
    def dimension(self) -> CostLimitDimension:
        return CostLimitDimension()

    def test_cost_limit_within_budget(self, dimension: CostLimitDimension):
        """Cost within limit is satisfied."""
        constraint = dimension.parse(1000)
        result = dimension.check(constraint, {"cost_used": 500})

        assert result.satisfied is True
        assert result.remaining == 500
        assert result.used == 500
        assert result.limit == 1000

    def test_cost_limit_over_budget(self, dimension: CostLimitDimension):
        """Cost over limit is not satisfied."""
        constraint = dimension.parse(1000)
        result = dimension.check(constraint, {"cost_used": 1200})

        assert result.satisfied is False
        assert result.remaining == 0
        assert result.used == 1200
        assert "over budget" in result.reason

    def test_cost_limit_parse_string(self, dimension: CostLimitDimension):
        """Parses string values."""
        constraint = dimension.parse("500.50")
        assert constraint.parsed == 500.50

    def test_cost_limit_negative_raises(self, dimension: CostLimitDimension):
        """Negative cost raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            dimension.parse(-100)


class TestTimeDimension:
    """Tests for TimeDimension."""

    @pytest.fixture
    def dimension(self) -> TimeDimension:
        return TimeDimension()

    def test_time_dimension_in_window(self, dimension: TimeDimension):
        """Time within window is satisfied."""
        constraint = dimension.parse("09:00-17:00")
        result = dimension.check(
            constraint, {"current_time": datetime(2024, 1, 15, 12, 0)}
        )

        assert result.satisfied is True
        assert "within time window" in result.reason

    def test_time_dimension_outside_window(self, dimension: TimeDimension):
        """Time outside window is not satisfied."""
        constraint = dimension.parse("09:00-17:00")
        result = dimension.check(
            constraint, {"current_time": datetime(2024, 1, 15, 20, 0)}
        )

        assert result.satisfied is False
        assert "outside time window" in result.reason

    def test_time_tightening_valid(self, dimension: TimeDimension):
        """Tighter time window is valid."""
        parent = dimension.parse("08:00-18:00")
        child = dimension.parse("09:00-17:00")  # Subset

        assert dimension.validate_tightening(parent, child) is True

    def test_time_tightening_invalid(self, dimension: TimeDimension):
        """Looser time window is invalid."""
        parent = dimension.parse("09:00-17:00")
        child = dimension.parse("08:00-18:00")  # Wider

        assert dimension.validate_tightening(parent, child) is False

    def test_time_dimension_invalid_format(self, dimension: TimeDimension):
        """Invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time window format"):
            dimension.parse("9-17")

    def test_time_dimension_overnight_window(self, dimension: TimeDimension):
        """Overnight window (e.g., 22:00-06:00) works."""
        constraint = dimension.parse("22:00-06:00")

        # At 23:00 (in evening part)
        result = dimension.check(
            constraint, {"current_time": datetime(2024, 1, 15, 23, 0)}
        )
        assert result.satisfied is True

        # At 03:00 (in morning part)
        result = dimension.check(
            constraint, {"current_time": datetime(2024, 1, 15, 3, 0)}
        )
        assert result.satisfied is True

        # At 12:00 (outside)
        result = dimension.check(
            constraint, {"current_time": datetime(2024, 1, 15, 12, 0)}
        )
        assert result.satisfied is False


class TestResourceDimension:
    """Tests for ResourceDimension."""

    @pytest.fixture
    def dimension(self) -> ResourceDimension:
        return ResourceDimension()

    def test_resource_glob_match(self, dimension: ResourceDimension):
        """Resource matching glob pattern is satisfied."""
        constraint = dimension.parse(["data/*.json", "logs/*.log"])
        result = dimension.check(constraint, {"resource_requested": "data/users.json"})

        assert result.satisfied is True
        assert "matches pattern" in result.reason

    def test_resource_glob_no_match(self, dimension: ResourceDimension):
        """Resource not matching any pattern is not satisfied."""
        constraint = dimension.parse(["data/*.json"])
        result = dimension.check(constraint, {"resource_requested": "secrets/keys.txt"})

        assert result.satisfied is False
        assert "does not match" in result.reason

    def test_resource_tightening_valid(self, dimension: ResourceDimension):
        """More specific patterns are valid tightening."""
        parent = dimension.parse(["data/**"])
        child = dimension.parse(["data/users/*"])

        assert dimension.validate_tightening(parent, child) is True

    def test_resource_tightening_invalid_broader_pattern(
        self, dimension: ResourceDimension
    ):
        """Broader patterns are invalid tightening (** rejected in parse)."""
        parent = dimension.parse(["data/users/*"])
        # "**" alone is now rejected as too permissive
        with pytest.raises(ValueError, match="too permissive"):
            dimension.parse(["**"])

    def test_resource_single_pattern(self, dimension: ResourceDimension):
        """Single pattern string works."""
        constraint = dimension.parse("*.txt")
        result = dimension.check(constraint, {"resource_requested": "readme.txt"})

        assert result.satisfied is True

    # Security tests for CARE-046

    def test_resource_path_traversal_blocked(self, dimension: ResourceDimension):
        """Path traversal attempts are blocked (CARE-046)."""
        constraint = dimension.parse(["data/*"])

        # Various path traversal attempts
        traversal_paths = [
            "../etc/passwd",
            "data/../etc/passwd",
            "data/subdir/../../etc/passwd",
            "..\\windows\\system32",
            "data\\..\\secrets",
        ]

        for path in traversal_paths:
            result = dimension.check(constraint, {"resource_requested": path})
            assert result.satisfied is False, f"Path traversal not blocked: {path}"
            assert (
                "path traversal" in result.reason.lower()
            ), f"Wrong reason for {path}: {result.reason}"

    def test_resource_null_byte_blocked(self, dimension: ResourceDimension):
        """Null byte injection is blocked (CARE-046)."""
        constraint = dimension.parse(["data/*"])

        # Null byte injection attempts
        null_paths = [
            "data/file.txt\x00.exe",
            "data/\x00../etc/passwd",
            "\x00data/file.txt",
        ]

        for path in null_paths:
            result = dimension.check(constraint, {"resource_requested": path})
            assert result.satisfied is False, f"Null byte not blocked: {path!r}"
            assert (
                "null byte" in result.reason.lower()
            ), f"Wrong reason for {path!r}: {result.reason}"

    def test_resource_case_sensitive_matching(self, dimension: ResourceDimension):
        """Pattern matching is case-sensitive (CARE-046)."""
        constraint = dimension.parse(["data/*.json"])

        # Exact case should match
        result = dimension.check(constraint, {"resource_requested": "data/file.json"})
        assert result.satisfied is True

        # Different case should NOT match (case-sensitive)
        result = dimension.check(constraint, {"resource_requested": "DATA/file.json"})
        assert result.satisfied is False

        result = dimension.check(constraint, {"resource_requested": "data/file.JSON"})
        assert result.satisfied is False

    def test_resource_overly_permissive_pattern_rejected(
        self, dimension: ResourceDimension
    ):
        """Overly permissive patterns are rejected (CARE-046)."""
        overly_permissive = ["*", "**", "***"]

        for pattern in overly_permissive:
            with pytest.raises(ValueError, match="too permissive"):
                dimension.parse(pattern)

            with pytest.raises(ValueError, match="too permissive"):
                dimension.parse([pattern])

    def test_resource_valid_wildcard_patterns_allowed(
        self, dimension: ResourceDimension
    ):
        """Valid wildcard patterns with path prefixes are allowed."""
        # These should work - they're specific enough
        valid_patterns = [
            "data/*",
            "data/**",
            "logs/*.log",
            "*.txt",
            "config/*.yaml",
        ]

        for pattern in valid_patterns:
            constraint = dimension.parse(pattern)
            assert constraint.parsed == [pattern]

    def test_resource_normal_paths_still_work(self, dimension: ResourceDimension):
        """Normal resource paths still work correctly."""
        constraint = dimension.parse(["data/*", "logs/**"])

        # Normal paths should match
        result = dimension.check(constraint, {"resource_requested": "data/users.json"})
        assert result.satisfied is True

        result = dimension.check(constraint, {"resource_requested": "logs/app.log"})
        assert result.satisfied is True

        result = dimension.check(
            constraint, {"resource_requested": "logs/subdir/app.log"}
        )
        assert result.satisfied is True  # ** matches across directories

        # Unmatched paths should fail normally
        result = dimension.check(constraint, {"resource_requested": "secrets/key.pem"})
        assert result.satisfied is False
        assert "does not match" in result.reason

    def test_resource_empty_path_allowed(self, dimension: ResourceDimension):
        """Empty resource path returns satisfied."""
        constraint = dimension.parse(["data/*"])
        result = dimension.check(constraint, {"resource_requested": ""})
        assert result.satisfied is True
        assert "no resource requested" in result.reason

    def test_resource_no_resource_key_allowed(self, dimension: ResourceDimension):
        """Missing resource_requested key returns satisfied."""
        constraint = dimension.parse(["data/*"])
        result = dimension.check(constraint, {})
        assert result.satisfied is True


class TestRateLimitDimension:
    """Tests for RateLimitDimension."""

    @pytest.fixture
    def dimension(self) -> RateLimitDimension:
        return RateLimitDimension()

    def test_rate_limit_within(self, dimension: RateLimitDimension):
        """Requests within limit is satisfied."""
        constraint = dimension.parse(100)
        result = dimension.check(constraint, {"requests_in_period": 50})

        assert result.satisfied is True
        assert result.remaining == 50
        assert result.limit == 100

    def test_rate_limit_exceeded(self, dimension: RateLimitDimension):
        """Requests over limit is not satisfied."""
        constraint = dimension.parse(100)
        result = dimension.check(constraint, {"requests_in_period": 150})

        assert result.satisfied is False
        assert result.remaining == 0
        assert "exceeded" in result.reason

    def test_rate_limit_period_format(self, dimension: RateLimitDimension):
        """N/period format parses correctly."""
        constraint = dimension.parse("100/minute")

        assert constraint.parsed["limit"] == 100
        assert constraint.parsed["period"] == "minute"

    def test_rate_limit_various_periods(self, dimension: RateLimitDimension):
        """Various period formats work."""
        for period in ["second", "minute", "hour", "day"]:
            constraint = dimension.parse(f"50/{period}")
            assert constraint.parsed["period"] == period

    def test_rate_limit_invalid_period(self, dimension: RateLimitDimension):
        """Invalid period raises ValueError."""
        with pytest.raises(ValueError, match="Invalid period"):
            dimension.parse("100/week")


class TestDataAccessDimension:
    """Tests for DataAccessDimension."""

    @pytest.fixture
    def dimension(self) -> DataAccessDimension:
        return DataAccessDimension()

    def test_data_access_no_pii_blocks(self, dimension: DataAccessDimension):
        """no_pii mode blocks PII access."""
        constraint = dimension.parse("no_pii")
        result = dimension.check(constraint, {"contains_pii": True})

        assert result.satisfied is False
        assert "PII access not allowed" in result.reason

    def test_data_access_no_pii_allows(self, dimension: DataAccessDimension):
        """no_pii mode allows non-PII access."""
        constraint = dimension.parse("no_pii")
        result = dimension.check(constraint, {"contains_pii": False})

        assert result.satisfied is True

    def test_data_access_internal_blocks(self, dimension: DataAccessDimension):
        """internal_only mode blocks external data."""
        constraint = dimension.parse("internal_only")
        result = dimension.check(constraint, {"data_classification": "external"})

        assert result.satisfied is False
        assert "not allowed" in result.reason

    def test_data_access_internal_allows(self, dimension: DataAccessDimension):
        """internal_only mode allows internal data."""
        constraint = dimension.parse("internal_only")
        result = dimension.check(constraint, {"data_classification": "internal"})

        assert result.satisfied is True

    def test_data_access_allows(self, dimension: DataAccessDimension):
        """allow_all mode allows access."""
        constraint = dimension.parse("allow_all")
        result = dimension.check(
            constraint, {"contains_pii": True, "data_classification": "external"}
        )

        assert result.satisfied is True

    def test_data_access_dict_config(self, dimension: DataAccessDimension):
        """Dict configuration with classifications."""
        constraint = dimension.parse(
            {
                "mode": "allow_all",
                "allowed_classifications": ["internal", "confidential"],
            }
        )
        result = dimension.check(constraint, {"data_classification": "internal"})

        assert result.satisfied is True


class TestCommunicationDimension:
    """Tests for CommunicationDimension."""

    @pytest.fixture
    def dimension(self) -> CommunicationDimension:
        return CommunicationDimension()

    def test_communication_none_blocks(self, dimension: CommunicationDimension):
        """none mode blocks all communication."""
        constraint = dimension.parse("none")
        result = dimension.check(
            constraint, {"communication_target": "api.external.com"}
        )

        assert result.satisfied is False
        assert "blocked" in result.reason

    def test_communication_internal_only(self, dimension: CommunicationDimension):
        """internal_only mode allows only internal targets."""
        constraint = dimension.parse("internal_only")

        # Internal allowed
        result = dimension.check(
            constraint, {"communication_target": "service.internal.company.com"}
        )
        assert result.satisfied is True

        # External blocked
        result = dimension.check(
            constraint, {"communication_target": "api.external.com"}
        )
        assert result.satisfied is False

    def test_communication_allowed_domains(self, dimension: CommunicationDimension):
        """allowed_domains mode allows specific domains."""
        constraint = dimension.parse(
            {
                "mode": "allowed_domains",
                "allowed_domains": ["example.com", "api.trusted.com"],
            }
        )

        # Allowed domain
        result = dimension.check(
            constraint, {"communication_target": "service.example.com"}
        )
        assert result.satisfied is True

        # Not allowed
        result = dimension.check(constraint, {"communication_target": "malicious.com"})
        assert result.satisfied is False

    def test_communication_no_target(self, dimension: CommunicationDimension):
        """No communication target is satisfied."""
        constraint = dimension.parse("none")
        result = dimension.check(constraint, {})

        assert result.satisfied is True
        assert "no communication target" in result.reason


class TestAuditRequirements:
    """Tests for requires_audit property."""

    def test_all_dimensions_require_audit(self):
        """CostLimit and DataAccess require audit."""
        cost = CostLimitDimension()
        data = DataAccessDimension()
        rate = RateLimitDimension()

        assert cost.requires_audit is True
        assert data.requires_audit is True
        assert rate.requires_audit is False  # Rate doesn't require audit

    def test_dimension_names(self):
        """All dimensions have correct names."""
        assert CostLimitDimension().name == "cost_limit"
        assert TimeDimension().name == "time_window"
        assert ResourceDimension().name == "resources"
        assert RateLimitDimension().name == "rate_limit"
        assert DataAccessDimension().name == "data_access"
        assert CommunicationDimension().name == "communication"
