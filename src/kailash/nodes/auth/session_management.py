"""
Advanced session management with security tracking.

This module provides comprehensive session management capabilities including
concurrent session limits, device tracking, anomaly detection, and automatic
session cleanup with security event integration.
"""

import hashlib
import json
import logging
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.mixins import LoggingMixin, PerformanceMixin, SecurityMixin
from kailash.nodes.security.audit_log import AuditLogNode
from kailash.nodes.security.security_event import SecurityEventNode

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """Session status enumeration."""

    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    SUSPICIOUS = "suspicious"


@dataclass
class DeviceInfo:
    """Device information for session tracking."""

    device_id: str
    device_type: str  # desktop, mobile, tablet
    os_name: str
    os_version: str
    browser_name: str
    browser_version: str
    user_agent: str
    fingerprint: str


@dataclass
class SessionData:
    """Complete session data."""

    session_id: str
    user_id: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    ip_address: str
    device_info: DeviceInfo
    status: SessionStatus

    # Security tracking
    login_method: str  # password, mfa, sso
    risk_score: float
    anomaly_flags: List[str]

    # Activity tracking
    page_views: int
    actions_performed: int
    data_accessed_mb: float

    # Geo-location (if available)
    country: Optional[str] = None
    city: Optional[str] = None

    # Session metadata
    metadata: Dict[str, Any] = None


@register_node()
class SessionManagementNode(SecurityMixin, PerformanceMixin, LoggingMixin, Node):
    """Advanced session management with security tracking.

    This node provides comprehensive session management including:
    - Concurrent session limits per user
    - Device fingerprinting and tracking
    - Idle and absolute session timeouts
    - Anomaly detection for sessions
    - Geographic location tracking
    - Session hijacking detection
    - Automatic cleanup and security logging

    Example:
        >>> session_mgr = SessionManagementNode(
        ...     max_sessions=3,
        ...     idle_timeout=timedelta(minutes=30),
        ...     absolute_timeout=timedelta(hours=8),
        ...     track_devices=True
        ... )
        >>>
        >>> # Create new session
        >>> device_info = {
        ...     "device_type": "desktop",
        ...     "os_name": "Windows",
        ...     "browser_name": "Chrome",
        ...     "user_agent": "Mozilla/5.0..."
        ... }
        >>>
        >>> result = session_mgr.execute(
        ...     action="create",
        ...     user_id="user123",
        ...     ip_address="192.168.1.100",
        ...     device_info=device_info
        ... )
        >>> print(f"Session ID: {result['session_id']}")
        >>>
        >>> # Validate session
        >>> validation = session_mgr.execute(
        ...     action="validate",
        ...     session_id=result['session_id']
        ... )
        >>> print(f"Valid: {validation['valid']}")
    """

    def __init__(
        self,
        name: str = "session_management",
        max_sessions: int = 3,
        idle_timeout: timedelta = timedelta(minutes=30),
        absolute_timeout: timedelta = timedelta(hours=8),
        track_devices: bool = True,
        enable_geo_tracking: bool = False,
        anomaly_detection: bool = True,
        cleanup_interval: int = 300,  # 5 minutes
        **kwargs,
    ):
        """Initialize session management node.

        Args:
            name: Node name
            max_sessions: Maximum concurrent sessions per user
            idle_timeout: Idle session timeout
            absolute_timeout: Absolute session timeout
            track_devices: Enable device tracking and fingerprinting
            enable_geo_tracking: Enable geographic location tracking
            anomaly_detection: Enable session anomaly detection
            cleanup_interval: Cleanup interval in seconds
            **kwargs: Additional node parameters
        """
        # Set attributes before calling super().__init__()
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.absolute_timeout = absolute_timeout
        self.track_devices = track_devices
        self.enable_geo_tracking = enable_geo_tracking
        self.anomaly_detection = anomaly_detection
        self.cleanup_interval = cleanup_interval

        # Initialize parent classes
        super().__init__(name=name, **kwargs)

        # Initialize audit logging and security events
        self.audit_log_node = AuditLogNode(name=f"{name}_audit_log")
        self.security_event_node = SecurityEventNode(name=f"{name}_security_events")

        # Session storage
        self.sessions: Dict[str, SessionData] = {}
        self.user_sessions: Dict[str, Set[str]] = {}  # user_id -> set of session_ids
        self.device_sessions: Dict[str, Set[str]] = (
            {}
        )  # device_fingerprint -> set of session_ids

        # Thread locks for concurrent access
        self._sessions_lock = threading.Lock()

        # Session statistics
        self.session_stats = {
            "total_sessions_created": 0,
            "active_sessions": 0,
            "expired_sessions_cleaned": 0,
            "concurrent_limit_hits": 0,
            "anomalies_detected": 0,
            "devices_tracked": 0,
            "sessions_terminated": 0,
        }

        # Last cleanup time
        self._last_cleanup = datetime.now(UTC)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters for validation and documentation.

        Returns:
            Dictionary mapping parameter names to NodeParameter objects
        """
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                description="Session action to perform",
                required=True,
            ),
            "session_id": NodeParameter(
                name="session_id",
                type=str,
                description="Session ID for operations",
                required=False,
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                description="User ID for session operations",
                required=False,
            ),
            "ip_address": NodeParameter(
                name="ip_address",
                type=str,
                description="Client IP address",
                required=False,
            ),
            "device_info": NodeParameter(
                name="device_info",
                type=dict,
                description="Device information for tracking",
                required=False,
                default={},
            ),
        }

    def run(
        self,
        action: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        device_info: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Run session management operation.

        Args:
            action: Session action (create, validate, update, terminate, cleanup)
            session_id: Session ID for operations
            user_id: User ID for session operations
            ip_address: Client IP address
            device_info: Device information
            **kwargs: Additional parameters

        Returns:
            Dictionary containing operation results
        """
        start_time = datetime.now(UTC)
        device_info = device_info or {}

        try:
            # Validate and sanitize inputs
            safe_params = self.validate_and_sanitize_inputs(
                {
                    "action": action,
                    "session_id": session_id or "",
                    "user_id": user_id or "",
                    "ip_address": ip_address or "",
                    "device_info": device_info,
                }
            )

            action = safe_params["action"]
            session_id = safe_params["session_id"] or None
            user_id = safe_params["user_id"] or None
            ip_address = safe_params["ip_address"] or None
            device_info = safe_params["device_info"]

            self.log_node_execution("session_operation_start", action=action)

            # Perform periodic cleanup
            self._maybe_cleanup_sessions()

            # Route to appropriate action handler
            if action == "create":
                if not user_id or not ip_address:
                    return {
                        "success": False,
                        "error": "user_id and ip_address required for create",
                    }
                result = self._create_session(user_id, ip_address, device_info)
                self.session_stats["total_sessions_created"] += 1

            elif action == "validate":
                if not session_id:
                    return {
                        "success": False,
                        "error": "session_id required for validate",
                    }
                result = self._validate_session(session_id)

            elif action == "update":
                if not session_id:
                    return {"success": False, "error": "session_id required for update"}
                result = self._update_session_activity(session_id, kwargs)

            elif action == "terminate":
                if session_id:
                    result = self._terminate_session(
                        session_id, kwargs.get("reason", "user_logout")
                    )
                elif user_id:
                    result = self._terminate_user_sessions(
                        user_id, kwargs.get("reason", "admin_action")
                    )
                else:
                    return {
                        "success": False,
                        "error": "session_id or user_id required for terminate",
                    }

            elif action == "cleanup":
                result = self._cleanup_expired_sessions()

            elif action == "list":
                if not user_id:
                    return {"success": False, "error": "user_id required for list"}
                result = self._list_user_sessions(user_id)

            elif action == "stats":
                result = self._get_session_statistics()

            else:
                result = {"success": False, "error": f"Unknown action: {action}"}

            # Add timing information
            processing_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            result["processing_time_ms"] = processing_time
            result["timestamp"] = start_time.isoformat()

            self.log_node_execution(
                "session_operation_complete",
                action=action,
                success=result.get("success", False),
                processing_time_ms=processing_time,
            )

            return result

        except Exception as e:
            self.log_error_with_traceback(e, "session_management")
            raise

    def _create_session(
        self, user_id: str, ip_address: str, device_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create new user session.

        Args:
            user_id: User ID
            ip_address: Client IP address
            device_info: Device information

        Returns:
            Session creation result
        """
        with self._sessions_lock:
            # Check concurrent session limit
            user_session_count = len(self.user_sessions.get(user_id, set()))
            if user_session_count >= self.max_sessions:
                self.session_stats["concurrent_limit_hits"] += 1

                # Terminate oldest session
                oldest_session = self._get_oldest_user_session(user_id)
                if oldest_session:
                    self._terminate_session_internal(
                        oldest_session, "concurrent_limit_exceeded"
                    )
                    self._log_security_event(
                        user_id,
                        "session_limit_exceeded",
                        "medium",
                        {"max_sessions": self.max_sessions},
                    )

            # Generate session ID
            session_id = self._generate_session_id()

            # Process device information
            device = self._process_device_info(device_info, ip_address)

            # Calculate session risk score
            risk_score = self._calculate_session_risk(user_id, ip_address, device)

            # Create session data
            current_time = datetime.now(UTC)
            session_data = SessionData(
                session_id=session_id,
                user_id=user_id,
                created_at=current_time,
                last_activity=current_time,
                expires_at=current_time + self.absolute_timeout,
                ip_address=ip_address,
                device_info=device,
                status=SessionStatus.ACTIVE,
                login_method="password",  # Default, should be set by caller
                risk_score=risk_score,
                anomaly_flags=[],
                page_views=0,
                actions_performed=0,
                data_accessed_mb=0.0,
                metadata={},
            )

            # Add geo-location if enabled
            if self.enable_geo_tracking:
                location = self._get_ip_location(ip_address)
                session_data.country = location.get("country")
                session_data.city = location.get("city")

            # Store session
            self.sessions[session_id] = session_data

            # Update user sessions mapping
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = set()
            self.user_sessions[user_id].add(session_id)

            # Update device sessions mapping if tracking enabled
            if self.track_devices:
                device_fingerprint = device.fingerprint
                if device_fingerprint not in self.device_sessions:
                    self.device_sessions[device_fingerprint] = set()
                    self.session_stats["devices_tracked"] += 1
                self.device_sessions[device_fingerprint].add(session_id)

            # Update statistics
            self.session_stats["active_sessions"] += 1

            # Audit log session creation
            self._audit_session_operation("create", session_data)

            # Check for anomalies
            if self.anomaly_detection:
                anomalies = self._detect_session_anomalies(session_data)
                if anomalies:
                    session_data.anomaly_flags.extend(anomalies)
                    self.session_stats["anomalies_detected"] += len(anomalies)
                    self._log_security_event(
                        user_id,
                        "session_anomaly_detected",
                        "medium",
                        {"anomalies": anomalies, "session_id": session_id},
                    )

            return {
                "success": True,
                "session_id": session_id,
                "expires_at": session_data.expires_at.isoformat(),
                "risk_score": risk_score,
                "device_tracked": self.track_devices,
                "anomalies": session_data.anomaly_flags,
                "concurrent_sessions": len(self.user_sessions[user_id]),
            }

    def _validate_session(self, session_id: str) -> Dict[str, Any]:
        """Validate session and check for anomalies.

        Args:
            session_id: Session ID to validate

        Returns:
            Session validation result
        """
        with self._sessions_lock:
            if session_id not in self.sessions:
                return {"success": True, "valid": False, "reason": "session_not_found"}

            session_data = self.sessions[session_id]
            current_time = datetime.now(UTC)

            # Check if session is expired
            if current_time > session_data.expires_at:
                session_data.status = SessionStatus.EXPIRED
                self._cleanup_session_internal(session_id)
                return {"success": True, "valid": False, "reason": "session_expired"}

            # Check idle timeout
            idle_time = current_time - session_data.last_activity
            if idle_time > self.idle_timeout:
                session_data.status = SessionStatus.IDLE
                if idle_time > self.idle_timeout * 2:  # Grace period
                    self._cleanup_session_internal(session_id)
                    return {
                        "success": True,
                        "valid": False,
                        "reason": "session_idle_timeout",
                    }

            # Check for suspicious activity
            if session_data.status == SessionStatus.SUSPICIOUS:
                return {"success": True, "valid": False, "reason": "session_suspicious"}

            # Session is valid
            return {
                "success": True,
                "valid": True,
                "session_data": {
                    "user_id": session_data.user_id,
                    "created_at": session_data.created_at.isoformat(),
                    "last_activity": session_data.last_activity.isoformat(),
                    "expires_at": session_data.expires_at.isoformat(),
                    "status": session_data.status.value,
                    "risk_score": session_data.risk_score,
                    "anomaly_flags": session_data.anomaly_flags,
                    "device_type": session_data.device_info.device_type,
                    "location": (
                        f"{session_data.city}, {session_data.country}"
                        if session_data.city
                        else None
                    ),
                },
            }

    def _update_session_activity(
        self, session_id: str, activity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update session activity and check for anomalies.

        Args:
            session_id: Session ID
            activity_data: Activity data to record

        Returns:
            Update result
        """
        with self._sessions_lock:
            if session_id not in self.sessions:
                return {"success": False, "error": "session_not_found"}

            session_data = self.sessions[session_id]
            current_time = datetime.now(UTC)

            # Update last activity
            session_data.last_activity = current_time
            session_data.status = SessionStatus.ACTIVE

            # Update activity counters
            if "page_views" in activity_data:
                session_data.page_views += activity_data["page_views"]

            if "actions_performed" in activity_data:
                session_data.actions_performed += activity_data["actions_performed"]

            if "data_accessed_mb" in activity_data:
                session_data.data_accessed_mb += activity_data["data_accessed_mb"]

            # Check for new anomalies
            if self.anomaly_detection:
                new_anomalies = self._detect_activity_anomalies(
                    session_data, activity_data
                )
                if new_anomalies:
                    session_data.anomaly_flags.extend(new_anomalies)
                    self.session_stats["anomalies_detected"] += len(new_anomalies)

                    # Mark session as suspicious if too many anomalies
                    if len(session_data.anomaly_flags) > 3:
                        session_data.status = SessionStatus.SUSPICIOUS
                        self._log_security_event(
                            session_data.user_id,
                            "session_marked_suspicious",
                            "high",
                            {
                                "session_id": session_id,
                                "anomalies": session_data.anomaly_flags,
                            },
                        )

            return {
                "success": True,
                "session_updated": True,
                "status": session_data.status.value,
                "new_anomalies": new_anomalies if self.anomaly_detection else [],
                "total_anomalies": len(session_data.anomaly_flags),
            }

    def _terminate_session(
        self, session_id: str, reason: str = "user_logout"
    ) -> Dict[str, Any]:
        """Terminate user session.

        Args:
            session_id: Session ID to terminate
            reason: Termination reason

        Returns:
            Termination result
        """
        with self._sessions_lock:
            if session_id not in self.sessions:
                return {"success": False, "error": "session_not_found"}

            session_data = self.sessions[session_id]
            self._terminate_session_internal(session_id, reason)

            # Audit log termination
            self._audit_session_operation("terminate", session_data, {"reason": reason})

            return {
                "success": True,
                "session_terminated": True,
                "reason": reason,
                "user_id": session_data.user_id,
            }

    def _terminate_user_sessions(
        self, user_id: str, reason: str = "admin_action"
    ) -> Dict[str, Any]:
        """Terminate all sessions for a user.

        Args:
            user_id: User ID
            reason: Termination reason

        Returns:
            Termination result
        """
        with self._sessions_lock:
            if user_id not in self.user_sessions:
                return {"success": True, "sessions_terminated": 0}

            session_ids = list(self.user_sessions[user_id])
            terminated_count = 0

            for session_id in session_ids:
                if session_id in self.sessions:
                    self._terminate_session_internal(session_id, reason)
                    terminated_count += 1

            # Log security event for mass termination
            if terminated_count > 1:
                self._log_security_event(
                    user_id,
                    "mass_session_termination",
                    "medium",
                    {"sessions_terminated": terminated_count, "reason": reason},
                )

            return {
                "success": True,
                "sessions_terminated": terminated_count,
                "reason": reason,
            }

    def _terminate_session_internal(self, session_id: str, reason: str) -> None:
        """Internal session termination.

        Args:
            session_id: Session ID
            reason: Termination reason
        """
        if session_id not in self.sessions:
            return

        session_data = self.sessions[session_id]

        # Update status
        session_data.status = SessionStatus.TERMINATED

        # Remove from active sessions
        self._cleanup_session_internal(session_id)

        # Update statistics
        self.session_stats["sessions_terminated"] += 1

    def _cleanup_session_internal(self, session_id: str) -> None:
        """Internal session cleanup.

        Args:
            session_id: Session ID to cleanup
        """
        if session_id not in self.sessions:
            return

        session_data = self.sessions[session_id]

        # Remove from user sessions
        if session_data.user_id in self.user_sessions:
            self.user_sessions[session_data.user_id].discard(session_id)
            if not self.user_sessions[session_data.user_id]:
                del self.user_sessions[session_data.user_id]

        # Remove from device sessions
        if self.track_devices:
            device_fingerprint = session_data.device_info.fingerprint
            if device_fingerprint in self.device_sessions:
                self.device_sessions[device_fingerprint].discard(session_id)
                if not self.device_sessions[device_fingerprint]:
                    del self.device_sessions[device_fingerprint]

        # Remove session
        del self.sessions[session_id]

        # Update statistics
        if self.session_stats["active_sessions"] > 0:
            self.session_stats["active_sessions"] -= 1

    def _cleanup_expired_sessions(self) -> Dict[str, Any]:
        """Clean up expired and idle sessions.

        Returns:
            Cleanup result
        """
        current_time = datetime.now(UTC)
        expired_sessions = []
        idle_sessions = []

        with self._sessions_lock:
            for session_id, session_data in list(self.sessions.items()):
                # Check for expired sessions
                if current_time > session_data.expires_at:
                    expired_sessions.append(session_id)
                    continue

                # Check for idle sessions beyond grace period
                idle_time = current_time - session_data.last_activity
                if idle_time > self.idle_timeout * 2:  # Grace period
                    idle_sessions.append(session_id)

            # Clean up expired and idle sessions
            for session_id in expired_sessions + idle_sessions:
                self._cleanup_session_internal(session_id)

        # Update statistics
        total_cleaned = len(expired_sessions) + len(idle_sessions)
        self.session_stats["expired_sessions_cleaned"] += total_cleaned

        # Update last cleanup time
        self._last_cleanup = current_time

        return {
            "success": True,
            "expired_sessions_cleaned": len(expired_sessions),
            "idle_sessions_cleaned": len(idle_sessions),
            "total_cleaned": total_cleaned,
        }

    def _maybe_cleanup_sessions(self) -> None:
        """Perform cleanup if enough time has passed."""
        current_time = datetime.now(UTC)
        if (current_time - self._last_cleanup).total_seconds() > self.cleanup_interval:
            self._cleanup_expired_sessions()

    def _list_user_sessions(self, user_id: str) -> Dict[str, Any]:
        """List all sessions for a user.

        Args:
            user_id: User ID

        Returns:
            List of user sessions
        """
        with self._sessions_lock:
            if user_id not in self.user_sessions:
                return {"success": True, "sessions": []}

            sessions_list = []
            for session_id in self.user_sessions[user_id]:
                if session_id in self.sessions:
                    session_data = self.sessions[session_id]
                    sessions_list.append(
                        {
                            "session_id": session_id,
                            "created_at": session_data.created_at.isoformat(),
                            "last_activity": session_data.last_activity.isoformat(),
                            "status": session_data.status.value,
                            "ip_address": session_data.ip_address,
                            "device_type": session_data.device_info.device_type,
                            "device_os": f"{session_data.device_info.os_name} {session_data.device_info.os_version}",
                            "browser": f"{session_data.device_info.browser_name} {session_data.device_info.browser_version}",
                            "location": (
                                f"{session_data.city}, {session_data.country}"
                                if session_data.city
                                else None
                            ),
                            "risk_score": session_data.risk_score,
                            "anomaly_count": len(session_data.anomaly_flags),
                        }
                    )

            return {
                "success": True,
                "sessions": sessions_list,
                "total_sessions": len(sessions_list),
            }

    def _get_session_statistics(self) -> Dict[str, Any]:
        """Get session management statistics.

        Returns:
            Session statistics
        """
        with self._sessions_lock:
            # Calculate additional statistics
            device_count = len(self.device_sessions) if self.track_devices else 0
            user_count = len(self.user_sessions)

            # Session status distribution
            status_distribution = {}
            for session_data in self.sessions.values():
                status = session_data.status.value
                status_distribution[status] = status_distribution.get(status, 0) + 1

            return {
                "success": True,
                "statistics": {
                    **self.session_stats,
                    "current_active_sessions": len(self.sessions),
                    "unique_users": user_count,
                    "unique_devices": device_count,
                    "status_distribution": status_distribution,
                    "max_sessions_per_user": self.max_sessions,
                    "idle_timeout_minutes": self.idle_timeout.total_seconds() / 60,
                    "absolute_timeout_hours": self.absolute_timeout.total_seconds()
                    / 3600,
                },
            }

    def _generate_session_id(self) -> str:
        """Generate secure session ID.

        Returns:
            Session ID
        """
        return secrets.token_urlsafe(32)

    def _process_device_info(
        self, device_info: Dict[str, Any], ip_address: str
    ) -> DeviceInfo:
        """Process and create device information.

        Args:
            device_info: Raw device information
            ip_address: Client IP address

        Returns:
            Processed device information
        """
        # Extract device information with defaults
        device_type = device_info.get("device_type", "unknown")
        os_name = device_info.get("os_name", "unknown")
        os_version = device_info.get("os_version", "unknown")
        browser_name = device_info.get("browser_name", "unknown")
        browser_version = device_info.get("browser_version", "unknown")
        user_agent = device_info.get("user_agent", "unknown")

        # Generate device fingerprint
        fingerprint_data = f"{device_type}:{os_name}:{os_version}:{browser_name}:{browser_version}:{user_agent}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

        # Create device ID (more stable than fingerprint)
        device_id = device_info.get("device_id", fingerprint)

        return DeviceInfo(
            device_id=device_id,
            device_type=device_type,
            os_name=os_name,
            os_version=os_version,
            browser_name=browser_name,
            browser_version=browser_version,
            user_agent=user_agent,
            fingerprint=fingerprint,
        )

    def _calculate_session_risk(
        self, user_id: str, ip_address: str, device: DeviceInfo
    ) -> float:
        """Calculate session risk score.

        Args:
            user_id: User ID
            ip_address: IP address
            device: Device information

        Returns:
            Risk score (0-1)
        """
        risk_score = 0.0

        # Check for new device
        if self.track_devices and device.fingerprint not in self.device_sessions:
            risk_score += 0.3

        # Check for multiple active sessions
        user_session_count = len(self.user_sessions.get(user_id, set()))
        if user_session_count >= self.max_sessions - 1:
            risk_score += 0.2

        # Check for unusual device type
        if device.device_type == "unknown":
            risk_score += 0.2

        # Check for mobile devices (potentially higher risk)
        if device.device_type == "mobile":
            risk_score += 0.1

        # Geo-location checks would go here
        # For now, add base risk for any session
        risk_score += 0.1

        return min(1.0, risk_score)

    def _get_ip_location(self, ip_address: str) -> Dict[str, str]:
        """Get geographic location for IP address.

        Args:
            ip_address: IP address

        Returns:
            Location information
        """
        # In a real implementation, this would use a geo-IP service
        # For now, return mock data
        return {"country": "Unknown", "city": "Unknown"}

    def _detect_session_anomalies(self, session_data: SessionData) -> List[str]:
        """Detect anomalies in session creation.

        Args:
            session_data: Session data to analyze

        Returns:
            List of anomaly indicators
        """
        anomalies = []

        # Check for multiple concurrent sessions
        user_session_count = len(self.user_sessions.get(session_data.user_id, set()))
        if user_session_count >= self.max_sessions:
            anomalies.append("max_concurrent_sessions")

        # Check for new device
        if (
            self.track_devices
            and session_data.device_info.fingerprint not in self.device_sessions
        ):
            anomalies.append("new_device")

        # Check for unusual IP address
        # In a real implementation, this would check against user's IP history
        if session_data.ip_address.startswith(
            "10."
        ) or session_data.ip_address.startswith("192.168."):
            # Internal IP - potentially lower risk
            pass
        else:
            # External IP - check against known IPs
            anomalies.append("external_ip")

        # Check for high risk score
        if session_data.risk_score > 0.7:
            anomalies.append("high_risk_score")

        return anomalies

    def _detect_activity_anomalies(
        self, session_data: SessionData, activity_data: Dict[str, Any]
    ) -> List[str]:
        """Detect anomalies in session activity.

        Args:
            session_data: Session data
            activity_data: New activity data

        Returns:
            List of anomaly indicators
        """
        anomalies = []

        # Check for excessive page views
        new_page_views = activity_data.get("page_views", 0)
        if new_page_views > 100:  # More than 100 page views in one update
            anomalies.append("excessive_page_views")

        # Check for excessive actions
        new_actions = activity_data.get("actions_performed", 0)
        if new_actions > 500:  # More than 500 actions in one update
            anomalies.append("excessive_actions")

        # Check for large data access
        new_data_mb = activity_data.get("data_accessed_mb", 0)
        if new_data_mb > 100:  # More than 100MB in one update
            anomalies.append("large_data_access")

        # Check session duration vs activity
        session_duration = (
            datetime.now(UTC) - session_data.created_at
        ).total_seconds() / 60
        if session_duration < 5 and (new_page_views > 50 or new_actions > 100):
            anomalies.append("rapid_activity")

        return anomalies

    def _get_oldest_user_session(self, user_id: str) -> Optional[str]:
        """Get oldest session for user.

        Args:
            user_id: User ID

        Returns:
            Oldest session ID or None
        """
        if user_id not in self.user_sessions:
            return None

        oldest_session = None
        oldest_time = None

        for session_id in self.user_sessions[user_id]:
            if session_id in self.sessions:
                session_data = self.sessions[session_id]
                if oldest_time is None or session_data.created_at < oldest_time:
                    oldest_time = session_data.created_at
                    oldest_session = session_id

        return oldest_session

    def _audit_session_operation(
        self,
        operation: str,
        session_data: SessionData,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Audit session operation.

        Args:
            operation: Operation performed
            session_data: Session data
            metadata: Additional metadata
        """
        audit_entry = {
            "action": f"session_{operation}",
            "user_id": session_data.user_id,
            "resource_type": "session",
            "resource_id": session_data.session_id,
            "metadata": {
                "operation": operation,
                "ip_address": session_data.ip_address,
                "device_type": session_data.device_info.device_type,
                "risk_score": session_data.risk_score,
                **(metadata or {}),
            },
            "ip_address": session_data.ip_address,
        }

        try:
            self.audit_log_node.execute(**audit_entry)
        except Exception as e:
            self.log_with_context("WARNING", f"Failed to audit session operation: {e}")

    def _log_security_event(
        self, user_id: str, event_type: str, severity: str, metadata: Dict[str, Any]
    ) -> None:
        """Log security event.

        Args:
            user_id: User ID
            event_type: Type of security event
            severity: Event severity
            metadata: Event metadata
        """
        security_event = {
            "event_type": event_type,
            "severity": severity,
            "description": f"Session management: {event_type}",
            "metadata": {"session_management": True, **metadata},
            "user_id": user_id,
            "source_ip": metadata.get("ip_address", "unknown"),
        }

        try:
            self.security_event_node.execute(**security_event)
        except Exception as e:
            self.log_with_context("WARNING", f"Failed to log security event: {e}")

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session management statistics.

        Returns:
            Dictionary with session statistics
        """
        return self._get_session_statistics()["statistics"]

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.execute(**kwargs)
