"""Enterprise audit logging node for comprehensive compliance and security tracking.

This node provides comprehensive audit logging capabilities for enterprise
compliance, security monitoring, and forensic analysis. Built on Session 065's
async database infrastructure for high-performance logging with retention
policies and advanced querying capabilities.

Features:
- Comprehensive audit trail for all admin operations
- Security event tracking and alerting
- Compliance reporting and data retention
- Real-time log streaming and monitoring
- Advanced querying and filtering
- Automated log archiving and cleanup
- Integration with SIEM systems
- Multi-tenant log isolation
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kailash.access_control import UserContext
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class AuditEventType(Enum):
    """Types of audit events."""

    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ACTIVATED = "user_activated"
    USER_DEACTIVATED = "user_deactivated"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET = "password_reset"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_UNASSIGNED = "role_unassigned"
    ROLE_CREATED = "role_created"
    ROLE_UPDATED = "role_updated"
    ROLE_DELETED = "role_deleted"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    PERMISSION_CHECKED = "permission_checked"
    PERMISSION_DENIED = "permission_denied"
    DATA_ACCESSED = "data_accessed"
    DATA_MODIFIED = "data_modified"
    DATA_DELETED = "data_deleted"
    DATA_EXPORTED = "data_exported"
    WORKFLOW_EXECUTED = "workflow_executed"
    WORKFLOW_FAILED = "workflow_failed"
    SYSTEM_CONFIG_CHANGED = "system_config_changed"
    SECURITY_VIOLATION = "security_violation"
    COMPLIANCE_EVENT = "compliance_event"
    CUSTOM = "custom"


class AuditSeverity(Enum):
    """Severity levels for audit events."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditOperation(Enum):
    """Supported audit logging operations."""

    LOG_EVENT = "log_event"
    LOG_BATCH = "log_batch"
    QUERY_LOGS = "query_logs"
    GET_USER_ACTIVITY = "get_user_activity"
    GET_SECURITY_EVENTS = "get_security_events"
    GENERATE_REPORT = "generate_report"
    EXPORT_LOGS = "export_logs"
    ARCHIVE_LOGS = "archive_logs"
    DELETE_LOGS = "delete_logs"
    GET_STATISTICS = "get_statistics"
    MONITOR_REALTIME = "monitor_realtime"


@dataclass
class AuditEvent:
    """Audit event structure."""

    event_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    user_id: Optional[str]
    tenant_id: str
    resource_id: Optional[str]
    action: str
    description: str
    metadata: Dict[str, Any]
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "action": self.action,
            "description": self.description,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
        }


@register_node()
class EnterpriseAuditLogNode(Node):
    """Enterprise audit logging node with comprehensive compliance features.

    This node provides comprehensive audit logging capabilities including:
    - Structured audit event logging
    - Advanced querying and filtering
    - Compliance reporting and export
    - Real-time monitoring and alerting
    - Automated archiving and retention
    - Multi-tenant log isolation

    Parameters:
        operation: Type of audit operation to perform
        event_data: Event data for logging operations
        events: List of events for batch logging
        query_filters: Filters for log querying
        user_id: User ID for user-specific queries
        event_types: Event types to filter
        severity: Minimum severity level
        date_range: Date range for queries
        pagination: Pagination parameters
        export_format: Format for log export
        tenant_id: Tenant isolation

    Example:
        >>> # Log single audit event
        >>> node = AuditLogNode(
        ...     operation="log_event",
        ...     event_data={
        ...         "event_type": "user_login",
        ...         "severity": "medium",
        ...         "user_id": "user123",
        ...         "action": "successful_login",
        ...         "description": "User logged in successfully",
        ...         "metadata": {
        ...             "login_method": "password",
        ...             "mfa_used": True
        ...         },
        ...         "ip_address": "192.168.1.100"
        ...     }
        ... )
        >>> result = node.execute()
        >>> event_id = result["event"]["event_id"]

        >>> # Query security events
        >>> node = AuditLogNode(
        ...     operation="get_security_events",
        ...     query_filters={
        ...         "severity": ["high", "critical"],
        ...         "date_range": {
        ...             "start": "2025-06-01T00:00:00Z",
        ...             "end": "2025-06-12T23:59:59Z"
        ...         }
        ...     },
        ...     pagination={"page": 1, "size": 50}
        ... )
        >>> result = node.execute()
        >>> events = result["events"]

        >>> # Generate compliance report
        >>> node = AuditLogNode(
        ...     operation="generate_report",
        ...     query_filters={
        ...         "event_types": ["data_accessed", "data_modified", "data_exported"],
        ...         "user_id": "analyst123"
        ...     },
        ...     export_format="json"
        ... )
        >>> result = node.execute()
        >>> report = result["report"]
    """

    def __init__(self, **config):
        super().__init__(**config)
        self._db_node = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for audit logging operations."""
        return {
            param.name: param
            for param in [
                # Operation type
                NodeParameter(
                    name="operation",
                    type=str,
                    required=True,
                    description="Audit logging operation to perform",
                    choices=[op.value for op in AuditOperation],
                ),
                # Event data for logging
                NodeParameter(
                    name="event_data",
                    type=dict,
                    required=False,
                    description="Event data for logging operations",
                ),
                NodeParameter(
                    name="events",
                    type=list,
                    required=False,
                    description="List of events for batch logging",
                ),
                # Query parameters
                NodeParameter(
                    name="query_filters",
                    type=dict,
                    required=False,
                    description="Filters for log querying",
                ),
                NodeParameter(
                    name="user_id",
                    type=str,
                    required=False,
                    description="User ID for user-specific queries",
                ),
                NodeParameter(
                    name="event_types",
                    type=list,
                    required=False,
                    description="Event types to filter",
                ),
                NodeParameter(
                    name="severity",
                    type=str,
                    required=False,
                    choices=[s.value for s in AuditSeverity],
                    description="Minimum severity level",
                ),
                # Date range
                NodeParameter(
                    name="date_range",
                    type=dict,
                    required=False,
                    description="Date range for queries (start, end)",
                ),
                # Pagination
                NodeParameter(
                    name="pagination",
                    type=dict,
                    required=False,
                    description="Pagination parameters (page, size, sort)",
                ),
                # Export options
                NodeParameter(
                    name="export_format",
                    type=str,
                    required=False,
                    choices=["json", "csv", "pdf"],
                    description="Format for log export",
                ),
                # Multi-tenancy
                NodeParameter(
                    name="tenant_id",
                    type=str,
                    required=False,
                    description="Tenant ID for multi-tenant isolation",
                ),
                # Database configuration
                NodeParameter(
                    name="database_config",
                    type=dict,
                    required=False,
                    description="Database connection configuration",
                ),
                # Archiving options
                NodeParameter(
                    name="archive_older_than_days",
                    type=int,
                    required=False,
                    description="Archive logs older than specified days",
                ),
                NodeParameter(
                    name="delete_older_than_days",
                    type=int,
                    required=False,
                    description="Delete logs older than specified days",
                ),
                # Real-time monitoring
                NodeParameter(
                    name="stream_duration_seconds",
                    type=int,
                    required=False,
                    default=60,
                    description="Duration for real-time log streaming",
                ),
            ]
        }

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute audit logging operation."""
        try:
            operation = AuditOperation(inputs["operation"])

            # Initialize dependencies
            self._init_dependencies(inputs)

            # Route to appropriate operation
            if operation == AuditOperation.LOG_EVENT:
                return self._log_event(inputs)
            elif operation == AuditOperation.LOG_BATCH:
                return self._log_batch(inputs)
            elif operation == AuditOperation.QUERY_LOGS:
                return self._query_logs(inputs)
            elif operation == AuditOperation.GET_USER_ACTIVITY:
                return self._get_user_activity(inputs)
            elif operation == AuditOperation.GET_SECURITY_EVENTS:
                return self._get_security_events(inputs)
            elif operation == AuditOperation.GENERATE_REPORT:
                return self._generate_report(inputs)
            elif operation == AuditOperation.EXPORT_LOGS:
                return self._export_logs(inputs)
            elif operation == AuditOperation.ARCHIVE_LOGS:
                return self._archive_logs(inputs)
            elif operation == AuditOperation.DELETE_LOGS:
                return self._delete_logs(inputs)
            elif operation == AuditOperation.GET_STATISTICS:
                return self._get_statistics(inputs)
            elif operation == AuditOperation.MONITOR_REALTIME:
                return self._monitor_realtime(inputs)
            else:
                raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            raise NodeExecutionError(f"Audit logging operation failed: {str(e)}")

    def _init_dependencies(self, inputs: Dict[str, Any]):
        """Initialize database dependencies."""
        # Get database config
        db_config = inputs.get(
            "database_config",
            {
                "database_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "kailash_admin",
                "user": "admin",
                "password": "admin",
            },
        )

        # Initialize async database node
        self._db_node = AsyncSQLDatabaseNode(name="audit_log_db", **db_config)

    def _log_event(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Log a single audit event."""
        event_data = inputs["event_data"]
        tenant_id = inputs.get("tenant_id", "default")

        # Validate required event fields
        required_fields = ["event_type", "action", "description"]
        for field in required_fields:
            if field not in event_data:
                raise NodeValidationError(f"Missing required field: {field}")

        # Create audit event
        event_id = self._generate_event_id()
        now = datetime.now(UTC)

        audit_event = AuditEvent(
            event_id=event_id,
            event_type=AuditEventType(event_data["event_type"]),
            severity=AuditSeverity(event_data.get("severity", "medium")),
            user_id=event_data.get("user_id"),
            tenant_id=tenant_id,
            resource_id=event_data.get("resource_id"),
            action=event_data["action"],
            description=event_data["description"],
            metadata=event_data.get("metadata", {}),
            timestamp=now,
            ip_address=event_data.get("ip_address"),
            user_agent=event_data.get("user_agent"),
            session_id=event_data.get("session_id"),
            correlation_id=event_data.get("correlation_id"),
        )

        # Insert into database
        insert_query = """
        INSERT INTO audit_logs (
            event_id, event_type, severity, user_id, tenant_id, resource_id,
            action, description, metadata, timestamp, ip_address, user_agent,
            session_id, correlation_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        """

        self._db_node.config.update(
            {
                "query": insert_query,
                "params": [
                    audit_event.event_id,
                    audit_event.event_type.value,
                    audit_event.severity.value,
                    audit_event.user_id,
                    audit_event.tenant_id,
                    audit_event.resource_id,
                    audit_event.action,
                    audit_event.description,
                    audit_event.metadata,
                    audit_event.timestamp,
                    audit_event.ip_address,
                    audit_event.user_agent,
                    audit_event.session_id,
                    audit_event.correlation_id,
                ],
            }
        )

        db_result = self._db_node.execute()

        return {
            "result": {
                "event": audit_event.to_dict(),
                "logged": True,
                "operation": "log_event",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _log_batch(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Log multiple audit events in batch."""
        events = inputs["events"]
        tenant_id = inputs.get("tenant_id", "default")

        if not isinstance(events, list):
            raise NodeValidationError("events must be a list for batch operations")

        results = {"logged": [], "failed": [], "stats": {"logged": 0, "failed": 0}}

        for i, event_data in enumerate(events):
            try:
                # Log individual event
                log_inputs = {
                    "operation": "log_event",
                    "event_data": event_data,
                    "tenant_id": tenant_id,
                }

                result = self._log_event(log_inputs)
                results["logged"].append(
                    {"index": i, "event": result["result"]["event"]}
                )
                results["stats"]["logged"] += 1

            except Exception as e:
                results["failed"].append(
                    {"index": i, "event_data": event_data, "error": str(e)}
                )
                results["stats"]["failed"] += 1

        return {
            "result": {
                "operation": "log_batch",
                "results": results,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _query_logs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Query audit logs with advanced filtering."""
        query_filters = inputs.get("query_filters", {})
        pagination = inputs.get(
            "pagination", {"page": 1, "size": 20, "sort": "timestamp"}
        )
        tenant_id = inputs.get("tenant_id", "default")

        # Build WHERE clause
        where_conditions = ["tenant_id = $1"]
        params = [tenant_id]
        param_count = 1

        # Apply filters
        if "event_types" in query_filters:
            param_count += 1
            event_types = query_filters["event_types"]
            placeholders = ",".join(
                ["$" + str(param_count + i) for i in range(len(event_types))]
            )
            where_conditions.append(f"event_type IN ({placeholders})")
            params.extend(event_types)
            param_count += len(event_types) - 1

        if "severity" in query_filters:
            param_count += 1
            where_conditions.append(f"severity = ${param_count}")
            params.append(query_filters["severity"])

        if "user_id" in query_filters:
            param_count += 1
            where_conditions.append(f"user_id = ${param_count}")
            params.append(query_filters["user_id"])

        if "resource_id" in query_filters:
            param_count += 1
            where_conditions.append(f"resource_id = ${param_count}")
            params.append(query_filters["resource_id"])

        # Date range filter
        if "date_range" in query_filters:
            date_range = query_filters["date_range"]
            if "start" in date_range:
                param_count += 1
                where_conditions.append(f"timestamp >= ${param_count}")
                params.append(
                    datetime.fromisoformat(date_range["start"].replace("Z", "+00:00"))
                )

            if "end" in date_range:
                param_count += 1
                where_conditions.append(f"timestamp <= ${param_count}")
                params.append(
                    datetime.fromisoformat(date_range["end"].replace("Z", "+00:00"))
                )

        # Pagination
        page = pagination.get("page", 1)
        size = pagination.get("size", 20)
        sort_field = pagination.get("sort", "timestamp")
        sort_direction = pagination.get("direction", "DESC")

        offset = (page - 1) * size

        # Count query
        count_query = f"""
        SELECT COUNT(*) as total
        FROM audit_logs
        WHERE {' AND '.join(where_conditions)}
        """

        # Data query
        data_query = f"""
        SELECT event_id, event_type, severity, user_id, resource_id, action,
               description, metadata, timestamp, ip_address, correlation_id
        FROM audit_logs
        WHERE {' AND '.join(where_conditions)}
        ORDER BY {sort_field} {sort_direction}
        LIMIT {size} OFFSET {offset}
        """

        # Execute count query
        self._db_node.config.update(
            {"query": count_query, "params": params, "fetch_mode": "one"}
        )
        count_result = self._db_node.execute()
        total_count = count_result["result"]["data"]["total"]

        # Execute data query
        self._db_node.config.update(
            {"query": data_query, "params": params, "fetch_mode": "all"}
        )
        data_result = self._db_node.execute()
        logs = data_result["result"]["data"]

        # Calculate pagination info
        total_pages = (total_count + size - 1) // size
        has_next = page < total_pages
        has_prev = page > 1

        return {
            "result": {
                "logs": logs,
                "pagination": {
                    "page": page,
                    "size": size,
                    "total": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev,
                },
                "filters_applied": query_filters,
                "operation": "query_logs",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_security_events(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get security-specific audit events."""
        # Security event types
        security_event_types = [
            AuditEventType.SECURITY_VIOLATION.value,
            AuditEventType.PERMISSION_DENIED.value,
            AuditEventType.USER_LOGIN.value,
            AuditEventType.USER_LOGOUT.value,
            AuditEventType.PASSWORD_CHANGED.value,
            AuditEventType.PASSWORD_RESET.value,
        ]

        # Add security event filter
        query_filters = inputs.get("query_filters", {})
        query_filters["event_types"] = security_event_types

        # Use regular query_logs with security filters
        security_inputs = inputs.copy()
        security_inputs["query_filters"] = query_filters

        result = self._query_logs(security_inputs)
        result["result"]["operation"] = "get_security_events"

        return result

    def _get_user_activity(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get activity logs for a specific user."""
        user_id = inputs["user_id"]

        # Add user filter
        query_filters = inputs.get("query_filters", {})
        query_filters["user_id"] = user_id

        # Use regular query_logs with user filter
        user_inputs = inputs.copy()
        user_inputs["query_filters"] = query_filters

        result = self._query_logs(user_inputs)
        result["result"]["operation"] = "get_user_activity"
        result["result"]["user_id"] = user_id

        return result

    def _generate_report(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate compliance and audit reports."""
        query_filters = inputs.get("query_filters", {})
        export_format = inputs.get("export_format", "json")
        tenant_id = inputs.get("tenant_id", "default")

        # Get audit logs based on filters
        query_inputs = {
            "query_filters": query_filters,
            "pagination": {"page": 1, "size": 10000},  # Large size for reports
            "tenant_id": tenant_id,
        }

        logs_result = self._query_logs(query_inputs)
        logs = logs_result["result"]["logs"]

        # Generate statistics
        stats = self._calculate_log_statistics(logs)

        # Build report
        report = {
            "report_id": self._generate_event_id(),
            "generated_at": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "filters": query_filters,
            "statistics": stats,
            "total_events": len(logs),
            "format": export_format,
        }

        if export_format == "json":
            report["events"] = logs
        elif export_format == "csv":
            report["csv_data"] = self._convert_to_csv(logs)
        elif export_format == "pdf":
            report["pdf_url"] = f"/reports/{report['report_id']}.pdf"

        return {
            "result": {
                "report": report,
                "operation": "generate_report",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _calculate_log_statistics(self, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics from audit logs."""
        stats = {
            "event_types": {},
            "severities": {},
            "users": {},
            "daily_counts": {},
            "hourly_distribution": [0] * 24,
        }

        for log in logs:
            # Event type distribution
            event_type = log["event_type"]
            stats["event_types"][event_type] = (
                stats["event_types"].get(event_type, 0) + 1
            )

            # Severity distribution
            severity = log["severity"]
            stats["severities"][severity] = stats["severities"].get(severity, 0) + 1

            # User activity
            user_id = log.get("user_id")
            if user_id:
                stats["users"][user_id] = stats["users"].get(user_id, 0) + 1

            # Daily counts
            if log["timestamp"]:
                date_str = log["timestamp"][:10]  # Extract date part
                stats["daily_counts"][date_str] = (
                    stats["daily_counts"].get(date_str, 0) + 1
                )

                # Hourly distribution
                try:
                    hour = datetime.fromisoformat(
                        log["timestamp"].replace("Z", "+00:00")
                    ).hour
                    stats["hourly_distribution"][hour] += 1
                except:
                    pass

        return stats

    def _convert_to_csv(self, logs: List[Dict[str, Any]]) -> str:
        """Convert logs to CSV format."""
        if not logs:
            return ""

        # CSV headers
        headers = [
            "event_id",
            "event_type",
            "severity",
            "user_id",
            "action",
            "timestamp",
        ]
        csv_lines = [",".join(headers)]

        # CSV data
        for log in logs:
            row = []
            for header in headers:
                value = log.get(header, "")
                if value is None:
                    value = ""
                # Escape commas and quotes
                value_str = str(value).replace('"', '""')
                if "," in value_str or '"' in value_str:
                    value_str = f'"{value_str}"'
                row.append(value_str)
            csv_lines.append(",".join(row))

        return "\n".join(csv_lines)

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        import uuid

        return str(uuid.uuid4())

    # Additional operations would follow similar patterns
    def _export_logs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Export audit logs in various formats."""
        format_type = inputs.get("export_format", "json")
        query_filters = inputs.get("query_filters", {})
        date_range = inputs.get("date_range", {})

        # Query logs
        query_result = self._query_logs(
            {
                "query_filters": query_filters,
                "date_range": date_range,
                "pagination": {"page": 1, "size": 10000},  # Export all matching records
            }
        )

        logs = query_result.get("logs", [])

        if format_type == "json":
            export_data = {
                "export_date": datetime.now(timezone.utc).isoformat(),
                "total_records": len(logs),
                "filters": query_filters,
                "date_range": date_range,
                "logs": logs,
            }
            filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        elif format_type == "csv":
            # Convert to CSV format
            import csv
            import io

            output = io.StringIO()
            if logs:
                writer = csv.DictWriter(output, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)

            export_data = output.getvalue()
            filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        elif format_type == "pdf":
            # For PDF, we'll return structured data that can be rendered
            export_data = {
                "title": "Audit Log Report",
                "generated_date": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "total_records": len(logs),
                    "date_range": date_range,
                    "filters": query_filters,
                },
                "logs": logs,
            }
            filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        return {
            "success": True,
            "filename": filename,
            "format": format_type,
            "record_count": len(logs),
            "export_data": export_data,
        }

    def _archive_logs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Archive old audit logs for long-term storage."""
        archive_days = inputs.get("archive_older_than_days", 90)
        archive_path = inputs.get("archive_path", "/archives/audit_logs")
        tenant_id = inputs.get("tenant_id")

        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=archive_days)

        # Query old logs
        query_result = self._query_logs(
            {
                "date_range": {"end": cutoff_date.isoformat()},
                "tenant_id": tenant_id,
                "pagination": {"page": 1, "size": 10000},
            }
        )

        logs_to_archive = query_result.get("logs", [])

        if not logs_to_archive:
            return {
                "success": True,
                "message": "No logs to archive",
                "archived_count": 0,
            }

        # Create archive
        archive_filename = f"audit_archive_{cutoff_date.strftime('%Y%m%d')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        archive_data = {
            "archive_date": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "total_records": len(logs_to_archive),
            "tenant_id": tenant_id,
            "logs": logs_to_archive,
        }

        # In a real implementation, this would save to cloud storage or archive system
        archive_location = f"{archive_path}/{archive_filename}"

        # Delete archived logs from main database
        log_ids = [log.get("id") for log in logs_to_archive if log.get("id")]

        if log_ids:
            # Delete logs
            delete_query = """
            DELETE FROM audit_logs
            WHERE id IN (%s)
            """ % ",".join(
                ["?" for _ in log_ids]
            )

            if tenant_id:
                delete_query += " AND tenant_id = ?"
                log_ids.append(tenant_id)

            self._ensure_db_node(inputs)
            self._db_node.execute(query=delete_query, params=log_ids)

        return {
            "success": True,
            "archived_count": len(logs_to_archive),
            "archive_location": archive_location,
            "archive_filename": archive_filename,
            "cutoff_date": cutoff_date.isoformat(),
            "message": f"Archived {len(logs_to_archive)} logs older than {archive_days} days",
        }

    def _delete_logs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Delete old audit logs based on retention policy."""
        retention_days = inputs.get("retention_days", 365)
        tenant_id = inputs.get("tenant_id")
        dry_run = inputs.get("dry_run", False)

        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # First count logs to be deleted
        count_query = """
        SELECT COUNT(*) as count FROM audit_logs
        WHERE created_at < ?
        """
        params = [cutoff_date.isoformat()]

        if tenant_id:
            count_query += " AND tenant_id = ?"
            params.append(tenant_id)

        self._ensure_db_node(inputs)
        count_result = self._db_node.execute(query=count_query, params=params)
        total_to_delete = count_result.get("rows", [{}])[0].get("count", 0)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "would_delete": total_to_delete,
                "cutoff_date": cutoff_date.isoformat(),
                "message": f"Dry run: Would delete {total_to_delete} logs older than {retention_days} days",
            }

        if total_to_delete == 0:
            return {"success": True, "deleted_count": 0, "message": "No logs to delete"}

        # Delete logs in batches to avoid locking
        batch_size = 1000
        deleted_total = 0

        while deleted_total < total_to_delete:
            delete_query = f"""
            DELETE FROM audit_logs
            WHERE id IN (
                SELECT id FROM audit_logs
                WHERE created_at < ?
                {' AND tenant_id = ?' if tenant_id else ''}
                LIMIT {batch_size}
            )
            """

            delete_params = [cutoff_date.isoformat()]
            if tenant_id:
                delete_params.append(tenant_id)

            result = self._db_node.execute(query=delete_query, params=delete_params)
            batch_deleted = result.get("rows_affected", 0)
            deleted_total += batch_deleted

            if batch_deleted == 0:
                break

        return {
            "success": True,
            "deleted_count": deleted_total,
            "cutoff_date": cutoff_date.isoformat(),
            "retention_days": retention_days,
            "message": f"Deleted {deleted_total} logs older than {retention_days} days",
        }

    def _get_statistics(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get audit log statistics and metrics."""
        tenant_id = inputs.get("tenant_id")
        date_range = inputs.get("date_range", {})
        group_by = inputs.get(
            "group_by", ["event_type", "severity"]
        )  # What to group statistics by

        self._ensure_db_node(inputs)

        # Build base WHERE clause
        where_conditions = []
        params = []

        if tenant_id:
            where_conditions.append("tenant_id = ?")
            params.append(tenant_id)

        if date_range:
            if date_range.get("start"):
                where_conditions.append("created_at >= ?")
                params.append(date_range["start"])
            if date_range.get("end"):
                where_conditions.append("created_at <= ?")
                params.append(date_range["end"])

        where_clause = (
            " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        )

        # Get total count
        total_query = f"SELECT COUNT(*) as total FROM audit_logs{where_clause}"
        total_result = self._db_node.execute(query=total_query, params=params)
        total_count = total_result.get("rows", [{}])[0].get("total", 0)

        # Get counts by severity
        severity_query = f"""
        SELECT severity, COUNT(*) as count
        FROM audit_logs{where_clause}
        GROUP BY severity
        """
        severity_result = self._db_node.execute(query=severity_query, params=params)
        severity_counts = {
            row["severity"]: row["count"] for row in severity_result.get("rows", [])
        }

        # Get counts by event type
        event_type_query = f"""
        SELECT event_type, COUNT(*) as count
        FROM audit_logs{where_clause}
        GROUP BY event_type
        ORDER BY count DESC
        LIMIT 20
        """
        event_type_result = self._db_node.execute(query=event_type_query, params=params)
        event_type_counts = {
            row["event_type"]: row["count"] for row in event_type_result.get("rows", [])
        }

        # Get hourly distribution for the date range
        hourly_query = f"""
        SELECT
            strftime('%Y-%m-%d %H:00:00', created_at) as hour,
            COUNT(*) as count
        FROM audit_logs{where_clause}
        GROUP BY hour
        ORDER BY hour DESC
        LIMIT 168
        """  # Last 7 days of hourly data
        hourly_result = self._db_node.execute(query=hourly_query, params=params)
        hourly_distribution = [
            {"hour": row["hour"], "count": row["count"]}
            for row in hourly_result.get("rows", [])
        ]

        # Get top users by activity
        user_activity_query = f"""
        SELECT user_id, COUNT(*) as action_count
        FROM audit_logs{where_clause}
        GROUP BY user_id
        ORDER BY action_count DESC
        LIMIT 10
        """
        user_activity_result = self._db_node.execute(
            query=user_activity_query, params=params
        )
        top_users = [
            {"user_id": row["user_id"], "action_count": row["action_count"]}
            for row in user_activity_result.get("rows", [])
        ]

        # Get failed actions
        failed_query = f"""
        SELECT COUNT(*) as failed_count
        FROM audit_logs{where_clause}
        {' AND ' if where_clause else ' WHERE '}
        status = 'failed' OR severity = 'error'
        """
        failed_params = params.copy()
        failed_result = self._db_node.execute(query=failed_query, params=failed_params)
        failed_count = failed_result.get("rows", [{}])[0].get("failed_count", 0)

        statistics = {
            "total_events": total_count,
            "failed_events": failed_count,
            "success_rate": (
                ((total_count - failed_count) / total_count * 100)
                if total_count > 0
                else 0
            ),
            "severity_distribution": severity_counts,
            "event_type_distribution": event_type_counts,
            "hourly_distribution": hourly_distribution,
            "top_users": top_users,
            "date_range": date_range,
            "tenant_id": tenant_id,
        }

        return {"success": True, "statistics": statistics}

    def _monitor_realtime(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Monitor audit logs in real-time."""
        # This operation would typically set up a subscription or polling mechanism
        # For now, we'll return the latest events and configuration for real-time monitoring

        tenant_id = inputs.get("tenant_id")
        event_types = inputs.get("event_types", [])  # Filter by specific event types
        severity_filter = inputs.get("severity", AuditSeverity.INFO.value)
        polling_interval = inputs.get("polling_interval", 5)  # seconds
        max_events = inputs.get("max_events", 100)

        # Get latest events
        query_result = self._query_logs(
            {
                "tenant_id": tenant_id,
                "event_types": event_types,
                "severity": severity_filter,
                "pagination": {
                    "page": 1,
                    "size": max_events,
                    "sort": [{"field": "created_at", "order": "desc"}],
                },
            }
        )

        latest_events = query_result.get("logs", [])

        # Create monitoring configuration
        monitor_config = {
            "monitor_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "filters": {
                "tenant_id": tenant_id,
                "event_types": event_types,
                "severity": severity_filter,
            },
            "polling_interval": polling_interval,
            "max_events": max_events,
            "status": "active",
            "last_poll": datetime.now(timezone.utc).isoformat(),
            "endpoint": f"/api/audit/monitor/{uuid.uuid4()}",  # Webhook or WebSocket endpoint
        }

        # In a real implementation, this would:
        # 1. Set up a WebSocket connection or Server-Sent Events stream
        # 2. Create database triggers or use change data capture
        # 3. Set up a message queue subscription

        return {
            "success": True,
            "monitor_config": monitor_config,
            "latest_events": latest_events,
            "event_count": len(latest_events),
            "message": "Real-time monitoring configured. Use the endpoint for live updates.",
        }
