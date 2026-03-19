# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Built-in Constraint Dimensions for EATP.

This module provides the six built-in constraint dimensions that are
auto-approved in the ConstraintDimensionRegistry:

1. CostLimitDimension: Maximum cost budget
2. TimeDimension: Allowed time windows
3. ResourceDimension: Resource access patterns (glob)
4. RateLimitDimension: Request rate limits
5. DataAccessDimension: Data classification and PII controls
6. CommunicationDimension: External communication controls

All built-in dimensions follow consistent patterns:
- Parse method normalizes various input formats
- Check method validates against execution context
- Tightening validation ensures child <= parent
- requires_audit=True for sensitive dimensions

Example:
    from eatp.constraints import ConstraintDimensionRegistry
    from eatp.constraints.builtin import (
        CostLimitDimension,
        TimeDimension,
        DataAccessDimension,
    )

    registry = ConstraintDimensionRegistry()
    registry.register(CostLimitDimension())
    registry.register(TimeDimension())
    registry.register(DataAccessDimension())

Author: Kaizen Framework Team
Created: 2026-02-08
"""

import fnmatch
import logging
import math
import re
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional, Set, Union

from eatp.constraints.dimension import (
    ConstraintCheckResult,
    ConstraintDimension,
    ConstraintValue,
)

logger = logging.getLogger(__name__)


class CostLimitDimension(ConstraintDimension):
    """
    Constraint dimension for cost/budget limits.

    Parses float values and checks against cost_used in context.
    This dimension requires audit logging due to financial implications.

    Example:
        dimension = CostLimitDimension()
        constraint = dimension.parse(1000.0)  # $10.00 in cents
        result = dimension.check(constraint, {"cost_used": 500.0})
        assert result.satisfied  # Within budget
    """

    @property
    def name(self) -> str:
        return "cost_limit"

    @property
    def description(self) -> str:
        return "Maximum cost limit in cents"

    @property
    def requires_audit(self) -> bool:
        return True

    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse cost limit value.

        Args:
            value: Float, int, or string representing cost limit

        Returns:
            ConstraintValue with parsed float

        Raises:
            ValueError: If value cannot be parsed or is negative
        """
        try:
            parsed = float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot parse cost limit: {value}") from e

        if not math.isfinite(parsed):
            raise ValueError(f"Cost limit must be finite: {parsed}")
        if parsed < 0:
            raise ValueError(f"Cost limit must be non-negative: {parsed}")

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
            metadata={"unit": "cents"},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if cost usage is within limit.

        Expected context keys:
        - cost_used: Amount already used

        Args:
            constraint: Parsed cost limit constraint
            context: Execution context with cost_used

        Returns:
            ConstraintCheckResult with satisfaction status
        """
        limit = constraint.parsed
        used = context.get("cost_used", 0.0)

        try:
            used = float(used)
        except (TypeError, ValueError):
            used = 0.0

        remaining = max(0, limit - used)
        satisfied = used <= limit

        return ConstraintCheckResult(
            satisfied=satisfied,
            reason="within budget" if satisfied else f"over budget by {used - limit}",
            remaining=remaining,
            used=used,
            limit=limit,
        )


class TimeDimension(ConstraintDimension):
    """
    Constraint dimension for time window restrictions.

    Parses time windows in "HH:MM-HH:MM" format and checks if current time
    falls within the allowed window. Supports overnight windows (e.g., "22:00-06:00").

    Example:
        dimension = TimeDimension()
        constraint = dimension.parse("09:00-17:00")  # Business hours
        result = dimension.check(constraint, {"current_time": datetime.now(timezone.utc)})
    """

    @property
    def name(self) -> str:
        return "time_window"

    @property
    def description(self) -> str:
        return "Allowed time window in HH:MM-HH:MM format"

    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse time window specification.

        Args:
            value: String in "HH:MM-HH:MM" format

        Returns:
            ConstraintValue with parsed time range

        Raises:
            ValueError: If format is invalid
        """
        if not isinstance(value, str):
            raise ValueError(f"Time window must be a string: {value}")

        pattern = r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$"
        match = re.match(pattern, value.strip())

        if not match:
            raise ValueError(f"Invalid time window format: {value}. Expected HH:MM-HH:MM")

        start_hour, start_min = int(match.group(1)), int(match.group(2))
        end_hour, end_min = int(match.group(3)), int(match.group(4))

        # Validate ranges
        if not (0 <= start_hour <= 23 and 0 <= start_min <= 59):
            raise ValueError(f"Invalid start time: {start_hour}:{start_min}")
        if not (0 <= end_hour <= 23 and 0 <= end_min <= 59):
            raise ValueError(f"Invalid end time: {end_hour}:{end_min}")

        start_time = time(start_hour, start_min)
        end_time = time(end_hour, end_min)

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed={"start": start_time, "end": end_time},
            metadata={
                "overnight": start_time > end_time,
            },
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if current time is within allowed window.

        Expected context keys:
        - current_time: datetime object (defaults to now)

        Args:
            constraint: Parsed time window constraint
            context: Execution context with current_time

        Returns:
            ConstraintCheckResult with satisfaction status
        """
        start_time = constraint.parsed["start"]
        end_time = constraint.parsed["end"]

        # CARE-045: Use server time by default. Context-provided time is only
        # used for testing/debugging and must be a valid datetime or time object.
        current = context.get("current_time")
        if isinstance(current, datetime):
            # Ensure timezone-aware; if naive, assume UTC
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            current_time = current.time()
        elif isinstance(current, time):
            current_time = current
        else:
            # Default to actual server time (secure default)
            current_time = datetime.now(timezone.utc).time()

        overnight = constraint.metadata.get("overnight", False)

        if overnight:
            # Window crosses midnight (e.g., 22:00-06:00)
            # At exactly start_time or end_time, access is allowed (inclusive)
            satisfied = current_time >= start_time or current_time <= end_time
        else:
            # Normal window (inclusive boundaries)
            satisfied = start_time <= current_time <= end_time

        return ConstraintCheckResult(
            satisfied=satisfied,
            reason="within time window" if satisfied else "outside time window",
        )

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        """
        Validate that child time window is a subset of parent.

        A tighter time window means:
        - Child start >= parent start (starts later or same)
        - Child end <= parent end (ends earlier or same)

        For overnight windows, this is more complex and may not be fully
        supported in this version.

        Args:
            parent: Parent time window constraint
            child: Child time window constraint

        Returns:
            True if child is valid tightening of parent
        """
        parent_start = parent.parsed["start"]
        parent_end = parent.parsed["end"]
        child_start = child.parsed["start"]
        child_end = child.parsed["end"]

        parent_overnight = parent.metadata.get("overnight", False)
        child_overnight = child.metadata.get("overnight", False)

        # Simple case: neither is overnight
        if not parent_overnight and not child_overnight:
            return child_start >= parent_start and child_end <= parent_end

        # If parent is not overnight but child is, invalid (child would be larger)
        if not parent_overnight and child_overnight:
            return False

        # If parent is overnight and child is not, valid if child fits in one part
        if parent_overnight and not child_overnight:
            # Child must fit entirely in either the evening part or morning part
            fits_evening = child_start >= parent_start  # Child starts in evening portion
            fits_morning = child_end <= parent_end  # Child ends in morning portion
            return fits_evening or fits_morning

        # Both overnight: child must be subset
        return child_start >= parent_start and child_end <= parent_end


class ResourceDimension(ConstraintDimension):
    """
    Constraint dimension for resource access patterns.

    Uses glob patterns to specify allowed resources. Supports standard
    glob patterns like "*.txt", "data/**", "logs/app-*.log".

    Security Notes:
        - Path traversal (../) is blocked
        - Null bytes are blocked
        - Case-sensitive matching is used (fnmatchcase)
        - Overly permissive patterns (just "*" or "**") are rejected

    Example:
        dimension = ResourceDimension()
        constraint = dimension.parse(["data/**", "logs/*.log"])
        result = dimension.check(constraint, {"resource_requested": "data/users.json"})
    """

    # Patterns that are too permissive and match everything
    _OVERLY_PERMISSIVE_PATTERNS = frozenset({"*", "**", "***"})

    @property
    def name(self) -> str:
        return "resources"

    @property
    def description(self) -> str:
        return "Allowed resource patterns (glob syntax)"

    def _is_overly_permissive(self, pattern: str) -> bool:
        """
        Check if a pattern is overly permissive.

        Args:
            pattern: The glob pattern to check

        Returns:
            True if the pattern matches everything (too permissive)
        """
        stripped = pattern.strip()
        return stripped in self._OVERLY_PERMISSIVE_PATTERNS

    def _validate_resource_path(self, resource: str) -> Optional[str]:
        """
        Validate and sanitize a resource path for security.

        Checks for:
        - Path traversal attempts (..)
        - Null byte injection
        - Other malicious patterns

        Args:
            resource: The resource path to validate

        Returns:
            Error message if validation fails, None if valid
        """
        # Check for null bytes (could be used to truncate paths)
        if "\x00" in resource:
            return "resource path contains null byte"

        # Check for path traversal attempts
        # Split by both forward and backslash for cross-platform safety
        parts = resource.replace("\\", "/").split("/")
        for part in parts:
            if part == "..":
                return "resource path contains path traversal (..)"

        return None

    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse resource patterns.

        Args:
            value: Single pattern string or list of patterns

        Returns:
            ConstraintValue with list of patterns

        Raises:
            ValueError: If patterns are invalid or overly permissive
        """
        if isinstance(value, str):
            patterns = [value]
        elif isinstance(value, (list, tuple)):
            patterns = list(value)
        else:
            raise ValueError(f"Resource patterns must be string or list: {value}")

        # Validate patterns are strings and not overly permissive
        for p in patterns:
            if not isinstance(p, str):
                raise ValueError(f"Resource pattern must be a string: {p}")

            # Reject overly permissive patterns that match everything
            if self._is_overly_permissive(p):
                raise ValueError(
                    f"Resource pattern '{p}' is too permissive and matches everything. "
                    "Use a more specific pattern like 'data/*' or 'logs/**'."
                )

            # Warn about patterns that could be dangerous (but don't reject)
            if "**" in p:
                logger.warning(
                    f"Resource pattern '{p}' uses '**' which matches across directories. Ensure this is intentional."
                )

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=patterns,
            metadata={"pattern_count": len(patterns)},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if requested resource matches allowed patterns.

        Security checks performed:
        - Path traversal detection (..)
        - Null byte detection
        - Case-sensitive pattern matching

        Expected context keys:
        - resource_requested: Resource path to check

        Args:
            constraint: Parsed resource patterns
            context: Execution context with resource_requested

        Returns:
            ConstraintCheckResult with satisfaction status
        """
        patterns = constraint.parsed
        resource = context.get("resource_requested", "")

        if not resource:
            return ConstraintCheckResult(
                satisfied=True,
                reason="no resource requested",
            )

        # Security: Validate the resource path before matching
        validation_error = self._validate_resource_path(resource)
        if validation_error:
            logger.warning(f"Resource path security violation: {validation_error} (resource: {resource!r})")
            return ConstraintCheckResult(
                satisfied=False,
                reason=f"security violation: {validation_error}",
            )

        # Check if resource matches any pattern using case-sensitive matching
        for pattern in patterns:
            if fnmatch.fnmatchcase(resource, pattern):
                return ConstraintCheckResult(
                    satisfied=True,
                    reason=f"matches pattern: {pattern}",
                )

        return ConstraintCheckResult(
            satisfied=False,
            reason=f"resource '{resource}' does not match any allowed pattern",
        )

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        """
        Validate that child patterns are subset of parent patterns.

        Each child pattern must match a subset of what parent patterns match.
        This is approximated by checking if each child pattern is either:
        1. Identical to a parent pattern, or
        2. More specific (has more specific path components)

        Args:
            parent: Parent resource patterns
            child: Child resource patterns

        Returns:
            True if child is valid tightening of parent
        """
        parent_patterns: List[str] = parent.parsed
        child_patterns: List[str] = child.parsed

        # Each child pattern must be "covered" by a parent pattern
        for child_pattern in child_patterns:
            covered = False
            for parent_pattern in parent_patterns:
                # Exact match
                if child_pattern == parent_pattern:
                    covered = True
                    break
                # Child is more specific if it would only match
                # things the parent would also match
                # Approximation: check if child matches parent pattern
                # Use fnmatchcase for case-sensitive matching
                if fnmatch.fnmatchcase(child_pattern, parent_pattern):
                    covered = True
                    break
                # Check if parent is a wildcard that covers child
                # Note: overly permissive patterns like "*" are now rejected in parse()
                if "**" in parent_pattern:
                    # Parent allows anything in subtree, so child is covered
                    if fnmatch.fnmatchcase(child_pattern, parent_pattern):
                        covered = True
                        break

            if not covered:
                # Try reverse check: does parent pattern cover child pattern?
                # This handles cases like parent="data/**" child="data/users/*"
                for parent_pattern in parent_patterns:
                    # If parent ends with /** or /*, it might cover child
                    if parent_pattern.endswith("/**"):
                        base = parent_pattern[:-3]
                        if child_pattern.startswith(base):
                            covered = True
                            break
                    elif parent_pattern.endswith("/*"):
                        base = parent_pattern[:-2]
                        if child_pattern.startswith(base + "/"):
                            covered = True
                            break

            if not covered:
                return False

        return True


class RateLimitDimension(ConstraintDimension):
    """
    Constraint dimension for rate limiting.

    Supports integer limits or "N/period" format (e.g., "100/minute", "1000/hour").

    Example:
        dimension = RateLimitDimension()
        constraint = dimension.parse("100/minute")
        result = dimension.check(constraint, {"requests_in_period": 50})
    """

    VALID_PERIODS = {"second", "minute", "hour", "day"}

    @property
    def name(self) -> str:
        return "rate_limit"

    @property
    def description(self) -> str:
        return "Request rate limit (count or count/period)"

    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse rate limit value.

        Args:
            value: Integer or "N/period" string (e.g., "100/minute")

        Returns:
            ConstraintValue with parsed limit and optional period

        Raises:
            ValueError: If format is invalid
        """
        if isinstance(value, (int, float)):
            return ConstraintValue(
                dimension=self.name,
                raw_value=value,
                parsed={"limit": int(value), "period": None},
                metadata={},
            )

        if isinstance(value, str):
            # Try to parse as "N/period"
            if "/" in value:
                parts = value.split("/", 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid rate limit format: {value}")

                try:
                    limit = int(parts[0].strip())
                except ValueError as e:
                    raise ValueError(f"Invalid rate limit count: {parts[0]}") from e

                period = parts[1].strip().lower()
                if period not in self.VALID_PERIODS:
                    raise ValueError(f"Invalid period: {period}. Valid periods: {self.VALID_PERIODS}")

                return ConstraintValue(
                    dimension=self.name,
                    raw_value=value,
                    parsed={"limit": limit, "period": period},
                    metadata={},
                )
            else:
                # Try as plain integer
                try:
                    limit = int(value.strip())
                    return ConstraintValue(
                        dimension=self.name,
                        raw_value=value,
                        parsed={"limit": limit, "period": None},
                        metadata={},
                    )
                except ValueError as e:
                    raise ValueError(f"Invalid rate limit: {value}") from e

        raise ValueError(f"Rate limit must be int or string: {value}")

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if request count is within rate limit.

        Expected context keys:
        - requests_in_period: Number of requests in current period

        Args:
            constraint: Parsed rate limit constraint
            context: Execution context with requests_in_period

        Returns:
            ConstraintCheckResult with satisfaction status
        """
        limit = constraint.parsed["limit"]
        used = context.get("requests_in_period", 0)

        try:
            used = int(used)
        except (TypeError, ValueError):
            used = 0

        remaining = max(0, limit - used)
        satisfied = used <= limit

        return ConstraintCheckResult(
            satisfied=satisfied,
            reason="within rate limit" if satisfied else f"exceeded by {used - limit}",
            remaining=float(remaining),
            used=float(used),
            limit=float(limit),
        )


class DataAccessDimension(ConstraintDimension):
    """
    Constraint dimension for data access controls.

    Controls access based on data classification and PII status.
    Supports modes: "no_pii", "internal_only", or detailed dict config.

    This dimension requires audit logging due to data sensitivity.

    Example:
        dimension = DataAccessDimension()
        constraint = dimension.parse("no_pii")
        result = dimension.check(constraint, {"contains_pii": True})
        assert not result.satisfied  # PII access blocked
    """

    VALID_MODES = {"no_pii", "internal_only", "allow_all"}

    @property
    def name(self) -> str:
        return "data_access"

    @property
    def description(self) -> str:
        return "Data access restrictions (PII, classification)"

    @property
    def requires_audit(self) -> bool:
        return True

    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse data access configuration.

        Args:
            value: String mode ("no_pii", "internal_only") or dict config

        Returns:
            ConstraintValue with parsed access rules

        Raises:
            ValueError: If configuration is invalid
        """
        if isinstance(value, str):
            mode = value.lower().strip()
            if mode not in self.VALID_MODES:
                raise ValueError(f"Invalid data access mode: {mode}. Valid modes: {self.VALID_MODES}")
            return ConstraintValue(
                dimension=self.name,
                raw_value=value,
                parsed={"mode": mode},
                metadata={},
            )

        if isinstance(value, dict):
            mode = value.get("mode", "no_pii")
            if mode not in self.VALID_MODES:
                raise ValueError(f"Invalid data access mode: {mode}")

            allowed_classifications = value.get("allowed_classifications", [])
            if not isinstance(allowed_classifications, (list, tuple)):
                allowed_classifications = [allowed_classifications]

            return ConstraintValue(
                dimension=self.name,
                raw_value=value,
                parsed={
                    "mode": mode,
                    "allowed_classifications": list(allowed_classifications),
                },
                metadata={},
            )

        raise ValueError(f"Data access config must be string or dict: {value}")

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if data access is allowed.

        Expected context keys:
        - contains_pii: Boolean indicating PII presence
        - data_classification: Classification level (e.g., "internal", "external")

        Args:
            constraint: Parsed data access constraint
            context: Execution context with data attributes

        Returns:
            ConstraintCheckResult with satisfaction status
        """
        mode = constraint.parsed.get("mode", "no_pii")
        contains_pii = context.get("contains_pii", False)
        classification = context.get("data_classification", "external")

        if mode == "no_pii":
            if contains_pii:
                return ConstraintCheckResult(
                    satisfied=False,
                    reason="PII access not allowed",
                )
            return ConstraintCheckResult(
                satisfied=True,
                reason="no PII present",
            )

        if mode == "internal_only":
            if classification not in ("internal", "restricted"):
                return ConstraintCheckResult(
                    satisfied=False,
                    reason=f"classification '{classification}' not allowed",
                )
            return ConstraintCheckResult(
                satisfied=True,
                reason="internal data access allowed",
            )

        if mode == "allow_all":
            # Check allowed classifications if specified
            allowed = constraint.parsed.get("allowed_classifications", [])
            if allowed and classification not in allowed:
                return ConstraintCheckResult(
                    satisfied=False,
                    reason=f"classification '{classification}' not in allowed list",
                )
            return ConstraintCheckResult(
                satisfied=True,
                reason="data access allowed",
            )

        return ConstraintCheckResult(
            satisfied=False,
            reason=f"unknown mode: {mode}",
        )


class CommunicationDimension(ConstraintDimension):
    """
    Constraint dimension for external communication controls.

    Controls what external communications an agent can make.
    Supports modes: "none", "internal_only", or allowed_domains list.

    Example:
        dimension = CommunicationDimension()
        constraint = dimension.parse({"mode": "internal_only"})
        result = dimension.check(
            constraint,
            {"communication_target": "external.api.com"}
        )
        assert not result.satisfied  # External blocked
    """

    VALID_MODES = {"none", "internal_only", "allowed_domains"}

    @property
    def name(self) -> str:
        return "communication"

    @property
    def description(self) -> str:
        return "External communication restrictions"

    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse communication configuration.

        Args:
            value: String mode or dict with mode and allowed_domains

        Returns:
            ConstraintValue with parsed communication rules

        Raises:
            ValueError: If configuration is invalid
        """
        if isinstance(value, str):
            mode = value.lower().strip()
            if mode not in self.VALID_MODES:
                raise ValueError(f"Invalid communication mode: {mode}. Valid modes: {self.VALID_MODES}")
            return ConstraintValue(
                dimension=self.name,
                raw_value=value,
                parsed={"mode": mode, "allowed_domains": []},
                metadata={},
            )

        if isinstance(value, dict):
            mode = value.get("mode", "none")
            if mode not in self.VALID_MODES:
                raise ValueError(f"Invalid communication mode: {mode}")

            allowed_domains = value.get("allowed_domains", [])
            if not isinstance(allowed_domains, (list, tuple)):
                allowed_domains = [allowed_domains]

            return ConstraintValue(
                dimension=self.name,
                raw_value=value,
                parsed={
                    "mode": mode,
                    "allowed_domains": [d.lower() for d in allowed_domains],
                },
                metadata={},
            )

        raise ValueError(f"Communication config must be string or dict: {value}")

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if communication is allowed.

        Expected context keys:
        - communication_target: Target domain or address

        Args:
            constraint: Parsed communication constraint
            context: Execution context with communication_target

        Returns:
            ConstraintCheckResult with satisfaction status
        """
        mode = constraint.parsed.get("mode", "none")
        target = context.get("communication_target", "")

        if not target:
            return ConstraintCheckResult(
                satisfied=True,
                reason="no communication target",
            )

        target_lower = target.lower()

        if mode == "none":
            return ConstraintCheckResult(
                satisfied=False,
                reason="all external communication blocked",
            )

        if mode == "internal_only":
            # Check if target is internal (simplified check)
            internal_patterns = [".internal.", ".local.", "localhost", "127.0.0.1"]
            is_internal = any(p in target_lower for p in internal_patterns)

            if not is_internal:
                return ConstraintCheckResult(
                    satisfied=False,
                    reason=f"external target '{target}' not allowed",
                )
            return ConstraintCheckResult(
                satisfied=True,
                reason="internal communication allowed",
            )

        if mode == "allowed_domains":
            allowed = constraint.parsed.get("allowed_domains", [])

            # Check if target matches any allowed domain
            for domain in allowed:
                if domain in target_lower or target_lower.endswith("." + domain):
                    return ConstraintCheckResult(
                        satisfied=True,
                        reason=f"target matches allowed domain: {domain}",
                    )

            return ConstraintCheckResult(
                satisfied=False,
                reason=f"target '{target}' not in allowed domains",
            )

        return ConstraintCheckResult(
            satisfied=False,
            reason=f"unknown mode: {mode}",
        )


def register_builtin_dimensions(registry: "ConstraintDimensionRegistry") -> None:
    """
    Register all built-in constraint dimensions with a registry.

    This is a convenience function to register all six built-in dimensions.
    Since they are built-in, they will be auto-approved.

    Args:
        registry: Registry to register dimensions with

    Example:
        from eatp.constraints import ConstraintDimensionRegistry
        from eatp.constraints.builtin import register_builtin_dimensions

        registry = ConstraintDimensionRegistry()
        register_builtin_dimensions(registry)
    """
    registry.register(CostLimitDimension())
    registry.register(TimeDimension())
    registry.register(ResourceDimension())
    registry.register(RateLimitDimension())
    registry.register(DataAccessDimension())
    registry.register(CommunicationDimension())
