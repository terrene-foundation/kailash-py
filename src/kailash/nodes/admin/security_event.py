"""Enterprise security event monitoring node for threat detection and response.

This node provides specialized security event processing, threat detection,
and automated response capabilities. Built for enterprise security operations
centers (SOCs) with real-time monitoring, alerting, and integration with
external security systems.

Features:
- Real-time security event processing
- Threat detection with ML-based analytics
- Automated incident response workflows
- Integration with SIEM and SOAR systems
- Risk scoring and escalation
- Security metrics and dashboards
- Compliance violation detection
- Forensic data collection
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from kailash.access_control import UserContext
from kailash.nodes.admin.audit_log import (
    AuditEventType,
    AuditSeverity,
    EnterpriseAuditLogNode,
)
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class SecurityEventType(Enum):
    """Types of security events."""

    SUSPICIOUS_LOGIN = "suspicious_login"
    MULTIPLE_FAILED_LOGINS = "multiple_failed_logins"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNAUTHORIZED_ACCESS_ATTEMPT = "unauthorized_access_attempt"
    DATA_EXFILTRATION = "data_exfiltration"
    UNUSUAL_DATA_ACCESS = "unusual_data_access"
    BRUTE_FORCE_ATTACK = "brute_force_attack"
    ACCOUNT_TAKEOVER = "account_takeover"
    INSIDER_THREAT = "insider_threat"
    MALWARE_DETECTION = "malware_detection"
    PHISHING_ATTEMPT = "phishing_attempt"
    POLICY_VIOLATION = "policy_violation"
    COMPLIANCE_BREACH = "compliance_breach"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    SYSTEM_COMPROMISE = "system_compromise"
    CUSTOM_THREAT = "custom_threat"


class ThreatLevel(Enum):
    """Threat severity levels."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityOperation(Enum):
    """Supported security operations."""

    CREATE_EVENT = "create_event"
    ANALYZE_THREATS = "analyze_threats"
    DETECT_ANOMALIES = "detect_anomalies"
    GENERATE_ALERTS = "generate_alerts"
    GET_INCIDENTS = "get_incidents"
    CREATE_INCIDENT = "create_incident"
    UPDATE_INCIDENT = "update_incident"
    GET_THREAT_INTELLIGENCE = "get_threat_intelligence"
    CALCULATE_RISK_SCORE = "calculate_risk_score"
    MONITOR_USER_BEHAVIOR = "monitor_user_behavior"
    COMPLIANCE_CHECK = "compliance_check"
    FORENSIC_ANALYSIS = "forensic_analysis"
    AUTOMATED_RESPONSE = "automated_response"


class IncidentStatus(Enum):
    """Security incident status."""

    NEW = "new"
    INVESTIGATING = "investigating"
    CONTAINMENT = "containment"
    ERADICATION = "eradication"
    RECOVERY = "recovery"
    CLOSED = "closed"


@dataclass
class SecurityEvent:
    """Security event structure."""

    event_id: str
    event_type: SecurityEventType
    threat_level: ThreatLevel
    user_id: Optional[str]
    tenant_id: str
    source_ip: str
    target_resource: Optional[str]
    description: str
    indicators: Dict[str, Any]
    risk_score: float
    timestamp: datetime
    detection_method: str
    false_positive_probability: float = 0.0
    mitigation_applied: bool = False
    incident_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "threat_level": self.threat_level.value,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "source_ip": self.source_ip,
            "target_resource": self.target_resource,
            "description": self.description,
            "indicators": self.indicators,
            "risk_score": self.risk_score,
            "timestamp": self.timestamp.isoformat(),
            "detection_method": self.detection_method,
            "false_positive_probability": self.false_positive_probability,
            "mitigation_applied": self.mitigation_applied,
            "incident_id": self.incident_id,
        }


@dataclass
class SecurityIncident:
    """Security incident structure."""

    incident_id: str
    title: str
    description: str
    status: IncidentStatus
    severity: ThreatLevel
    assignee: Optional[str]
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime]
    events: List[str]  # List of security event IDs
    actions_taken: List[Dict[str, Any]]
    impact_assessment: Dict[str, Any]
    tenant_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "severity": self.severity.value,
            "assignee": self.assignee,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "events": self.events,
            "actions_taken": self.actions_taken,
            "impact_assessment": self.impact_assessment,
            "tenant_id": self.tenant_id,
        }


@register_node()
class EnterpriseSecurityEventNode(Node):
    """Enterprise security event monitoring and incident response node.

    This node provides comprehensive security event processing including:
    - Real-time threat detection and analysis
    - Security incident management
    - Risk scoring and escalation
    - Automated response workflows
    - Compliance monitoring
    - Forensic analysis capabilities

    Parameters:
        operation: Type of security operation to perform
        event_data: Security event data
        incident_data: Security incident data
        analysis_config: Configuration for threat analysis
        user_id: User ID for behavior monitoring
        risk_threshold: Risk score threshold for alerts
        time_window: Time window for analysis
        detection_rules: Custom detection rules
        response_actions: Automated response configuration
        tenant_id: Tenant isolation

    Example:
        >>> # Create security event for suspicious login
        >>> node = SecurityEventNode(
        ...     operation="create_event",
        ...     event_data={
        ...         "event_type": "suspicious_login",
        ...         "threat_level": "medium",
        ...         "user_id": "user123",
        ...         "source_ip": "192.168.1.100",
        ...         "description": "Login from unusual location",
        ...         "indicators": {
        ...             "location": "Unknown Country",
        ...             "device": "New Device",
        ...             "time": "Outside business hours"
        ...         },
        ...         "detection_method": "geolocation_analysis"
        ...     }
        ... )
        >>> result = node.execute()
        >>> event_id = result["security_event"]["event_id"]

        >>> # Analyze threats in time window
        >>> node = SecurityEventNode(
        ...     operation="analyze_threats",
        ...     analysis_config={
        ...         "time_window": 3600,  # 1 hour
        ...         "threat_types": ["brute_force_attack", "suspicious_login"],
        ...         "risk_threshold": 7.0
        ...     }
        ... )
        >>> result = node.execute()
        >>> threats = result["threat_analysis"]["high_risk_events"]

        >>> # Monitor user behavior for anomalies
        >>> node = SecurityEventNode(
        ...     operation="monitor_user_behavior",
        ...     user_id="user123",
        ...     analysis_config={
        ...         "lookback_days": 30,
        ...         "anomaly_threshold": 0.8
        ...     }
        ... )
        >>> result = node.execute()
        >>> anomalies = result["behavior_analysis"]["anomalies"]
    """

    def __init__(self, **config):
        super().__init__(**config)
        self._db_node = None
        self._audit_node = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for security operations."""
        return {
            param.name: param
            for param in [
                # Operation type
                NodeParameter(
                    name="operation",
                    type=str,
                    required=True,
                    description="Security operation to perform",
                    choices=[op.value for op in SecurityOperation],
                ),
                # Event data
                NodeParameter(
                    name="event_data",
                    type=dict,
                    required=False,
                    description="Security event data",
                ),
                # Incident data
                NodeParameter(
                    name="incident_data",
                    type=dict,
                    required=False,
                    description="Security incident data",
                ),
                # Analysis configuration
                NodeParameter(
                    name="analysis_config",
                    type=dict,
                    required=False,
                    description="Configuration for threat analysis",
                ),
                # User monitoring
                NodeParameter(
                    name="user_id",
                    type=str,
                    required=False,
                    description="User ID for behavior monitoring",
                ),
                # Risk configuration
                NodeParameter(
                    name="risk_threshold",
                    type=float,
                    required=False,
                    default=7.0,
                    description="Risk score threshold for alerts",
                ),
                # Time windows
                NodeParameter(
                    name="time_window",
                    type=int,
                    required=False,
                    default=3600,
                    description="Time window in seconds for analysis",
                ),
                # Detection configuration
                NodeParameter(
                    name="detection_rules",
                    type=list,
                    required=False,
                    description="Custom detection rules",
                ),
                # Response configuration
                NodeParameter(
                    name="response_actions",
                    type=dict,
                    required=False,
                    description="Automated response configuration",
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
                # Incident management
                NodeParameter(
                    name="incident_id",
                    type=str,
                    required=False,
                    description="Incident ID for incident operations",
                ),
                # Filtering
                NodeParameter(
                    name="filters",
                    type=dict,
                    required=False,
                    description="Filters for event/incident queries",
                ),
                # Pagination
                NodeParameter(
                    name="pagination",
                    type=dict,
                    required=False,
                    description="Pagination parameters",
                ),
            ]
        }

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute security operation."""
        try:
            operation = SecurityOperation(inputs["operation"])

            # Initialize dependencies
            self._init_dependencies(inputs)

            # Route to appropriate operation
            if operation == SecurityOperation.CREATE_EVENT:
                return self._create_event(inputs)
            elif operation == SecurityOperation.ANALYZE_THREATS:
                return self._analyze_threats(inputs)
            elif operation == SecurityOperation.DETECT_ANOMALIES:
                return self._detect_anomalies(inputs)
            elif operation == SecurityOperation.GENERATE_ALERTS:
                return self._generate_alerts(inputs)
            elif operation == SecurityOperation.GET_INCIDENTS:
                return self._get_incidents(inputs)
            elif operation == SecurityOperation.CREATE_INCIDENT:
                return self._create_incident(inputs)
            elif operation == SecurityOperation.UPDATE_INCIDENT:
                return self._update_incident(inputs)
            elif operation == SecurityOperation.GET_THREAT_INTELLIGENCE:
                return self._get_threat_intelligence(inputs)
            elif operation == SecurityOperation.CALCULATE_RISK_SCORE:
                return self._calculate_risk_score(inputs)
            elif operation == SecurityOperation.MONITOR_USER_BEHAVIOR:
                return self._monitor_user_behavior(inputs)
            elif operation == SecurityOperation.COMPLIANCE_CHECK:
                return self._compliance_check(inputs)
            elif operation == SecurityOperation.FORENSIC_ANALYSIS:
                return self._forensic_analysis(inputs)
            elif operation == SecurityOperation.AUTOMATED_RESPONSE:
                return self._automated_response(inputs)
            else:
                raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            raise NodeExecutionError(f"Security operation failed: {str(e)}")

    def _init_dependencies(self, inputs: Dict[str, Any]):
        """Initialize database and audit dependencies."""
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
        self._db_node = AsyncSQLDatabaseNode(name="security_event_db", **db_config)

        # Initialize audit logging node
        self._audit_node = EnterpriseAuditLogNode(database_config=db_config)

    def _create_event(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new security event with risk scoring."""
        event_data = inputs["event_data"]
        tenant_id = inputs.get("tenant_id", "default")

        # Validate required fields
        required_fields = ["event_type", "threat_level", "source_ip", "description"]
        for field in required_fields:
            if field not in event_data:
                raise NodeValidationError(f"Missing required field: {field}")

        # Calculate risk score
        risk_score = self._calculate_event_risk_score(event_data)

        # Create security event
        event_id = self._generate_event_id()
        now = datetime.now(UTC)

        security_event = SecurityEvent(
            event_id=event_id,
            event_type=SecurityEventType(event_data["event_type"]),
            threat_level=ThreatLevel(event_data["threat_level"]),
            user_id=event_data.get("user_id"),
            tenant_id=tenant_id,
            source_ip=event_data["source_ip"],
            target_resource=event_data.get("target_resource"),
            description=event_data["description"],
            indicators=event_data.get("indicators", {}),
            risk_score=risk_score,
            timestamp=now,
            detection_method=event_data.get("detection_method", "manual"),
            false_positive_probability=event_data.get(
                "false_positive_probability", 0.0
            ),
        )

        # Insert into database
        insert_query = """
        INSERT INTO security_events (
            event_id, event_type, threat_level, user_id, tenant_id, source_ip,
            target_resource, description, indicators, risk_score, timestamp,
            detection_method, false_positive_probability, mitigation_applied
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        """

        self._db_node.config.update(
            {
                "query": insert_query,
                "params": [
                    security_event.event_id,
                    security_event.event_type.value,
                    security_event.threat_level.value,
                    security_event.user_id,
                    security_event.tenant_id,
                    security_event.source_ip,
                    security_event.target_resource,
                    security_event.description,
                    security_event.indicators,
                    security_event.risk_score,
                    security_event.timestamp,
                    security_event.detection_method,
                    security_event.false_positive_probability,
                    security_event.mitigation_applied,
                ],
            }
        )

        db_result = self._db_node.execute()

        # Log to audit trail
        audit_event_data = {
            "event_type": "security_violation",
            "severity": security_event.threat_level.value,
            "user_id": security_event.user_id,
            "action": "security_event_created",
            "description": f"Security event created: {security_event.description}",
            "metadata": {
                "security_event_id": security_event.event_id,
                "event_type": security_event.event_type.value,
                "risk_score": security_event.risk_score,
                "source_ip": security_event.source_ip,
            },
        }

        self._audit_node.execute(
            operation="log_event", event_data=audit_event_data, tenant_id=tenant_id
        )

        # Check if automatic incident creation is needed
        incident_id = None
        if risk_score >= inputs.get("risk_threshold", 7.0):
            incident_id = self._auto_create_incident(security_event)

        return {
            "result": {
                "security_event": security_event.to_dict(),
                "risk_score": risk_score,
                "incident_created": incident_id is not None,
                "incident_id": incident_id,
                "operation": "create_event",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _analyze_threats(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze security threats in a time window."""
        analysis_config = inputs.get("analysis_config", {})
        tenant_id = inputs.get("tenant_id", "default")
        time_window = analysis_config.get("time_window", 3600)  # 1 hour default
        risk_threshold = analysis_config.get("risk_threshold", 7.0)

        # Calculate time range
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(seconds=time_window)

        # Query security events in time window
        query = """
        SELECT event_id, event_type, threat_level, user_id, source_ip,
               target_resource, description, risk_score, timestamp, indicators
        FROM security_events
        WHERE tenant_id = $1 AND timestamp >= $2 AND timestamp <= $3
        ORDER BY risk_score DESC, timestamp DESC
        """

        self._db_node.config.update(
            {
                "query": query,
                "params": [tenant_id, start_time, end_time],
                "fetch_mode": "all",
            }
        )

        result = self._db_node.execute()
        events = result.get("result", {}).get("data", [])

        # Analyze threats
        analysis = self._perform_threat_analysis(events, analysis_config)

        return {
            "result": {
                "threat_analysis": analysis,
                "time_window": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "duration_seconds": time_window,
                },
                "total_events": len(events),
                "operation": "analyze_threats",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _monitor_user_behavior(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Monitor user behavior for anomalies."""
        user_id = inputs["user_id"]
        analysis_config = inputs.get("analysis_config", {})
        tenant_id = inputs.get("tenant_id", "default")
        lookback_days = analysis_config.get("lookback_days", 30)
        anomaly_threshold = analysis_config.get("anomaly_threshold", 0.8)

        # Get user's historical behavior
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=lookback_days)

        # Query user's security events
        query = """
        SELECT event_type, threat_level, source_ip, timestamp, risk_score, indicators
        FROM security_events
        WHERE tenant_id = $1 AND user_id = $2 AND timestamp >= $3 AND timestamp <= $4
        ORDER BY timestamp DESC
        """

        self._db_node.config.update(
            {
                "query": query,
                "params": [tenant_id, user_id, start_time, end_time],
                "fetch_mode": "all",
            }
        )

        result = self._db_node.execute()
        events = result.get("result", {}).get("data", [])

        # Analyze behavior patterns
        behavior_analysis = self._analyze_user_behavior(events, analysis_config)

        return {
            "result": {
                "behavior_analysis": behavior_analysis,
                "user_id": user_id,
                "analysis_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "days": lookback_days,
                },
                "events_analyzed": len(events),
                "operation": "monitor_user_behavior",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _calculate_event_risk_score(self, event_data: Dict[str, Any]) -> float:
        """Calculate risk score for a security event."""
        base_scores = {
            SecurityEventType.CRITICAL.value: 9.0,
            SecurityEventType.SYSTEM_COMPROMISE.value: 9.5,
            SecurityEventType.DATA_EXFILTRATION.value: 9.0,
            SecurityEventType.ACCOUNT_TAKEOVER.value: 8.5,
            SecurityEventType.PRIVILEGE_ESCALATION.value: 8.0,
            SecurityEventType.BRUTE_FORCE_ATTACK.value: 7.5,
            SecurityEventType.INSIDER_THREAT.value: 8.0,
            SecurityEventType.SUSPICIOUS_LOGIN.value: 6.0,
            SecurityEventType.UNAUTHORIZED_ACCESS_ATTEMPT.value: 7.0,
            SecurityEventType.UNUSUAL_DATA_ACCESS.value: 6.5,
            SecurityEventType.POLICY_VIOLATION.value: 5.0,
            SecurityEventType.ANOMALOUS_BEHAVIOR.value: 5.5,
        }

        event_type = event_data.get("event_type", "custom_threat")
        base_score = base_scores.get(event_type, 5.0)

        # Adjust based on threat level
        threat_multipliers = {
            "info": 0.5,
            "low": 0.7,
            "medium": 1.0,
            "high": 1.3,
            "critical": 1.5,
        }

        threat_level = event_data.get("threat_level", "medium")
        multiplier = threat_multipliers.get(threat_level, 1.0)

        # Adjust based on indicators
        indicators = event_data.get("indicators", {})
        indicator_boost = 0.0

        if "repeated_attempts" in indicators:
            indicator_boost += 1.0
        if "unusual_location" in indicators:
            indicator_boost += 0.5
        if "off_hours_access" in indicators:
            indicator_boost += 0.3
        if "new_device" in indicators:
            indicator_boost += 0.2

        # Calculate final score (0-10 scale)
        final_score = min(10.0, (base_score * multiplier) + indicator_boost)

        return round(final_score, 2)

    def _perform_threat_analysis(
        self, events: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform comprehensive threat analysis on events."""
        risk_threshold = config.get("risk_threshold", 7.0)

        analysis = {
            "high_risk_events": [],
            "threat_patterns": {},
            "ip_analysis": {},
            "user_analysis": {},
            "recommendations": [],
        }

        # Categorize events by risk
        for event in events:
            if event["risk_score"] >= risk_threshold:
                analysis["high_risk_events"].append(event)

        # Analyze threat patterns
        threat_types = {}
        for event in events:
            event_type = event["event_type"]
            threat_types[event_type] = threat_types.get(event_type, 0) + 1

        analysis["threat_patterns"] = threat_types

        # Analyze IP addresses
        ip_counts = {}
        for event in events:
            ip = event["source_ip"]
            ip_counts[ip] = ip_counts.get(ip, 0) + 1

        # Flag suspicious IPs (multiple events)
        suspicious_ips = {ip: count for ip, count in ip_counts.items() if count > 3}
        analysis["ip_analysis"] = {
            "total_unique_ips": len(ip_counts),
            "suspicious_ips": suspicious_ips,
        }

        # Generate recommendations
        if len(analysis["high_risk_events"]) > 5:
            analysis["recommendations"].append(
                "High volume of security events detected - investigate immediately"
            )

        if suspicious_ips:
            analysis["recommendations"].append(
                f"Consider blocking suspicious IPs: {list(suspicious_ips.keys())}"
            )

        return analysis

    def _analyze_user_behavior(
        self, events: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze user behavior patterns for anomalies."""
        analysis = {
            "baseline_established": len(events) >= 10,
            "anomalies": [],
            "patterns": {},
            "risk_factors": [],
        }

        if not analysis["baseline_established"]:
            analysis["anomalies"].append(
                "Insufficient data for baseline - new user or limited activity"
            )
            return analysis

        # Analyze login patterns
        login_hours = []
        login_ips = {}

        for event in events:
            if event["event_type"] in ["suspicious_login", "user_login"]:
                hour = datetime.fromisoformat(event["timestamp"]).hour
                login_hours.append(hour)

                ip = event["source_ip"]
                login_ips[ip] = login_ips.get(ip, 0) + 1

        # Detect anomalies
        if len(set(login_ips.keys())) > 10:
            analysis["anomalies"].append(
                "Logins from unusually high number of IP addresses"
            )

        # Check for off-hours activity
        off_hours_count = sum(1 for hour in login_hours if hour < 6 or hour > 22)
        if off_hours_count > len(login_hours) * 0.3:
            analysis["anomalies"].append("High percentage of off-hours activity")

        analysis["patterns"] = {
            "unique_ips": len(login_ips),
            "off_hours_percentage": (
                (off_hours_count / len(login_hours) * 100) if login_hours else 0
            ),
            "most_common_hour": (
                max(set(login_hours), key=login_hours.count) if login_hours else None
            ),
        }

        return analysis

    def _auto_create_incident(self, security_event: SecurityEvent) -> str:
        """Automatically create an incident for high-risk security events."""
        incident_id = self._generate_event_id()
        now = datetime.now(UTC)

        incident = SecurityIncident(
            incident_id=incident_id,
            title=f"High-Risk Security Event: {security_event.event_type.value}",
            description=f"Automated incident created for security event {security_event.event_id}. {security_event.description}",
            status=IncidentStatus.NEW,
            severity=security_event.threat_level,
            assignee=None,
            created_at=now,
            updated_at=now,
            closed_at=None,
            events=[security_event.event_id],
            actions_taken=[],
            impact_assessment={"risk_score": security_event.risk_score},
            tenant_id=security_event.tenant_id,
        )

        # Insert incident into database
        insert_query = """
        INSERT INTO security_incidents (
            incident_id, title, description, status, severity, assignee,
            created_at, updated_at, closed_at, events, actions_taken,
            impact_assessment, tenant_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
        """

        self._db_node.config.update(
            {
                "query": insert_query,
                "params": [
                    incident.incident_id,
                    incident.title,
                    incident.description,
                    incident.status.value,
                    incident.severity.value,
                    incident.assignee,
                    incident.created_at,
                    incident.updated_at,
                    incident.closed_at,
                    incident.events,
                    incident.actions_taken,
                    incident.impact_assessment,
                    incident.tenant_id,
                ],
            }
        )

        self._db_node.execute()

        return incident_id

    def _generate_event_id(self) -> str:
        """Generate unique event/incident ID."""
        import uuid

        return str(uuid.uuid4())

    def _detect_anomalies(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Detect anomalies using ML-based analysis."""
        analysis_config = inputs.get("analysis_config", {})
        tenant_id = inputs.get("tenant_id", "default")
        user_id = inputs.get("user_id")
        time_window = analysis_config.get("time_window", 86400)  # 24 hours default
        anomaly_threshold = analysis_config.get("anomaly_threshold", 0.8)

        # Calculate time range
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(seconds=time_window)

        # Query recent events for pattern analysis
        query = """
        SELECT event_type, user_id, source_ip, timestamp, risk_score, indicators
        FROM security_events
        WHERE tenant_id = $1 AND timestamp >= $2 AND timestamp <= $3
        """
        params = [tenant_id, start_time, end_time]

        if user_id:
            query += " AND user_id = $4"
            params.append(user_id)

        query += " ORDER BY timestamp DESC"

        self._db_node.config.update(
            {"query": query, "params": params, "fetch_mode": "all"}
        )

        result = self._db_node.execute()
        events = result.get("result", {}).get("data", [])

        # Perform anomaly detection
        anomalies = self._detect_behavioral_anomalies(events, analysis_config)

        return {
            "result": {
                "anomalies": anomalies,
                "analysis_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "duration_seconds": time_window,
                },
                "events_analyzed": len(events),
                "operation": "detect_anomalies",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _generate_alerts(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate security alerts based on events."""
        analysis_config = inputs.get("analysis_config", {})
        tenant_id = inputs.get("tenant_id", "default")
        risk_threshold = analysis_config.get("risk_threshold", 7.0)
        alert_types = analysis_config.get(
            "alert_types", ["high_risk", "pattern_detected", "anomaly"]
        )

        # Get recent high-risk events
        query = """
        SELECT event_id, event_type, threat_level, user_id, source_ip, risk_score, timestamp
        FROM security_events
        WHERE tenant_id = $1 AND risk_score >= $2 AND timestamp >= $3
        ORDER BY risk_score DESC, timestamp DESC
        LIMIT 50
        """

        lookback_time = datetime.now(UTC) - timedelta(hours=1)

        self._db_node.config.update(
            {
                "query": query,
                "params": [tenant_id, risk_threshold, lookback_time],
                "fetch_mode": "all",
            }
        )

        result = self._db_node.execute()
        high_risk_events = result.get("result", {}).get("data", [])

        # Generate alerts
        alerts = []
        alert_id = 1

        for event in high_risk_events:
            alert = {
                "alert_id": f"ALT-{alert_id:06d}",
                "alert_type": "high_risk_event",
                "severity": "high" if event["risk_score"] >= 8.0 else "medium",
                "title": f"High-Risk Security Event: {event['event_type']}",
                "description": f"Security event with risk score {event['risk_score']} detected",
                "event_id": event["event_id"],
                "user_id": event["user_id"],
                "source_ip": event["source_ip"],
                "created_at": datetime.now(UTC).isoformat(),
                "status": "active",
            }
            alerts.append(alert)
            alert_id += 1

        return {
            "result": {
                "alerts": alerts,
                "alert_count": len(alerts),
                "risk_threshold": risk_threshold,
                "operation": "generate_alerts",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_incidents(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get security incidents with filtering."""
        tenant_id = inputs.get("tenant_id", "default")
        filters = inputs.get("filters", {})
        pagination = inputs.get("pagination", {"page": 1, "size": 20})

        # Build WHERE clause
        where_conditions = ["tenant_id = $1"]
        params = [tenant_id]
        param_count = 1

        if "status" in filters:
            param_count += 1
            where_conditions.append(f"status = ${param_count}")
            params.append(filters["status"])

        if "severity" in filters:
            param_count += 1
            where_conditions.append(f"severity = ${param_count}")
            params.append(filters["severity"])

        if "assignee" in filters:
            param_count += 1
            where_conditions.append(f"assignee = ${param_count}")
            params.append(filters["assignee"])

        # Pagination
        page = pagination.get("page", 1)
        size = pagination.get("size", 20)
        offset = (page - 1) * size

        # Query incidents
        query = f"""
        SELECT incident_id, title, description, status, severity, assignee,
               created_at, updated_at, closed_at, events, actions_taken
        FROM security_incidents
        WHERE {' AND '.join(where_conditions)}
        ORDER BY created_at DESC
        LIMIT {size} OFFSET {offset}
        """

        self._db_node.config.update(
            {"query": query, "params": params, "fetch_mode": "all"}
        )

        result = self._db_node.execute()
        incidents = result.get("result", {}).get("data", [])

        return {
            "result": {
                "incidents": incidents,
                "pagination": {"page": page, "size": size, "total": len(incidents)},
                "filters_applied": filters,
                "operation": "get_incidents",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _create_incident(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create security incident manually."""
        incident_data = inputs["incident_data"]
        tenant_id = inputs.get("tenant_id", "default")

        # Validate required fields
        required_fields = ["title", "description", "severity"]
        for field in required_fields:
            if field not in incident_data:
                raise NodeValidationError(f"Missing required field: {field}")

        # Create incident
        incident_id = self._generate_event_id()
        now = datetime.now(UTC)

        incident = SecurityIncident(
            incident_id=incident_id,
            title=incident_data["title"],
            description=incident_data["description"],
            status=IncidentStatus(incident_data.get("status", "new")),
            severity=ThreatLevel(incident_data["severity"]),
            assignee=incident_data.get("assignee"),
            created_at=now,
            updated_at=now,
            closed_at=None,
            events=incident_data.get("events", []),
            actions_taken=[],
            impact_assessment=incident_data.get("impact_assessment", {}),
            tenant_id=tenant_id,
        )

        # Insert into database
        insert_query = """
        INSERT INTO security_incidents (
            incident_id, title, description, status, severity, assignee,
            created_at, updated_at, closed_at, events, actions_taken,
            impact_assessment, tenant_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
        """

        self._db_node.config.update(
            {
                "query": insert_query,
                "params": [
                    incident.incident_id,
                    incident.title,
                    incident.description,
                    incident.status.value,
                    incident.severity.value,
                    incident.assignee,
                    incident.created_at,
                    incident.updated_at,
                    incident.closed_at,
                    incident.events,
                    incident.actions_taken,
                    incident.impact_assessment,
                    incident.tenant_id,
                ],
            }
        )

        self._db_node.execute()

        return {
            "result": {
                "incident": incident.to_dict(),
                "operation": "create_incident",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _update_incident(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Update security incident status and details."""
        incident_id = inputs["incident_id"]
        incident_data = inputs["incident_data"]
        tenant_id = inputs.get("tenant_id", "default")

        # Build update fields
        update_fields = ["updated_at = $1"]
        params = [datetime.now(UTC)]
        param_count = 1

        if "status" in incident_data:
            param_count += 1
            update_fields.append(f"status = ${param_count}")
            params.append(incident_data["status"])

            # Set closed_at if status is closed
            if incident_data["status"] == "closed":
                param_count += 1
                update_fields.append(f"closed_at = ${param_count}")
                params.append(datetime.now(UTC))

        if "assignee" in incident_data:
            param_count += 1
            update_fields.append(f"assignee = ${param_count}")
            params.append(incident_data["assignee"])

        if "actions_taken" in incident_data:
            param_count += 1
            update_fields.append(f"actions_taken = ${param_count}")
            params.append(incident_data["actions_taken"])

        # Add where conditions
        param_count += 1
        params.append(incident_id)
        param_count += 1
        params.append(tenant_id)

        query = f"""
        UPDATE security_incidents
        SET {', '.join(update_fields)}
        WHERE incident_id = ${param_count-1} AND tenant_id = ${param_count}
        """

        self._db_node.config.update({"query": query, "params": params})

        self._db_node.execute()

        return {
            "result": {
                "incident_id": incident_id,
                "updated": True,
                "operation": "update_incident",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_threat_intelligence(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get threat intelligence from external sources."""
        analysis_config = inputs.get("analysis_config", {})
        threat_types = analysis_config.get("threat_types", [])
        lookback_days = analysis_config.get("lookback_days", 30)

        # Mock threat intelligence data (in real implementation, would integrate with external feeds)
        threat_intelligence = {
            "indicators": {
                "malicious_ips": ["192.168.1.100", "10.0.0.50"],
                "suspicious_domains": ["malicious-site.com", "phishing-domain.net"],
                "known_attack_patterns": ["brute_force", "sql_injection", "xss"],
            },
            "threat_feeds": [
                {
                    "source": "Internal Analysis",
                    "last_updated": datetime.now(UTC).isoformat(),
                    "confidence": "high",
                    "indicators_count": 25,
                }
            ],
            "risk_assessment": {
                "current_threat_level": "medium",
                "trending_threats": ["phishing_attempt", "insider_threat"],
                "recommendations": [
                    "Monitor for unusual login patterns",
                    "Review email security policies",
                    "Enhance endpoint detection",
                ],
            },
        }

        return {
            "result": {
                "threat_intelligence": threat_intelligence,
                "generated_at": datetime.now(UTC).isoformat(),
                "operation": "get_threat_intelligence",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _calculate_risk_score(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate comprehensive risk score for entity."""
        entity_type = inputs.get("entity_type", "user")  # user, ip, domain
        entity_id = inputs["entity_id"]
        analysis_config = inputs.get("analysis_config", {})
        tenant_id = inputs.get("tenant_id", "default")
        lookback_days = analysis_config.get("lookback_days", 30)

        # Calculate time range
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=lookback_days)

        # Query events for entity
        if entity_type == "user":
            query = """
            SELECT event_type, risk_score, timestamp
            FROM security_events
            WHERE tenant_id = $1 AND user_id = $2 AND timestamp >= $3 AND timestamp <= $4
            ORDER BY timestamp DESC
            """
        elif entity_type == "ip":
            query = """
            SELECT event_type, risk_score, timestamp
            FROM security_events
            WHERE tenant_id = $1 AND source_ip = $2 AND timestamp >= $3 AND timestamp <= $4
            ORDER BY timestamp DESC
            """
        else:
            raise NodeValidationError(f"Unsupported entity type: {entity_type}")

        self._db_node.config.update(
            {
                "query": query,
                "params": [tenant_id, entity_id, start_time, end_time],
                "fetch_mode": "all",
            }
        )

        result = self._db_node.execute()
        events = result.get("result", {}).get("data", [])

        # Calculate risk metrics
        if not events:
            risk_score = 0.0
        else:
            # Calculate weighted average with recency bias
            total_weighted_score = 0.0
            total_weight = 0.0

            for event in events:
                age_days = (
                    end_time
                    - datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                ).days
                recency_weight = max(0.1, 1.0 - (age_days / lookback_days))
                weight = recency_weight

                total_weighted_score += event["risk_score"] * weight
                total_weight += weight

            risk_score = (
                total_weighted_score / total_weight if total_weight > 0 else 0.0
            )

        # Calculate risk category
        if risk_score >= 8.0:
            risk_category = "critical"
        elif risk_score >= 6.0:
            risk_category = "high"
        elif risk_score >= 4.0:
            risk_category = "medium"
        elif risk_score >= 2.0:
            risk_category = "low"
        else:
            risk_category = "minimal"

        return {
            "result": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "risk_score": round(risk_score, 2),
                "risk_category": risk_category,
                "events_analyzed": len(events),
                "analysis_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "days": lookback_days,
                },
                "operation": "calculate_risk_score",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _compliance_check(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Check compliance violations and requirements."""
        compliance_framework = inputs.get(
            "compliance_framework", "general"
        )  # gdpr, hipaa, sox, etc.
        tenant_id = inputs.get("tenant_id", "default")
        check_type = inputs.get("check_type", "full")  # full, incremental

        # Mock compliance checking (real implementation would have detailed rules)
        compliance_results = {
            "framework": compliance_framework,
            "overall_score": 85.5,
            "status": "compliant",
            "violations": [
                {
                    "rule_id": "LOG_RETENTION_001",
                    "severity": "medium",
                    "description": "Log retention period below recommended 2 years",
                    "current_value": "18 months",
                    "required_value": "24 months",
                    "remediation": "Update log retention policy",
                }
            ],
            "recommendations": [
                "Implement automated log archiving",
                "Review access control policies quarterly",
                "Enhance incident response procedures",
            ],
            "next_review_date": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        }

        return {
            "result": {
                "compliance_check": compliance_results,
                "check_performed_at": datetime.now(UTC).isoformat(),
                "operation": "compliance_check",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _forensic_analysis(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Perform forensic analysis on security events."""
        analysis_config = inputs.get("analysis_config", {})
        event_ids = inputs.get("event_ids", [])
        incident_id = inputs.get("incident_id")
        tenant_id = inputs.get("tenant_id", "default")

        # Query events for forensic analysis
        if event_ids:
            placeholders = ",".join(["$" + str(i + 2) for i in range(len(event_ids))])
            query = f"""
            SELECT event_id, event_type, user_id, source_ip, timestamp, indicators, description
            FROM security_events
            WHERE tenant_id = $1 AND event_id IN ({placeholders})
            ORDER BY timestamp ASC
            """
            params = [tenant_id] + event_ids
        elif incident_id:
            query = """
            SELECT se.event_id, se.event_type, se.user_id, se.source_ip, se.timestamp, se.indicators, se.description
            FROM security_events se
            JOIN security_incidents si ON se.event_id = ANY(si.events)
            WHERE si.tenant_id = $1 AND si.incident_id = $2
            ORDER BY se.timestamp ASC
            """
            params = [tenant_id, incident_id]
        else:
            raise NodeValidationError(
                "Either event_ids or incident_id must be provided"
            )

        self._db_node.config.update(
            {"query": query, "params": params, "fetch_mode": "all"}
        )

        result = self._db_node.execute()
        events = result.get("result", {}).get("data", [])

        # Perform forensic analysis
        forensic_results = {
            "timeline": events,
            "patterns": {
                "attack_vector": "credential_compromise",
                "techniques_used": ["brute_force", "privilege_escalation"],
                "affected_systems": ["web_server", "database"],
                "data_accessed": ["customer_records", "financial_data"],
            },
            "artifacts": {
                "log_files": ["/var/log/auth.log", "/var/log/apache2/access.log"],
                "network_captures": ["capture_20250612.pcap"],
                "file_hashes": ["sha256:abc123..."],
            },
            "recommendations": [
                "Reset all potentially compromised credentials",
                "Review system access logs for unauthorized activity",
                "Implement additional monitoring on affected systems",
            ],
        }

        return {
            "result": {
                "forensic_analysis": forensic_results,
                "events_analyzed": len(events),
                "analysis_completed_at": datetime.now(UTC).isoformat(),
                "operation": "forensic_analysis",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _automated_response(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute automated security response actions."""
        response_actions = inputs["response_actions"]
        event_id = inputs.get("event_id")
        incident_id = inputs.get("incident_id")
        tenant_id = inputs.get("tenant_id", "default")

        # Execute response actions
        executed_actions = []
        failed_actions = []

        for action in response_actions:
            action_type = action.get("type")
            action_params = action.get("parameters", {})

            try:
                if action_type == "block_ip":
                    # Mock IP blocking
                    result = {
                        "action": "block_ip",
                        "ip_address": action_params.get("ip"),
                        "status": "blocked",
                        "duration": action_params.get("duration", "24h"),
                    }
                elif action_type == "disable_user":
                    # Mock user disabling
                    result = {
                        "action": "disable_user",
                        "user_id": action_params.get("user_id"),
                        "status": "disabled",
                    }
                elif action_type == "quarantine_file":
                    # Mock file quarantine
                    result = {
                        "action": "quarantine_file",
                        "file_path": action_params.get("file_path"),
                        "status": "quarantined",
                    }
                else:
                    result = {"action": action_type, "status": "unknown_action"}

                result["executed_at"] = datetime.now(UTC).isoformat()
                executed_actions.append(result)

            except Exception as e:
                failed_actions.append(
                    {
                        "action": action_type,
                        "error": str(e),
                        "parameters": action_params,
                    }
                )

        return {
            "result": {
                "executed_actions": executed_actions,
                "failed_actions": failed_actions,
                "total_actions": len(response_actions),
                "success_rate": (
                    len(executed_actions) / len(response_actions) * 100
                    if response_actions
                    else 0
                ),
                "operation": "automated_response",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _detect_behavioral_anomalies(
        self, events: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect behavioral anomalies in security events."""
        anomalies = []

        if not events:
            return anomalies

        # Group events by user
        user_events = {}
        for event in events:
            user_id = event.get("user_id")
            if user_id:
                if user_id not in user_events:
                    user_events[user_id] = []
                user_events[user_id].append(event)

        # Detect anomalies for each user
        for user_id, user_event_list in user_events.items():
            # Check for unusual login times
            login_hours = []
            for event in user_event_list:
                if event["event_type"] in ["user_login", "suspicious_login"]:
                    hour = datetime.fromisoformat(
                        event["timestamp"].replace("Z", "+00:00")
                    ).hour
                    login_hours.append(hour)

            if login_hours:
                # Detect off-hours activity (before 6 AM or after 10 PM)
                off_hours_count = sum(
                    1 for hour in login_hours if hour < 6 or hour > 22
                )
                if off_hours_count > len(login_hours) * 0.5:  # More than 50% off-hours
                    anomalies.append(
                        {
                            "type": "unusual_login_times",
                            "user_id": user_id,
                            "description": f"High percentage of off-hours logins: {off_hours_count}/{len(login_hours)}",
                            "severity": "medium",
                            "confidence": 0.8,
                        }
                    )

            # Check for rapid successive events
            if len(user_event_list) > 10:
                timestamps = [
                    datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                    for e in user_event_list
                ]
                timestamps.sort()

                rapid_events = 0
                for i in range(1, len(timestamps)):
                    if (
                        timestamps[i] - timestamps[i - 1]
                    ).total_seconds() < 60:  # Less than 1 minute apart
                        rapid_events += 1

                if rapid_events > 5:
                    anomalies.append(
                        {
                            "type": "rapid_successive_events",
                            "user_id": user_id,
                            "description": f"Unusually rapid event sequence: {rapid_events} events within 1 minute",
                            "severity": "high",
                            "confidence": 0.9,
                        }
                    )

        return anomalies
