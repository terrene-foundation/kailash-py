# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Constraint validation for EATP delegations.

Ensures that delegations can only TIGHTEN constraints, never loosen them.
This is a fundamental security property of EATP - trust can only be
reduced as it flows through the delegation chain.

Key Principle: A delegation can only REMOVE permissions, never ADD them.

Supported Constraints:
- cost_limit: Child must be <= parent
- time_window: Child must be subset of parent
- resources: Child must be subset of parent (glob matching)
- rate_limit: Child must be <= parent
- geo_restrictions: Child must be subset of parent

Reference: docs/plans/eatp-integration/04-gap-analysis.md (G4)

Author: Kaizen Framework Team
Created: 2026-01-02
"""

import logging
import re as _re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConstraintViolation(str, Enum):
    """
    Types of constraint violations.

    Each violation type indicates a specific way constraints were loosened.
    """

    COST_LOOSENED = "cost_limit_increased"
    TIME_WINDOW_EXPANDED = "time_window_expanded"
    RESOURCES_EXPANDED = "resources_expanded"
    RATE_LIMIT_INCREASED = "rate_limit_increased"
    GEO_RESTRICTION_REMOVED = "geo_restriction_removed"
    BUDGET_LIMIT_INCREASED = "budget_limit_increased"
    ACTION_RESTRICTION_REMOVED = "action_restriction_removed"
    MAX_DELEGATION_DEPTH_INCREASED = "max_delegation_depth_increased"
    # CARE-009: Additional violation types for inheritance validation
    FORBIDDEN_ACTION_REMOVED = "forbidden_action_removed"
    DATA_SCOPE_EXPANDED = "data_scope_expanded"
    COMMUNICATION_TARGETS_EXPANDED = "communication_targets_expanded"
    MAX_API_CALLS_INCREASED = "max_api_calls_increased"
    NESTED_CONSTRAINT_WIDENED = "nested_constraint_widened"


@dataclass
class ValidationResult:
    """
    Result of constraint validation.

    Attributes:
        valid: True if all constraints are properly tightened
        violations: List of specific violations found
        details: Detailed messages for each violation
    """

    valid: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    details: Dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Allow using result directly in boolean context."""
        return self.valid


class ConstraintValidator:
    """
    Validates that child constraints are strictly tighter than parent.

    Rule: A delegation can only REMOVE permissions, never ADD them.

    This validator checks various constraint types to ensure that
    when trust is delegated, the delegatee cannot have more permissions
    than the delegator.

    Supported constraints:
    - cost_limit: Child must be <= parent
    - time_window: Child must be subset of parent (format: "HH:MM-HH:MM")
    - resources: Child must be subset of parent (glob matching)
    - rate_limit: Child must be <= parent
    - geo_restrictions: Child must be subset of parent
    - budget_limit: Child must be <= parent
    - max_delegation_depth: Child must be <= parent

    Example:
        >>> validator = ConstraintValidator()
        >>>
        >>> # Valid: tightening constraints
        >>> result = validator.validate_tightening(
        ...     parent_constraints={"cost_limit": 10000},
        ...     child_constraints={"cost_limit": 1000}  # Lower = tighter
        ... )
        >>> assert result.valid is True
        >>>
        >>> # Invalid: loosening constraints
        >>> result = validator.validate_tightening(
        ...     parent_constraints={"cost_limit": 1000},
        ...     child_constraints={"cost_limit": 10000}  # Higher = loosened!
        ... )
        >>> assert result.valid is False
        >>> assert ConstraintViolation.COST_LOOSENED in result.violations
    """

    def __init__(self, strict_mode: bool = True):
        """
        Initialize validator.

        Args:
            strict_mode: If True, fail on any unknown constraint types.
                        If False, skip unknown constraints with a warning.
        """
        self._strict_mode = strict_mode

    def validate_tightening(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate that child constraints are subset of parent.

        Args:
            parent_constraints: Constraints of the delegator
            child_constraints: Constraints for the delegatee

        Returns:
            ValidationResult with any violations found
        """
        violations: List[ConstraintViolation] = []
        details: Dict[str, str] = {}

        # Check cost limit
        if "cost_limit" in child_constraints:
            parent_limit = parent_constraints.get("cost_limit", float("inf"))
            child_limit = child_constraints["cost_limit"]
            if child_limit > parent_limit:
                violations.append(ConstraintViolation.COST_LOOSENED)
                details["cost_limit"] = f"Child {child_limit} > Parent {parent_limit}"

        # Check budget limit (similar to cost_limit but for different domain)
        if "budget_limit" in child_constraints:
            parent_limit = parent_constraints.get("budget_limit", float("inf"))
            child_limit = child_constraints["budget_limit"]
            if child_limit > parent_limit:
                violations.append(ConstraintViolation.BUDGET_LIMIT_INCREASED)
                details["budget_limit"] = f"Child {child_limit} > Parent {parent_limit}"

        # Check time window
        if "time_window" in child_constraints:
            parent_window = parent_constraints.get("time_window")
            if parent_window and not self._is_time_subset(
                parent_window, child_constraints["time_window"]
            ):
                violations.append(ConstraintViolation.TIME_WINDOW_EXPANDED)
                details["time_window"] = (
                    f"Child window '{child_constraints['time_window']}' not within parent window '{parent_window}'"
                )

        # Check resources
        if "resources" in child_constraints:
            parent_resources = parent_constraints.get("resources", [])
            if parent_resources and not self._is_resource_subset(
                parent_resources, child_constraints["resources"]
            ):
                violations.append(ConstraintViolation.RESOURCES_EXPANDED)
                details["resources"] = "Child resources not subset of parent"

        # Check rate limit
        if "rate_limit" in child_constraints:
            parent_rate = parent_constraints.get("rate_limit", float("inf"))
            child_rate = child_constraints["rate_limit"]
            if child_rate > parent_rate:
                violations.append(ConstraintViolation.RATE_LIMIT_INCREASED)
                details["rate_limit"] = f"Child {child_rate} > Parent {parent_rate}"

        # Check geo restrictions
        if "geo_restrictions" in parent_constraints:
            parent_geo = set(parent_constraints["geo_restrictions"])
            child_geo = set(child_constraints.get("geo_restrictions", []))
            # If child has geo restrictions, they must be subset of parent
            if child_geo and not child_geo.issubset(parent_geo):
                violations.append(ConstraintViolation.GEO_RESTRICTION_REMOVED)
                added_regions = child_geo - parent_geo
                details["geo_restrictions"] = (
                    f"Child adds regions not in parent: {added_regions}"
                )

        # Check max delegation depth
        if "max_delegation_depth" in child_constraints:
            parent_depth = parent_constraints.get("max_delegation_depth", float("inf"))
            child_depth = child_constraints["max_delegation_depth"]
            if child_depth > parent_depth:
                violations.append(ConstraintViolation.MAX_DELEGATION_DEPTH_INCREASED)
                details["max_delegation_depth"] = (
                    f"Child {child_depth} > Parent {parent_depth}"
                )

        # Check action restrictions (allowed_actions must be subset)
        if "allowed_actions" in parent_constraints:
            parent_actions = set(parent_constraints["allowed_actions"])
            child_actions = set(child_constraints.get("allowed_actions", []))
            if child_actions and not child_actions.issubset(parent_actions):
                violations.append(ConstraintViolation.ACTION_RESTRICTION_REMOVED)
                added_actions = child_actions - parent_actions
                details["allowed_actions"] = (
                    f"Child adds actions not in parent: {added_actions}"
                )

        return ValidationResult(
            valid=len(violations) == 0,
            violations=violations,
            details=details,
        )

    def _is_time_subset(self, parent_window: str, child_window: str) -> bool:
        """
        Check if child time window is within parent.

        Time windows are in format "HH:MM-HH:MM" (24-hour format).
        Child is valid if its start >= parent start AND its end <= parent end.

        Args:
            parent_window: Parent's time window (e.g., "09:00-17:00")
            child_window: Child's time window (e.g., "10:00-16:00")

        Returns:
            True if child window is within parent window
        """
        try:
            p_start, p_end = self._parse_time_window(parent_window)
            c_start, c_end = self._parse_time_window(child_window)
            return c_start >= p_start and c_end <= p_end
        except Exception as e:
            logger.warning(f"Failed to parse time windows: {e}")
            return False  # Invalid format = not a subset

    def _is_resource_subset(
        self,
        parent_resources: List[str],
        child_resources: List[str],
    ) -> bool:
        """
        Check if child resources are subset of parent (with glob matching).

        Each child resource must match at least one parent pattern.

        Args:
            parent_resources: Parent's resource patterns (may include globs)
            child_resources: Child's resource patterns

        Returns:
            True if all child resources match parent patterns

        Example:
            >>> validator._is_resource_subset(
            ...     ["invoices/*"], ["invoices/small/*"]
            ... )
            True
            >>> validator._is_resource_subset(
            ...     ["invoices/small/*"], ["invoices/*"]  # Expanded!
            ... )
            False
        """
        for child_res in child_resources:
            # Child resource must match at least one parent pattern
            if not any(
                self._glob_match(parent, child_res) for parent in parent_resources
            ):
                return False
        return True

    def _glob_match(self, pattern: str, path: str) -> bool:
        """
        Check if path matches glob pattern using path-aware semantics.

        Supports:
        - * matches any characters within a single path segment (not /)
        - ** matches across path segments (including /)
        - ? matches a single non-/ character

        Security: fnmatch.fnmatch treats * as matching / which would allow
        resource expansion attacks. We convert to regex instead.

        Args:
            pattern: Glob pattern
            path: Path to match

        Returns:
            True if path matches pattern
        """
        # Convert glob pattern to regex with path-aware semantics
        # Process ** first (before * is consumed)
        i = 0
        regex = "^"
        while i < len(pattern):
            if i + 1 < len(pattern) and pattern[i] == "*" and pattern[i + 1] == "*":
                regex += ".*"  # ** matches everything including /
                i += 2
                # Skip trailing slash after **
                if i < len(pattern) and pattern[i] == "/":
                    regex += "/?"
                    i += 1
            elif pattern[i] == "*":
                regex += "[^/]*"  # * matches within segment only
                i += 1
            elif pattern[i] == "?":
                regex += "[^/]"  # ? matches single non-/ char
                i += 1
            else:
                regex += _re.escape(pattern[i])
                i += 1
        regex += "$"

        return bool(_re.match(regex, path))

    def _parse_time_window(self, window: str) -> Tuple[int, int]:
        """
        Parse time window "HH:MM-HH:MM" to minutes from midnight.

        Args:
            window: Time window string (e.g., "09:00-17:00")

        Returns:
            Tuple of (start_minutes, end_minutes) from midnight

        Raises:
            ValueError: If format is invalid
        """
        parts = window.split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid time window format: {window}")

        start = self._time_to_minutes(parts[0].strip())
        end = self._time_to_minutes(parts[1].strip())
        return start, end

    def _time_to_minutes(self, time_str: str) -> int:
        """
        Convert HH:MM to minutes from midnight.

        Args:
            time_str: Time string (e.g., "09:00", "17:30")

        Returns:
            Minutes from midnight
        """
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {time_str}")

        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"Invalid time values: {time_str}")

        return h * 60 + m

    # =========================================================================
    # CARE-009: Constraint Inheritance Validation
    # =========================================================================

    def validate_inheritance(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate child constraints properly inherit and can only tighten.

        CARE-009: Widening Attack Prevention.
        This is a fundamental security property of EATP - trust can only be
        reduced as it flows through the delegation chain.

        Rules enforced:
        - Child cannot ADD new allowed_actions not in parent
        - Child cannot INCREASE numeric limits (cost, rate, budget, depth, api_calls)
        - Child cannot EXPAND resource scopes
        - Child cannot REMOVE restrictions (forbidden_actions)
        - Child time windows must be within parent time windows
        - Child data scopes must be subset of parent data scopes
        - Child communication targets must be subset of parent targets

        Args:
            parent_constraints: Constraints of the parent (delegator)
            child_constraints: Constraints for the child (delegatee)

        Returns:
            ValidationResult with any violations found

        Example:
            >>> validator = ConstraintValidator()
            >>>
            >>> # Valid: tightening constraints
            >>> result = validator.validate_inheritance(
            ...     parent_constraints={"cost_limit": 10000, "rate_limit": 100},
            ...     child_constraints={"cost_limit": 5000, "rate_limit": 50}
            ... )
            >>> assert result.valid is True
            >>>
            >>> # Invalid: widening attack
            >>> result = validator.validate_inheritance(
            ...     parent_constraints={"cost_limit": 1000},
            ...     child_constraints={"cost_limit": 10000}  # Widened!
            ... )
            >>> assert result.valid is False
            >>> assert ConstraintViolation.COST_LOOSENED in result.violations
        """
        violations: List[ConstraintViolation] = []
        details: Dict[str, str] = {}

        # If parent has no constraints, any child constraints are valid
        # (they can only add restrictions, not remove them)
        if not parent_constraints:
            return ValidationResult(valid=True, violations=[], details={})

        # Validate numeric limits (child must be <= parent)
        self._validate_numeric_limits(
            parent_constraints, child_constraints, violations, details
        )

        # Validate allowed actions (child must be subset)
        self._validate_allowed_actions(
            parent_constraints, child_constraints, violations, details
        )

        # Validate forbidden actions (parent's must be preserved)
        self._validate_forbidden_actions(
            parent_constraints, child_constraints, violations, details
        )

        # Validate resource scopes (child must be subset)
        self._validate_resource_scopes(
            parent_constraints, child_constraints, violations, details
        )

        # Validate time windows (child must be within parent)
        self._validate_time_windows(
            parent_constraints, child_constraints, violations, details
        )

        # Validate data scopes (child must be subset)
        self._validate_data_scopes(
            parent_constraints, child_constraints, violations, details
        )

        # Validate communication limits (child cannot have more targets)
        self._validate_communication_limits(
            parent_constraints, child_constraints, violations, details
        )

        # Validate nested constraints recursively
        self._validate_nested_constraints(
            parent_constraints, child_constraints, violations, details
        )

        return ValidationResult(
            valid=len(violations) == 0,
            violations=violations,
            details=details,
        )

    def _validate_numeric_limits(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
    ) -> None:
        """
        Validate that numeric limits are not increased (child <= parent).

        Checks: cost_limit, rate_limit, budget_limit, max_delegation_depth, max_api_calls
        """
        numeric_fields = [
            ("cost_limit", ConstraintViolation.COST_LOOSENED),
            ("rate_limit", ConstraintViolation.RATE_LIMIT_INCREASED),
            ("budget_limit", ConstraintViolation.BUDGET_LIMIT_INCREASED),
            (
                "max_delegation_depth",
                ConstraintViolation.MAX_DELEGATION_DEPTH_INCREASED,
            ),
            ("max_api_calls", ConstraintViolation.MAX_API_CALLS_INCREASED),
        ]

        for field_name, violation_type in numeric_fields:
            error_msg = self._check_numeric_tightening(
                parent_constraints.get(field_name),
                child_constraints.get(field_name),
                field_name,
            )
            if error_msg:
                violations.append(violation_type)
                details[field_name] = error_msg

    def _check_numeric_tightening(
        self,
        parent_val: Any,
        child_val: Any,
        field_name: str,
    ) -> Optional[str]:
        """
        Check if a numeric constraint is properly tightened.

        Args:
            parent_val: Parent's value (may be None)
            child_val: Child's value (may be None)
            field_name: Name of the field for error messages

        Returns:
            Error message if widening detected, None if valid
        """
        # If child doesn't specify this constraint, it's valid (inherits parent's)
        if child_val is None:
            return None

        # If parent doesn't specify but child does, valid (child adds restriction)
        if parent_val is None:
            return None

        try:
            parent_num = float(parent_val)
            child_num = float(child_val)
        except (TypeError, ValueError):
            # Non-numeric values: can't validate numerically
            return None

        if child_num > parent_num:
            return f"Child {child_num} exceeds parent {parent_num}"

        return None

    def _validate_allowed_actions(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
    ) -> None:
        """
        Validate that allowed_actions in child are subset of parent.

        Child cannot add actions that parent doesn't allow.
        """
        if "allowed_actions" not in parent_constraints:
            # Parent doesn't restrict, child can specify any
            return

        parent_actions = set(parent_constraints.get("allowed_actions", []))
        child_actions = set(child_constraints.get("allowed_actions", []))

        # If child specifies actions, they must be subset of parent's
        if child_actions:
            added_actions = child_actions - parent_actions
            if added_actions:
                violations.append(ConstraintViolation.ACTION_RESTRICTION_REMOVED)
                details["allowed_actions"] = (
                    f"Child adds actions not in parent: {added_actions}"
                )

    def _validate_forbidden_actions(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
    ) -> None:
        """
        Validate that parent's forbidden_actions are preserved in child.

        Child cannot remove restrictions that parent has set.
        """
        if "forbidden_actions" not in parent_constraints:
            # Parent doesn't forbid anything
            return

        parent_forbidden = set(parent_constraints.get("forbidden_actions", []))
        child_forbidden = set(child_constraints.get("forbidden_actions", []))

        # All parent's forbidden actions must be in child's forbidden list
        removed_forbidden = parent_forbidden - child_forbidden
        if removed_forbidden:
            violations.append(ConstraintViolation.FORBIDDEN_ACTION_REMOVED)
            details["forbidden_actions"] = (
                f"Parent's forbidden actions removed: {removed_forbidden}"
            )

    def _validate_resource_scopes(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
    ) -> None:
        """
        Validate that child resource scopes are subset of parent.
        """
        if "resources" not in parent_constraints:
            # Parent doesn't restrict resources
            return

        parent_resources = parent_constraints.get("resources", [])
        child_resources = child_constraints.get("resources", [])

        # Normalize to lists
        if isinstance(parent_resources, str):
            parent_resources = [parent_resources]
        if isinstance(child_resources, str):
            child_resources = [child_resources]

        # If parent has resources but child is empty, child inherits parent's (OK)
        if not child_resources:
            return

        # Check if child resources are subset of parent
        if not self._is_resource_subset_strict(parent_resources, child_resources):
            violations.append(ConstraintViolation.RESOURCES_EXPANDED)
            details["resources"] = (
                f"Child resources not subset of parent. Parent: {parent_resources}, Child: {child_resources}"
            )

    def _is_resource_subset_strict(
        self,
        parent_resources: List[str],
        child_resources: List[str],
    ) -> bool:
        """
        Check if child resources are strictly a subset of parent resources.

        Each child resource must be "covered" by at least one parent resource.
        A child resource is covered if:
        1. It matches a parent pattern exactly
        2. It is more specific than a parent pattern

        Args:
            parent_resources: Parent's resource patterns
            child_resources: Child's resource patterns

        Returns:
            True if all child resources are covered by parent
        """
        for child_res in child_resources:
            covered = False
            for parent_res in parent_resources:
                # Exact match
                if child_res == parent_res:
                    covered = True
                    break

                # Child matches parent pattern (child is more specific)
                if self._glob_match(parent_res, child_res):
                    covered = True
                    break

                # Check if parent with wildcard covers child
                if parent_res.endswith("/**"):
                    base = parent_res[:-3]
                    if child_res.startswith(base):
                        covered = True
                        break
                elif parent_res.endswith("/*"):
                    base = parent_res[:-2]
                    if child_res.startswith(base + "/"):
                        covered = True
                        break
                elif parent_res == "*" or parent_res == "**":
                    covered = True
                    break

            if not covered:
                return False

        return True

    def _validate_time_windows(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
    ) -> None:
        """
        Validate that child time windows are within parent time windows.
        """
        if "time_window" not in parent_constraints:
            return

        parent_window = parent_constraints.get("time_window")
        child_window = child_constraints.get("time_window")

        if not child_window:
            # Child inherits parent's time window (OK)
            return

        if parent_window is None or not self._is_time_window_within(
            parent_window, child_window
        ):
            violations.append(ConstraintViolation.TIME_WINDOW_EXPANDED)
            details["time_window"] = (
                f"Child window '{child_window}' not within parent window '{parent_window}'"
            )

    def _is_time_window_within(
        self,
        parent_window: str,
        child_window: str,
    ) -> bool:
        """
        Check if child time window is within parent time window.

        Args:
            parent_window: Parent's time window (e.g., "09:00-17:00")
            child_window: Child's time window

        Returns:
            True if child window is within parent window
        """
        try:
            p_start, p_end = self._parse_time_window(parent_window)
            c_start, c_end = self._parse_time_window(child_window)

            # Child start must be >= parent start
            # Child end must be <= parent end
            return c_start >= p_start and c_end <= p_end
        except Exception as e:
            logger.warning(f"Failed to compare time windows: {e}")
            return False

    def _validate_data_scopes(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
    ) -> None:
        """
        Validate that child data scopes are subset of parent data scopes.
        """
        if "data_scopes" not in parent_constraints:
            return

        parent_scopes = set(parent_constraints.get("data_scopes", []))
        child_scopes = set(child_constraints.get("data_scopes", []))

        if not child_scopes:
            # Child inherits parent's scopes (OK)
            return

        # Child scopes must be subset of parent
        if not child_scopes.issubset(parent_scopes):
            added_scopes = child_scopes - parent_scopes
            violations.append(ConstraintViolation.DATA_SCOPE_EXPANDED)
            details["data_scopes"] = (
                f"Child adds data scopes not in parent: {added_scopes}"
            )

    def _validate_communication_limits(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
    ) -> None:
        """
        Validate that child communication targets are subset of parent.
        """
        if "communication_targets" not in parent_constraints:
            return

        parent_targets = set(parent_constraints.get("communication_targets", []))
        child_targets = set(child_constraints.get("communication_targets", []))

        if not child_targets:
            # Child inherits parent's targets (OK)
            return

        # Child targets must be subset of parent
        if not child_targets.issubset(parent_targets):
            added_targets = child_targets - parent_targets
            violations.append(ConstraintViolation.COMMUNICATION_TARGETS_EXPANDED)
            details["communication_targets"] = (
                f"Child adds communication targets not in parent: {added_targets}"
            )

    def _validate_nested_constraints(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
        violations: List[ConstraintViolation],
        details: Dict[str, str],
        prefix: str = "",
    ) -> None:
        """
        Recursively validate nested dict constraints.

        Handles arbitrary nesting like:
        {
            "api_limits": {
                "max_calls": 100,
                "per_endpoint": {"users": 50, "orders": 30}
            }
        }
        """
        # Find nested dicts in parent that need recursive validation
        for key, parent_value in parent_constraints.items():
            if not isinstance(parent_value, dict):
                continue

            # Skip already-handled constraint types
            if key in (
                "cost_limit",
                "rate_limit",
                "budget_limit",
                "max_delegation_depth",
                "max_api_calls",
                "allowed_actions",
                "forbidden_actions",
                "resources",
                "time_window",
                "data_scopes",
                "communication_targets",
                "geo_restrictions",
            ):
                continue

            child_value = child_constraints.get(key)
            if child_value is None:
                # Child doesn't specify this nested constraint, inherits parent's (OK)
                continue

            if not isinstance(child_value, dict):
                # Type mismatch
                full_key = f"{prefix}{key}" if prefix else key
                violations.append(ConstraintViolation.NESTED_CONSTRAINT_WIDENED)
                details[full_key] = (
                    f"Parent has dict constraint but child has {type(child_value).__name__}"
                )
                continue

            # Recursively validate nested dict
            nested_prefix = f"{prefix}{key}." if prefix else f"{key}."

            # Check for numeric values in nested dict
            for nested_key, nested_parent_val in parent_value.items():
                nested_child_val = child_value.get(nested_key)
                full_key = f"{nested_prefix}{nested_key}"

                if isinstance(nested_parent_val, (int, float)):
                    error = self._check_numeric_tightening(
                        nested_parent_val, nested_child_val, full_key
                    )
                    if error:
                        violations.append(ConstraintViolation.NESTED_CONSTRAINT_WIDENED)
                        details[full_key] = error
                elif isinstance(nested_parent_val, dict):
                    # Deeper nesting - recursive call
                    self._validate_nested_constraints(
                        {nested_key: nested_parent_val},
                        {nested_key: nested_child_val} if nested_child_val else {},
                        violations,
                        details,
                        nested_prefix,
                    )


class DelegationConstraintValidator:
    """
    High-level validator for delegation constraint checking.

    This class provides a simplified interface for validating
    constraint tightening during delegation operations.
    """

    def __init__(self):
        self._validator = ConstraintValidator()

    def validate_delegation(
        self,
        delegator_constraints: Dict[str, Any],
        delegatee_constraints: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate that a delegation maintains constraint tightening.

        Args:
            delegator_constraints: Constraints of the delegating agent
            delegatee_constraints: Constraints being given to the delegatee

        Returns:
            ValidationResult indicating if delegation is valid
        """
        return self._validator.validate_tightening(
            delegator_constraints, delegatee_constraints
        )

    def can_delegate(
        self,
        delegator_constraints: Dict[str, Any],
        delegatee_constraints: Dict[str, Any],
    ) -> bool:
        """
        Quick check if delegation would be valid.

        Args:
            delegator_constraints: Constraints of the delegating agent
            delegatee_constraints: Constraints being given to the delegatee

        Returns:
            True if delegation is valid, False otherwise
        """
        result = self.validate_delegation(delegator_constraints, delegatee_constraints)
        return result.valid

    def get_max_allowed_constraints(
        self,
        delegator_constraints: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get the maximum constraints that can be delegated.

        Returns a copy of the delegator's constraints, which represent
        the loosest constraints that can be given to a delegatee.

        Args:
            delegator_constraints: Constraints of the delegating agent

        Returns:
            Copy of delegator constraints (represents ceiling for delegatee)
        """
        return dict(delegator_constraints)
