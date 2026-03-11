"""Trust-Aware Query Wrapper for DataFlow (CARE-019).

This module provides trust integration for DataFlow queries, wrapping
database operations with EATP constraint envelopes for fine-grained
access control.

Design Principles:
    - No hard dependencies on Kaizen or Core SDK trust modules
    - Graceful degradation when trust modules not available
    - All executor methods are async for consistency
    - Thread-safe with no shared mutable state
    - Explicit error handling (never use defaults for fallbacks)

Key Classes:
    - ConstraintEnvelopeWrapper: Translates EATP constraints to SQL filters
    - TrustAwareQueryExecutor: Wraps queries with trust verification
    - QueryAccessResult: Result of constraint application
    - QueryExecutionResult: Result of query execution

Example:
    >>> wrapper = ConstraintEnvelopeWrapper()
    >>> result = wrapper.apply_constraints(constraints, columns, "read")
    >>> if result.allowed:
    ...     # Execute query with result.additional_filters
    ...     pass

Version:
    Added in: v0.11.0
    Part of: CARE-019 trust implementation
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    # Avoid hard dependencies - use TYPE_CHECKING for type annotations only
    pass

logger = logging.getLogger(__name__)


# === PII and Sensitive Column Patterns ===

# CARE-056 Security Fix: Use lookahead/lookbehind to prevent false positives.
# Without proper boundaries, patterns like "dob" would match "doberman_breed",
# "token" would match "tokenized", and "secret" would match "newsecret".
# We use (?<![a-z]) and (?![a-z]) to ensure patterns only match when NOT
# preceded or followed by a letter. This allows matching:
#   - "user_ssn" (underscore separates, ssn matches)
#   - "ssn" (standalone)
#   - "ssn_value" (underscore separates, ssn matches)
# But prevents matching:
#   - "session_id" (e-s-s-i prevents match since letters surround)
#   - "doberman_breed" (o-b-e prevents match)
#   - "tokenized" (n-i prevents match)
# This is critical for accurate PII detection with minimal false positives.

# Patterns for PII column detection (case-insensitive, with letter boundaries)
PII_COLUMN_PATTERNS = [
    r"(?<![a-z])ssn(?![a-z])",
    r"(?<![a-z])social_security(?![a-z])",
    r"(?<![a-z])social_security_number(?![a-z])",
    r"(?<![a-z])tax_id(?![a-z])",
    r"(?<![a-z])taxpayer_id(?![a-z])",
    r"(?<![a-z])dob(?![a-z])",
    r"(?<![a-z])date_of_birth(?![a-z])",
    r"(?<![a-z])passport(?![a-z])",
    r"(?<![a-z])passport_number(?![a-z])",
    r"(?<![a-z])drivers_license(?![a-z])",
    r"(?<![a-z])driver_license(?![a-z])",
    r"(?<![a-z])driver_license_number(?![a-z])",
    r"(?<![a-z])national_id(?![a-z])",
    r"(?<![a-z])national_identification(?![a-z])",
]

# Patterns for sensitive column detection (case-insensitive, with letter boundaries)
SENSITIVE_COLUMN_PATTERNS = [
    r"(?<![a-z])salary(?![a-z])",
    r"(?<![a-z])annual_salary(?![a-z])",
    r"(?<![a-z])password(?![a-z])",
    r"(?<![a-z])password_hash(?![a-z])",
    r"(?<![a-z])api_key(?![a-z])",
    r"(?<![a-z])api_secret(?![a-z])",
    r"(?<![a-z])secret(?![a-z])",
    r"(?<![a-z])client_secret(?![a-z])",
    r"(?<![a-z])token(?![a-z])",
    r"(?<![a-z])access_token(?![a-z])",
    r"(?<![a-z])refresh_token(?![a-z])",
    r"(?<![a-z])credential(?![a-z])",
    r"(?<![a-z])credentials(?![a-z])",
]


# === Constraint Types (local definitions to avoid Kaizen dependency) ===


class LocalConstraintType(Enum):
    """Local constraint type enum (mirrors Kaizen's ConstraintType)."""

    RESOURCE_LIMIT = "resource_limit"
    TIME_WINDOW = "time_window"
    DATA_SCOPE = "data_scope"
    ACTION_RESTRICTION = "action_restriction"
    AUDIT_REQUIREMENT = "audit_requirement"


# === Data Classes ===


@dataclass
class QueryAccessResult:
    """Result of applying constraints to a query.

    Captures the outcome of constraint evaluation, including which columns
    are accessible, what additional filters should be applied, and any
    columns that were filtered due to PII/sensitive data rules.

    Attributes:
        allowed: Whether the query is allowed to proceed
        filtered_columns: List of columns the agent can access
        additional_filters: Extra WHERE clause filters to apply
        row_limit: LIMIT value if applicable
        denied_reason: Reason if access denied
        applied_constraints: Descriptions of applied constraints
        pii_columns_filtered: PII columns that were removed
        sensitive_columns_flagged: Sensitive columns for audit
    """

    allowed: bool
    filtered_columns: List[str]
    additional_filters: Dict[str, Any]
    row_limit: Optional[int]
    denied_reason: Optional[str]
    applied_constraints: List[str]
    pii_columns_filtered: List[str]
    sensitive_columns_flagged: List[str]


@dataclass
class QueryExecutionResult:
    """Result of a trust-aware query execution.

    Captures the full outcome of a query including trust verification
    and constraint application.

    Attributes:
        success: Whether the query executed successfully
        data: Query results
        rows_affected: Number of rows affected/returned
        constraints_applied: List of constraint descriptions
        audit_event_id: Audit trail reference if recorded
        execution_time_ms: Execution time in milliseconds
    """

    success: bool
    data: Any
    rows_affected: int
    constraints_applied: List[str]
    audit_event_id: Optional[str]
    execution_time_ms: float


# === Constraint Envelope Wrapper ===


class ConstraintEnvelopeWrapper:
    """Translates EATP constraints to SQL filter components.

    This class handles the translation of EATP constraint values into
    formats that can be used to filter DataFlow queries.

    Supported Constraints:
        - DATA_SCOPE: Translated to WHERE clause filters
        - TIME_WINDOW: Translated to timestamp filters
        - RESOURCE_LIMIT: Extracted as row limits
        - ACTION_RESTRICTION: Enforces read_only, no_pii, etc.
        - AUDIT_REQUIREMENT: Flags for audit logging

    Example:
        >>> wrapper = ConstraintEnvelopeWrapper()
        >>> filters = wrapper.translate_data_scope("department:finance")
        >>> print(filters)
        {'department': 'finance'}
    """

    def translate_data_scope(self, constraint_value: str) -> Dict[str, Any]:
        """Convert data_scope constraint to WHERE clause dict.

        Parses constraint values like "department:finance" or
        "department:finance,region:us" into filter dictionaries.

        Args:
            constraint_value: Data scope constraint string

        Returns:
            Dictionary suitable for use as query filters

        Examples:
            >>> wrapper.translate_data_scope("department:finance")
            {'department': 'finance'}
            >>> wrapper.translate_data_scope("department:finance,region:us")
            {'department': 'finance', 'region': 'us'}
        """
        if not constraint_value or not constraint_value.strip():
            return {}

        result: Dict[str, Any] = {}

        # Split on comma for multiple constraints
        parts = constraint_value.split(",")

        for part in parts:
            part = part.strip()
            if ":" not in part:
                # Invalid format, skip
                logger.debug(f"Invalid data scope format, skipping: {part}")
                continue

            # Split on first colon only
            key_value = part.split(":", 1)
            if len(key_value) != 2:
                continue

            key = key_value[0].strip()
            value = key_value[1].strip()

            if key and value:
                result[key] = value

        return result

    def translate_column_access(
        self, constraint_value: str, model_columns: List[str]
    ) -> List[str]:
        """Filter column list based on column_access constraints.

        Supports both "allowed:col1,col2" and "denied:col1,col2" formats.
        Wildcard "*" in allowed means all columns are permitted.

        Args:
            constraint_value: Column access constraint string
            model_columns: Full list of model columns

        Returns:
            Filtered list of accessible columns
        """
        if not constraint_value or not constraint_value.strip():
            return list(model_columns)

        constraint_value = constraint_value.strip()

        # Check for "allowed:" prefix
        if constraint_value.startswith("allowed:"):
            allowed_str = constraint_value[8:]  # Remove "allowed:" prefix

            # Wildcard means all columns
            if allowed_str.strip() == "*":
                return list(model_columns)

            allowed_cols = {c.strip() for c in allowed_str.split(",") if c.strip()}
            return [col for col in model_columns if col in allowed_cols]

        # Check for "denied:" prefix
        if constraint_value.startswith("denied:"):
            denied_str = constraint_value[7:]  # Remove "denied:" prefix
            denied_cols = {c.strip() for c in denied_str.split(",") if c.strip()}
            return [col for col in model_columns if col not in denied_cols]

        # Unknown format, return all columns
        return list(model_columns)

    def translate_time_window(self, constraint_value: str) -> Dict[str, Any]:
        """Convert time_window constraint to timestamp filters.

        Supports common time window formats:
            - last_30_days
            - last_7_days
            - last_24_hours

        Args:
            constraint_value: Time window constraint string

        Returns:
            Dictionary with created_at filter using $gte operator

        Example:
            >>> wrapper.translate_time_window("last_30_days")
            {'created_at': {'$gte': datetime(...)}}
        """
        if not constraint_value or not constraint_value.strip():
            return {}

        constraint_value = constraint_value.strip().lower()
        now = datetime.now(timezone.utc)

        if constraint_value == "last_30_days":
            cutoff = now - timedelta(days=30)
            return {"created_at": {"$gte": cutoff}}

        if constraint_value == "last_7_days":
            cutoff = now - timedelta(days=7)
            return {"created_at": {"$gte": cutoff}}

        if constraint_value == "last_24_hours":
            cutoff = now - timedelta(hours=24)
            return {"created_at": {"$gte": cutoff}}

        # Unknown format
        logger.debug(f"Unknown time window format: {constraint_value}")
        return {}

    def translate_row_limit(self, constraint_value: str) -> Optional[int]:
        """Extract row limit integer from constraint.

        Args:
            constraint_value: Row limit constraint string
                (e.g., "row_limit:1000" or just "1000")

        Returns:
            Row limit as integer, or None if invalid/empty
        """
        if not constraint_value or not constraint_value.strip():
            return None

        constraint_value = constraint_value.strip()

        # Handle "row_limit:N" format
        if constraint_value.startswith("row_limit:"):
            value_str = constraint_value[10:]  # Remove prefix
        else:
            value_str = constraint_value

        try:
            limit = int(value_str)
            if limit < 0:
                logger.debug(f"Negative row limit not allowed: {limit}")
                return None
            return limit
        except ValueError:
            logger.debug(f"Invalid row limit value: {value_str}")
            return None

    def detect_pii_columns(self, columns: List[str]) -> List[str]:
        """Detect PII columns by name patterns.

        Identifies columns that likely contain personally identifiable
        information based on naming patterns.

        Args:
            columns: List of column names to check

        Returns:
            List of column names that match PII patterns

        PII Patterns Detected:
            - ssn, social_security, social_security_number
            - tax_id, taxpayer_id
            - dob, date_of_birth
            - passport, passport_number
            - drivers_license, driver_license_number
        """
        pii_columns: List[str] = []

        for col in columns:
            col_lower = col.lower()
            for pattern in PII_COLUMN_PATTERNS:
                if re.search(pattern, col_lower):
                    pii_columns.append(col)
                    break

        return pii_columns

    def detect_sensitive_columns(self, columns: List[str]) -> List[str]:
        """Detect sensitive columns by name patterns.

        Identifies columns that likely contain sensitive data
        based on naming patterns.

        Args:
            columns: List of column names to check

        Returns:
            List of column names that match sensitive patterns

        Sensitive Patterns Detected:
            - salary, annual_salary
            - password, password_hash
            - api_key, api_secret
            - secret, client_secret
            - token, access_token, refresh_token
            - credential, credentials
        """
        sensitive_columns: List[str] = []

        for col in columns:
            col_lower = col.lower()
            for pattern in SENSITIVE_COLUMN_PATTERNS:
                if re.search(pattern, col_lower):
                    sensitive_columns.append(col)
                    break

        return sensitive_columns

    def apply_constraints(
        self,
        constraints: List[Any],
        model_columns: List[str],
        operation: str = "read",
    ) -> QueryAccessResult:
        """Apply all constraints and return aggregated result.

        Processes all provided constraints and builds a comprehensive
        QueryAccessResult that can be used to filter queries.

        Args:
            constraints: List of constraint objects (Kaizen-style or mock)
            model_columns: List of column names in the model
            operation: Operation type ("read", "write", "delete", etc.)

        Returns:
            QueryAccessResult with applied constraints
        """
        # Initialize result values
        allowed = True
        denied_reason: Optional[str] = None
        filtered_columns = list(model_columns)
        additional_filters: Dict[str, Any] = {}
        row_limit: Optional[int] = None
        applied_constraints: List[str] = []
        pii_columns_filtered: List[str] = []
        sensitive_columns_flagged: List[str] = []

        # Early return for empty constraints
        if not constraints:
            return QueryAccessResult(
                allowed=True,
                filtered_columns=filtered_columns,
                additional_filters={},
                row_limit=None,
                denied_reason=None,
                applied_constraints=[],
                pii_columns_filtered=[],
                sensitive_columns_flagged=[],
            )

        # Process each constraint
        for constraint in constraints:
            # Get constraint type and value
            # Handle both Kaizen Constraint objects and mock objects
            constraint_type = getattr(constraint, "constraint_type", None)
            constraint_value = str(getattr(constraint, "value", ""))

            if constraint_type is None:
                logger.debug(f"Constraint has no type: {constraint}")
                continue

            # Get type value (handle both enum and string)
            type_value = (
                constraint_type.value
                if hasattr(constraint_type, "value")
                else str(constraint_type)
            )

            # Process based on constraint type
            if type_value == "data_scope":
                scope_filters = self.translate_data_scope(constraint_value)
                additional_filters.update(scope_filters)
                if scope_filters:
                    applied_constraints.append(f"data_scope:{constraint_value}")

            elif type_value == "time_window":
                time_filters = self.translate_time_window(constraint_value)
                additional_filters.update(time_filters)
                if time_filters:
                    applied_constraints.append(f"time_window:{constraint_value}")

            elif type_value == "resource_limit":
                if "row_limit" in constraint_value.lower():
                    limit = self.translate_row_limit(constraint_value)
                    if limit is not None:
                        row_limit = limit
                        applied_constraints.append(f"resource_limit:{constraint_value}")

            elif type_value == "action_restriction":
                value_lower = constraint_value.lower()

                # CARE-055: Use allowlist approach for read_only constraint
                # Only explicitly permitted operations are allowed when read_only is active
                if value_lower == "read_only":
                    # Allowlist of operations permitted under read_only constraint
                    read_only_allowed_operations = frozenset(
                        {"read", "select", "list", "count", "get"}
                    )
                    if operation.lower() not in read_only_allowed_operations:
                        allowed = False
                        denied_reason = f"Operation '{operation}' denied: read_only constraint active"
                    applied_constraints.append("action_restriction:read_only")

                # Check for no_pii restriction
                elif value_lower == "no_pii":
                    pii_cols = self.detect_pii_columns(filtered_columns)
                    if pii_cols:
                        filtered_columns = [
                            c for c in filtered_columns if c not in pii_cols
                        ]
                        pii_columns_filtered.extend(pii_cols)
                    applied_constraints.append("action_restriction:no_pii")

            elif type_value == "audit_requirement":
                # Audit requirements don't filter, just flag
                applied_constraints.append(f"audit_requirement:{constraint_value}")

        # Always detect sensitive columns for flagging (not filtering)
        sensitive_columns_flagged = self.detect_sensitive_columns(filtered_columns)

        return QueryAccessResult(
            allowed=allowed,
            filtered_columns=filtered_columns,
            additional_filters=additional_filters,
            row_limit=row_limit,
            denied_reason=denied_reason,
            applied_constraints=applied_constraints,
            pii_columns_filtered=pii_columns_filtered,
            sensitive_columns_flagged=sensitive_columns_flagged,
        )


# === Trust-Aware Query Executor ===


class TrustAwareQueryExecutor:
    """Wraps DataFlow query operations with trust verification.

    This executor intercepts DataFlow queries and applies trust constraints
    before execution. It supports three enforcement modes:
        - disabled: No trust checking, all operations allowed
        - permissive: Log violations but allow operations
        - enforcing: Block operations that violate constraints

    Integration Points:
        - trust_verifier: For verifying table/resource access
        - trust_operations: For getting agent constraints (Kaizen)
        - audit_generator: For recording audit events (Core SDK)

    All dependencies are optional for standalone operation.

    Example:
        >>> executor = TrustAwareQueryExecutor(
        ...     dataflow_instance=db,
        ...     enforcement_mode="enforcing",
        ... )
        >>> result = await executor.execute_read(
        ...     model_name="User",
        ...     filter={"id": 1},
        ...     agent_id="agent-001",
        ... )
    """

    def __init__(
        self,
        dataflow_instance: Any,
        trust_verifier: Optional[Any] = None,
        trust_operations: Optional[Any] = None,
        enforcement_mode: str = "enforcing",
        audit_generator: Optional[Any] = None,
    ) -> None:
        """Initialize TrustAwareQueryExecutor.

        Args:
            dataflow_instance: DataFlow instance for executing queries
            trust_verifier: Optional TrustVerifier from Core SDK
            trust_operations: Optional Kaizen TrustOperations
            enforcement_mode: One of "disabled", "permissive", "enforcing"
            audit_generator: Optional RuntimeAuditGenerator
        """
        self._dataflow = dataflow_instance
        self._trust_verifier = trust_verifier
        self._trust_operations = trust_operations
        self._enforcement_mode = enforcement_mode.lower()
        self._audit_generator = audit_generator
        self._constraint_wrapper = ConstraintEnvelopeWrapper()

        # Validate enforcement mode
        valid_modes = ("disabled", "permissive", "enforcing")
        if self._enforcement_mode not in valid_modes:
            raise ValueError(
                f"Invalid enforcement_mode '{enforcement_mode}'. "
                f"Must be one of: {valid_modes}"
            )

    async def _get_agent_constraints(self, agent_id: str) -> List[Any]:
        """Get constraints from trust_operations or return empty.

        Args:
            agent_id: Agent ID to get constraints for

        Returns:
            List of constraint objects, empty if not available
        """
        if self._trust_operations is None:
            return []

        try:
            return await self._trust_operations.get_agent_constraints(agent_id)
        except Exception as e:
            logger.warning(f"Failed to get agent constraints for {agent_id}: {e}")
            return []

    async def _verify_table_access(
        self, model_name: str, agent_id: str, operation: str
    ) -> bool:
        """Verify agent can access this table.

        Args:
            model_name: Name of the model/table
            agent_id: Agent requesting access
            operation: Operation type (read, write, etc.)

        Returns:
            True if access allowed, False otherwise

        Raises:
            PermissionError: If access denied in enforcing mode
        """
        if self._trust_verifier is None:
            return True

        try:
            result = await self._trust_verifier.verify_resource_access(
                resource=f"table:{model_name}",
                action=operation,
                agent_id=agent_id,
            )

            if not result.allowed:
                if self._enforcement_mode == "enforcing":
                    raise PermissionError(
                        f"Table access denied for '{model_name}': {result.reason}"
                    )
                elif self._enforcement_mode == "permissive":
                    logger.warning(
                        f"Table access would be denied for '{model_name}' "
                        f"(permissive mode): {result.reason}"
                    )
                return result.allowed

            return True

        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"Table access verification failed: {e}")
            # In case of verification failure, deny in enforcing mode
            if self._enforcement_mode == "enforcing":
                raise PermissionError(
                    f"Table access verification failed for '{model_name}': {e}"
                )
            return True

    def _get_model_columns(self, model_name: str) -> List[str]:
        """Get column names for a model.

        Args:
            model_name: Name of the model

        Returns:
            List of column names
        """
        # Try to get schema from DataFlow
        try:
            if hasattr(self._dataflow, "get_model_columns"):
                return self._dataflow.get_model_columns(model_name)
            elif hasattr(self._dataflow, "discover_schema"):
                schema = self._dataflow.discover_schema(model_name)
                if schema and "columns" in schema:
                    return list(schema["columns"].keys())
        except Exception as e:
            logger.debug(f"Could not get model columns: {e}")

        # Return empty list if we can't determine columns
        return []

    def _filter_pii_from_data(self, data: Any, pii_columns: List[str]) -> Any:
        """Filter PII columns from query result data.

        Args:
            data: Query result data
            pii_columns: List of PII column names to filter

        Returns:
            Data with PII columns removed
        """
        if not pii_columns:
            return data

        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                # Handle {"data": [...]} format
                filtered_rows = []
                for row in data["data"]:
                    if isinstance(row, dict):
                        filtered_row = {
                            k: v for k, v in row.items() if k not in pii_columns
                        }
                        filtered_rows.append(filtered_row)
                    else:
                        filtered_rows.append(row)
                return {"data": filtered_rows}
            else:
                # Handle flat dict
                return {k: v for k, v in data.items() if k not in pii_columns}
        elif isinstance(data, list):
            # Handle list of dicts
            return [
                (
                    {k: v for k, v in row.items() if k not in pii_columns}
                    if isinstance(row, dict)
                    else row
                )
                for row in data
            ]

        return data

    async def _record_audit(
        self,
        model_name: str,
        operation: str,
        result: str,
        agent_id: Optional[str],
        trust_context: Optional[Any],
    ) -> Optional[str]:
        """Record audit event if audit generator is available.

        Args:
            model_name: Model/table accessed
            operation: Operation performed
            result: Result ("success", "failure", "denied")
            agent_id: Agent performing operation
            trust_context: Trust context if available

        Returns:
            Audit event ID if recorded, None otherwise
        """
        if self._audit_generator is None:
            return None

        try:
            event = await self._audit_generator.resource_accessed(
                run_id=trust_context.trace_id if trust_context else "unknown",
                resource=f"table:{model_name}",
                action=operation,
                result=result,
                trust_context=trust_context,
            )
            return getattr(event, "event_id", None)
        except Exception as e:
            logger.warning(f"Failed to record audit event: {e}")
            return None

    async def execute_read(
        self,
        model_name: str,
        filter: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        trust_context: Optional[Any] = None,
    ) -> QueryExecutionResult:
        """Execute a read query with trust verification.

        Steps:
        1. Get constraint envelope from trust_operations if available
        2. Apply constraints via ConstraintEnvelopeWrapper
        3. If denied, raise or log based on enforcement_mode
        4. Execute query with applied filters
        5. Record audit event
        6. Return results

        Args:
            model_name: Name of the model to query
            filter: Optional filter dict for the query
            agent_id: Optional agent ID for constraint lookup
            trust_context: Optional RuntimeTrustContext

        Returns:
            QueryExecutionResult with query results and metadata
        """
        start_time = time.time()
        filter = filter or {}
        applied_constraints: List[str] = []
        audit_event_id: Optional[str] = None

        # Disabled mode - bypass all checks
        if self._enforcement_mode == "disabled":
            try:
                result = await self._dataflow.execute({"model": model_name, **filter})
                execution_time = (time.time() - start_time) * 1000

                return QueryExecutionResult(
                    success=True,
                    data=result,
                    rows_affected=(
                        len(result.get("data", [])) if isinstance(result, dict) else 0
                    ),
                    constraints_applied=[],
                    audit_event_id=None,
                    execution_time_ms=execution_time,
                )
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                return QueryExecutionResult(
                    success=False,
                    data={"error": str(e)},
                    rows_affected=0,
                    constraints_applied=[],
                    audit_event_id=None,
                    execution_time_ms=execution_time,
                )

        # Verify table access if verifier available
        if agent_id:
            await self._verify_table_access(model_name, agent_id, "read")

        # Get and apply constraints
        pii_columns_to_filter: List[str] = []
        if agent_id:
            constraints = await self._get_agent_constraints(agent_id)
            if constraints:
                model_columns = self._get_model_columns(model_name)
                access_result = self._constraint_wrapper.apply_constraints(
                    constraints, model_columns, "read"
                )

                if not access_result.allowed:
                    if self._enforcement_mode == "enforcing":
                        await self._record_audit(
                            model_name, "read", "denied", agent_id, trust_context
                        )
                        raise PermissionError(access_result.denied_reason)
                    else:
                        logger.warning(
                            f"Read access would be denied (permissive): "
                            f"{access_result.denied_reason}"
                        )

                # Merge additional filters
                filter.update(access_result.additional_filters)
                applied_constraints = access_result.applied_constraints
                pii_columns_to_filter = access_result.pii_columns_filtered

        # Execute query
        try:
            result = await self._dataflow.execute({"model": model_name, **filter})

            # Filter PII from result if needed
            if pii_columns_to_filter:
                result = self._filter_pii_from_data(result, pii_columns_to_filter)

            execution_time = (time.time() - start_time) * 1000

            # Record audit
            audit_event_id = await self._record_audit(
                model_name, "read", "success", agent_id, trust_context
            )

            return QueryExecutionResult(
                success=True,
                data=result,
                rows_affected=(
                    len(result.get("data", [])) if isinstance(result, dict) else 0
                ),
                constraints_applied=applied_constraints,
                audit_event_id=audit_event_id,
                execution_time_ms=execution_time,
            )

        except PermissionError:
            raise
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            await self._record_audit(
                model_name, "read", "failure", agent_id, trust_context
            )
            return QueryExecutionResult(
                success=False,
                data={"error": str(e)},
                rows_affected=0,
                constraints_applied=applied_constraints,
                audit_event_id=None,
                execution_time_ms=execution_time,
            )

    async def execute_write(
        self,
        model_name: str,
        operation: str,
        data: Optional[Dict[str, Any]] = None,
        filter: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        trust_context: Optional[Any] = None,
    ) -> QueryExecutionResult:
        """Execute a write query with trust verification.

        Steps:
        1. Check for read_only constraint
        2. Verify write access via trust_verifier
        3. Execute write operation
        4. Record audit event
        5. Return results

        Args:
            model_name: Name of the model to modify
            operation: Write operation type ("create", "update", "delete")
            data: Data to write (for create/update)
            filter: Filter for update/delete operations
            agent_id: Optional agent ID for constraint lookup
            trust_context: Optional RuntimeTrustContext

        Returns:
            QueryExecutionResult with operation results and metadata
        """
        start_time = time.time()
        data = data or {}
        filter = filter or {}
        applied_constraints: List[str] = []
        audit_event_id: Optional[str] = None

        # Disabled mode - bypass all checks
        if self._enforcement_mode == "disabled":
            try:
                result = await self._dataflow.execute(
                    {
                        "model": model_name,
                        "operation": operation,
                        "data": data,
                        **filter,
                    }
                )
                execution_time = (time.time() - start_time) * 1000

                return QueryExecutionResult(
                    success=True,
                    data=result,
                    rows_affected=1,  # Assume 1 for write operations
                    constraints_applied=[],
                    audit_event_id=None,
                    execution_time_ms=execution_time,
                )
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                return QueryExecutionResult(
                    success=False,
                    data={"error": str(e)},
                    rows_affected=0,
                    constraints_applied=[],
                    audit_event_id=None,
                    execution_time_ms=execution_time,
                )

        # Verify table access if verifier available
        if agent_id:
            await self._verify_table_access(model_name, agent_id, operation)

        # Get and check constraints
        if agent_id:
            constraints = await self._get_agent_constraints(agent_id)
            if constraints:
                model_columns = self._get_model_columns(model_name)
                access_result = self._constraint_wrapper.apply_constraints(
                    constraints, model_columns, operation
                )

                if not access_result.allowed:
                    if self._enforcement_mode == "enforcing":
                        await self._record_audit(
                            model_name, operation, "denied", agent_id, trust_context
                        )
                        raise PermissionError(access_result.denied_reason)
                    else:
                        logger.warning(
                            f"Write access would be denied (permissive): "
                            f"{access_result.denied_reason}"
                        )

                applied_constraints = access_result.applied_constraints

        # Execute write operation
        try:
            result = await self._dataflow.execute(
                {
                    "model": model_name,
                    "operation": operation,
                    "data": data,
                    **filter,
                }
            )
            execution_time = (time.time() - start_time) * 1000

            # Record audit
            audit_event_id = await self._record_audit(
                model_name, operation, "success", agent_id, trust_context
            )

            return QueryExecutionResult(
                success=True,
                data=result,
                rows_affected=1,  # Assume 1 for write operations
                constraints_applied=applied_constraints,
                audit_event_id=audit_event_id,
                execution_time_ms=execution_time,
            )

        except PermissionError:
            raise
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            await self._record_audit(
                model_name, operation, "failure", agent_id, trust_context
            )
            return QueryExecutionResult(
                success=False,
                data={"error": str(e)},
                rows_affected=0,
                constraints_applied=applied_constraints,
                audit_event_id=None,
                execution_time_ms=execution_time,
            )
