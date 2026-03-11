"""
DataFlow Write Protection System

Comprehensive write protection that integrates with Core SDK workflow execution.
Provides multi-level protection: Global, Connection, Model, Operation, Field, and Runtime.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class ProtectionLevel(Enum):
    """Protection enforcement levels."""

    OFF = "off"
    WARN = "warn"  # Log warnings but allow operations
    BLOCK = "block"  # Block operations with detailed errors
    AUDIT = "audit"  # Block and create audit entries


class OperationType(Enum):
    """Database operation types."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    BULK_CREATE = "bulk_create"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"
    BULK_UPSERT = "bulk_upsert"
    CUSTOM_QUERY = "custom_query"


@dataclass
class TimeWindow:
    """Time-based protection window."""

    start_time: Optional[time] = None
    end_time: Optional[time] = None
    timezone: str = "UTC"
    days_of_week: Optional[Set[int]] = None  # 0=Monday, 6=Sunday

    def is_active(self, check_time: Optional[datetime] = None) -> bool:
        """Check if protection is active at given time."""
        if not check_time:
            check_time = datetime.now()

        # Check day of week if specified
        if self.days_of_week and check_time.weekday() not in self.days_of_week:
            return False

        # Check time window if specified
        if self.start_time and self.end_time:
            current_time = check_time.time()
            if self.start_time <= self.end_time:
                return self.start_time <= current_time <= self.end_time
            else:  # Overnight window
                return current_time >= self.start_time or current_time <= self.end_time

        return True


@dataclass
class FieldProtection:
    """Field-level protection configuration."""

    field_name: str
    protection_level: ProtectionLevel = ProtectionLevel.BLOCK
    allowed_operations: Set[OperationType] = field(
        default_factory=lambda: {OperationType.READ}
    )
    reason: str = "Field is protected"


@dataclass
class ModelProtection:
    """Model-level protection configuration."""

    model_name: str
    protection_level: ProtectionLevel = ProtectionLevel.BLOCK
    allowed_operations: Set[OperationType] = field(
        default_factory=lambda: {OperationType.READ}
    )
    protected_fields: List[FieldProtection] = field(default_factory=list)
    reason: str = "Model is protected"
    time_window: Optional[TimeWindow] = None
    conditions: List[Callable[[Dict[str, Any]], bool]] = field(default_factory=list)

    def is_operation_allowed(
        self,
        operation: OperationType,
        field_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """Check if operation is allowed on this model/field."""
        # Check time window
        if self.time_window and not self.time_window.is_active():
            return True, "Protection not active in current time window"

        # Check custom conditions
        if context and self.conditions:
            for condition in self.conditions:
                try:
                    if not condition(context):
                        return False, f"Custom condition failed: {condition.__name__}"
                except Exception as e:
                    logger.warning(f"Protection condition error: {e}")
                    return False, f"Protection condition error: {str(e)}"

        # Check field-level protection first
        if field_name:
            for field_protection in self.protected_fields:
                if field_protection.field_name == field_name:
                    allowed = operation in field_protection.allowed_operations
                    reason = field_protection.reason if not allowed else ""
                    return allowed, reason

        # Check model-level protection
        allowed = operation in self.allowed_operations
        reason = self.reason if not allowed else ""
        return allowed, reason


@dataclass
class ConnectionProtection:
    """Connection-level protection configuration."""

    connection_pattern: str  # Regex pattern for connection strings
    protection_level: ProtectionLevel = ProtectionLevel.BLOCK
    allowed_operations: Set[OperationType] = field(
        default_factory=lambda: {OperationType.READ}
    )
    reason: str = "Connection is protected"
    time_window: Optional[TimeWindow] = None

    def matches_connection(self, connection_string: str) -> bool:
        """Check if this protection applies to the connection."""
        return bool(re.match(self.connection_pattern, connection_string))


@dataclass
class GlobalProtection:
    """Global DataFlow protection configuration."""

    protection_level: ProtectionLevel = ProtectionLevel.OFF
    allowed_operations: Set[OperationType] = field(
        default_factory=lambda: set(OperationType)
    )
    reason: str = "Global write protection enabled"
    time_window: Optional[TimeWindow] = None


class ProtectionViolation(Exception):
    """Exception raised when protection rules are violated."""

    def __init__(
        self,
        message: str,
        operation: OperationType,
        level: ProtectionLevel,
        model: Optional[str] = None,
        field: Optional[str] = None,
        connection: Optional[str] = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.level = level
        self.model = model
        self.field = field
        self.connection = connection
        self.timestamp = datetime.now()


class ProtectionAuditor:
    """Audit trail for protection events."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def log_violation(
        self, violation: ProtectionViolation, context: Optional[Dict[str, Any]] = None
    ):
        """Log a protection violation."""
        event = {
            "timestamp": violation.timestamp,
            "message": str(violation),
            "operation": violation.operation.value,
            "level": violation.level.value,
            "model": violation.model,
            "field": violation.field,
            "connection": violation.connection,
            "context": context or {},
        }
        self.events.append(event)
        logger.warning(f"Protection violation: {event}")

    def log_allowed(
        self,
        operation: OperationType,
        model: Optional[str] = None,
        field: Optional[str] = None,
        reason: str = "Allowed",
    ):
        """Log an allowed operation."""
        event = {
            "timestamp": datetime.now(),
            "operation": operation.value,
            "model": model,
            "field": field,
            "status": "allowed",
            "reason": reason,
        }
        self.events.append(event)
        logger.debug(f"Protection check passed: {event}")


@dataclass
class WriteProtectionConfig:
    """Complete write protection configuration."""

    global_protection: GlobalProtection = field(default_factory=GlobalProtection)
    connection_protections: List[ConnectionProtection] = field(default_factory=list)
    model_protections: List[ModelProtection] = field(default_factory=list)
    auditor: ProtectionAuditor = field(default_factory=ProtectionAuditor)

    # Convenience methods for common protection patterns
    @classmethod
    def read_only_global(
        cls, reason: str = "System in read-only mode"
    ) -> "WriteProtectionConfig":
        """Create global read-only protection."""
        return cls(
            global_protection=GlobalProtection(
                protection_level=ProtectionLevel.BLOCK,
                allowed_operations={OperationType.READ},
                reason=reason,
            )
        )

    @classmethod
    def business_hours_protection(
        cls, start_hour: int = 9, end_hour: int = 17, weekdays_only: bool = True
    ) -> "WriteProtectionConfig":
        """Create business hours read-only protection."""
        days = {0, 1, 2, 3, 4} if weekdays_only else None  # Mon-Fri
        time_window = TimeWindow(
            start_time=time(start_hour, 0),
            end_time=time(end_hour, 0),
            days_of_week=days,
        )
        return cls(
            global_protection=GlobalProtection(
                protection_level=ProtectionLevel.BLOCK,
                allowed_operations={OperationType.READ},
                reason="Write operations blocked during business hours",
                time_window=time_window,
            )
        )

    @classmethod
    def production_safe(cls) -> "WriteProtectionConfig":
        """Create production-safe protection configuration."""
        return cls(
            connection_protections=[
                ConnectionProtection(
                    connection_pattern=r".*prod.*|.*production.*",
                    protection_level=ProtectionLevel.BLOCK,
                    allowed_operations={OperationType.READ},
                    reason="Production database protection",
                )
            ]
        )


class WriteProtectionEngine:
    """Core engine for enforcing write protection rules."""

    def __init__(self, config: WriteProtectionConfig):
        self.config = config
        self._operation_mapping = {
            "create": OperationType.CREATE,
            "read": OperationType.READ,
            "update": OperationType.UPDATE,
            "delete": OperationType.DELETE,
            "list": OperationType.READ,
            "bulk_create": OperationType.BULK_CREATE,
            "bulk_update": OperationType.BULK_UPDATE,
            "bulk_delete": OperationType.BULK_DELETE,
            "bulk_upsert": OperationType.BULK_UPSERT,
        }

    def check_operation(
        self,
        operation: str,
        model_name: Optional[str] = None,
        field_name: Optional[str] = None,
        connection_string: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Check if an operation is allowed under current protection rules.

        Args:
            operation: Operation type (create, read, update, delete, etc.)
            model_name: Model being operated on
            field_name: Specific field being accessed
            connection_string: Database connection string
            context: Additional context for dynamic rules

        Raises:
            ProtectionViolation: If operation is blocked
        """
        op_type = self._operation_mapping.get(operation, OperationType.CUSTOM_QUERY)

        # Check global protection first
        if not self._check_global_protection(op_type):
            violation = ProtectionViolation(
                f"Global protection blocks {operation}",
                op_type,
                self.config.global_protection.protection_level,
            )
            self._handle_violation(violation, context)
            return

        # Check connection-level protection
        if connection_string:
            for conn_protection in self.config.connection_protections:
                if conn_protection.matches_connection(connection_string):
                    if not self._check_connection_protection(conn_protection, op_type):
                        violation = ProtectionViolation(
                            f"Connection protection blocks {operation}",
                            op_type,
                            conn_protection.protection_level,
                            connection=connection_string,
                        )
                        self._handle_violation(violation, context)
                        return

        # Check model-level protection
        if model_name:
            for model_protection in self.config.model_protections:
                if model_protection.model_name == model_name:
                    allowed, reason = model_protection.is_operation_allowed(
                        op_type, field_name, context
                    )
                    if not allowed:
                        # Determine if this is field-level or model-level protection
                        if field_name and any(
                            fp.field_name == field_name
                            for fp in model_protection.protected_fields
                        ):
                            message = f"Field protection blocks {operation}: {reason}"
                            # Use the field's protection level, not the model's
                            field_protection = next(
                                (
                                    fp
                                    for fp in model_protection.protected_fields
                                    if fp.field_name == field_name
                                ),
                                None,
                            )
                            protection_level = (
                                field_protection.protection_level
                                if field_protection
                                else model_protection.protection_level
                            )
                        else:
                            message = f"Model protection blocks {operation}: {reason}"
                            protection_level = model_protection.protection_level

                        violation = ProtectionViolation(
                            message,
                            op_type,
                            protection_level,
                            model=model_name,
                            field=field_name,
                        )
                        self._handle_violation(violation, context)
                        return

        # Operation allowed - log if auditing
        self.config.auditor.log_allowed(op_type, model_name, field_name)

    def _check_global_protection(self, operation: OperationType) -> bool:
        """Check global protection rules."""
        global_prot = self.config.global_protection
        if global_prot.protection_level == ProtectionLevel.OFF:
            return True

        if global_prot.time_window and not global_prot.time_window.is_active():
            return True

        return operation in global_prot.allowed_operations

    def _check_connection_protection(
        self, protection: ConnectionProtection, operation: OperationType
    ) -> bool:
        """Check connection-level protection."""
        if protection.time_window and not protection.time_window.is_active():
            return True

        return operation in protection.allowed_operations

    def _handle_violation(
        self, violation: ProtectionViolation, context: Optional[Dict[str, Any]]
    ):
        """Handle a protection violation based on protection level."""
        self.config.auditor.log_violation(violation, context)

        if violation.level in (ProtectionLevel.BLOCK, ProtectionLevel.AUDIT):
            raise violation
        elif violation.level == ProtectionLevel.WARN:
            logger.warning(f"Protection warning: {violation}")
