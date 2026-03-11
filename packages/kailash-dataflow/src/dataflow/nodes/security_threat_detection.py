"""DataFlow Security Threat Detection Node - SDK Compliant Implementation."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.security.threat_detection import (
    ThreatDetectionNode as SDKThreatDetectionNode,
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class DataFlowThreatDetectionNode(AsyncNode):
    """Node for threat detection in DataFlow operations.

    This node extends AsyncNode and leverages the SDK's ThreatDetectionNode
    to provide enterprise-grade threat detection following SDK patterns.

    Configuration Parameters (set during initialization):
        detection_mode: Detection mode (realtime, batch, hybrid)
        threat_threshold: Threshold for threat scoring (0-100)
        enable_ml_detection: Enable machine learning detection
        enable_pattern_matching: Enable pattern-based detection
        enable_anomaly_detection: Enable anomaly detection
        window_size_minutes: Time window for analysis

    Runtime Parameters (provided during execution):
        operation: Operation being analyzed
        user_id: User performing the operation
        source_ip: Source IP address
        data: Data being processed
        context: Additional context for threat analysis
        patterns: Custom patterns to check
    """

    def __init__(self, **kwargs):
        """Initialize the DataFlowThreatDetectionNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.detection_mode = kwargs.pop("detection_mode", "realtime")
        self.threat_threshold = kwargs.pop("threat_threshold", 70)
        self.enable_ml_detection = kwargs.pop("enable_ml_detection", True)
        self.enable_pattern_matching = kwargs.pop("enable_pattern_matching", True)
        self.enable_anomaly_detection = kwargs.pop("enable_anomaly_detection", True)
        self.enable_rate_limiting = kwargs.pop("enable_rate_limiting", False)
        self.rate_limit_threshold = kwargs.pop("rate_limit_threshold", 100)
        self.enable_sql_injection_detection = kwargs.pop(
            "enable_sql_injection_detection", True
        )
        self.window_size_minutes = kwargs.pop("window_size_minutes", 60)

        # Call parent constructor
        super().__init__(**kwargs)

        # Initialize the SDK ThreatDetectionNode
        self.threat_detector = SDKThreatDetectionNode(
            name=f"{getattr(self, 'node_id', 'unknown')}_sdk_threat",
            detection_rules=getattr(
                self, "detection_rules", ["sql_injection", "unauthorized_access"]
            ),
            real_time=getattr(self, "detection_mode", "realtime") == "realtime",
            severity_threshold=getattr(self, "threat_threshold", 70),
        )

        # Initialize threat patterns for DataFlow operations
        self.threat_patterns = self._initialize_threat_patterns()

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation being analyzed (e.g., 'bulk_delete', 'data_export')",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=True,
                description="User performing the operation",
            ),
            "source_ip": NodeParameter(
                name="source_ip",
                type=str,
                required=False,
                description="Source IP address of the request",
            ),
            "data": NodeParameter(
                name="data",
                type=dict,
                required=False,
                default={},
                description="Data being processed in the operation",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context for threat analysis",
            ),
            "patterns": NodeParameter(
                name="patterns",
                type=list,
                required=False,
                default=[],
                description="Custom threat patterns to check",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute threat detection asynchronously."""
        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            operation = validated_inputs.get("operation")
            user_id = validated_inputs.get("user_id")
            source_ip = validated_inputs.get("source_ip")
            data = validated_inputs.get("data", {})
            context = validated_inputs.get("context", {})
            custom_patterns = validated_inputs.get("patterns", [])

            # Perform threat detection
            threat_score = 0
            threats_detected = []
            risk_level = "low"

            # Pattern matching
            if self.enable_pattern_matching:
                pattern_threats = await self._check_patterns(
                    operation, data, context, custom_patterns
                )
                threats_detected.extend(pattern_threats)
                threat_score += len(pattern_threats) * 20

            # Anomaly detection
            if self.enable_anomaly_detection:
                anomaly_score = await self._detect_anomalies(
                    operation, user_id, data, context
                )
                if anomaly_score > 50:
                    threats_detected.append(
                        {
                            "type": "anomaly",
                            "description": f"Anomalous behavior detected (score: {anomaly_score})",
                            "severity": "medium" if anomaly_score < 75 else "high",
                        }
                    )
                threat_score += anomaly_score * 0.5

            # Rate limiting detection
            if self.enable_rate_limiting:
                rate_limit_threats = await self._check_rate_limits(
                    operation, user_id, context
                )
                threats_detected.extend(rate_limit_threats)
                threat_score += len(rate_limit_threats) * 30

            # ML-based detection
            if self.enable_ml_detection:
                ml_result = await self._ml_threat_detection(
                    operation, user_id, source_ip, data
                )
                if ml_result["threat_detected"]:
                    # Add ML threats directly if provided, otherwise create a summary threat
                    ml_threats = ml_result.get("threats", [])
                    if ml_threats:
                        threats_detected.extend(ml_threats)
                    else:
                        threats_detected.append(
                            {
                                "type": "ml_detection",
                                "description": ml_result["description"],
                                "severity": ml_result["severity"],
                            }
                        )
                threat_score += ml_result["score"]

            # Normalize threat score
            threat_score = min(100, threat_score)

            # Determine risk level based on both threat score AND highest severity threat
            highest_severity = "low"
            for threat in threats_detected:
                threat_severity = threat.get("severity", "low")
                if threat_severity == "critical":
                    highest_severity = "critical"
                    break
                elif threat_severity == "high" and highest_severity != "critical":
                    highest_severity = "high"
                elif threat_severity == "medium" and highest_severity not in [
                    "critical",
                    "high",
                ]:
                    highest_severity = "medium"

            # Risk level is the higher of threat score based or severity based
            score_based_risk = "low"
            if threat_score >= self.threat_threshold:
                score_based_risk = "critical"
            elif threat_score >= 50:
                score_based_risk = "high"
            elif threat_score >= 30:
                score_based_risk = "medium"

            # Use the higher risk level
            severity_priority = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            if (
                severity_priority[highest_severity]
                > severity_priority[score_based_risk]
            ):
                risk_level = highest_severity
            else:
                risk_level = score_based_risk

            # Build result following SDK patterns
            result = {
                "success": True,
                "threat_detected": len(threats_detected) > 0,
                "threat_score": threat_score,
                "risk_level": risk_level,
                "threats": threats_detected,
                "operation": operation,
                "user_id": user_id,
                "metadata": {
                    "detection_mode": self.detection_mode,
                    "threshold": self.threat_threshold,
                    "patterns_checked": len(self.threat_patterns)
                    + len(custom_patterns),
                    "ml_enabled": self.enable_ml_detection,
                    "anomaly_enabled": self.enable_anomaly_detection,
                },
            }

            # Add recommendations
            if threat_score >= self.threat_threshold:
                result["recommendations"] = self._get_recommendations(
                    threats_detected, risk_level
                )
                result["action_required"] = True

            # Add audit trail
            result["audit_trail"] = {
                "timestamp": datetime.utcnow().isoformat(),
                "detection_methods": self._get_active_methods(),
                "analysis_window": f"{self.window_size_minutes} minutes",
            }

            return result

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except Exception as e:
            return {"success": False, "error": str(e), "threat_detected": False}

    def _initialize_threat_patterns(self) -> List[Dict[str, Any]]:
        """Initialize threat patterns for DataFlow operations."""
        return [
            {
                "pattern": "bulk_delete_all",
                "operation": "bulk_delete",
                "condition": lambda data: data.get("filter") == {}
                or data.get("delete_all"),
                "severity": "critical",
                "description": "Attempting to delete all records",
            },
            {
                "pattern": "mass_data_export",
                "operation": "data_export",
                "condition": lambda data: data.get("record_count", 0) > 10000,
                "severity": "high",
                "description": "Large data export detected",
            },
            {
                "pattern": "rapid_operations",
                "operation": "*",
                "condition": lambda data: data.get("rate_per_minute", 0) > 100,
                "severity": "medium",
                "description": "Unusually high operation rate",
            },
            {
                "pattern": "sql_injection_attempt",
                "operation": "*",
                "condition": lambda data: self._check_sql_injection(data),
                "severity": "critical",
                "description": "Potential SQL injection attempt",
            },
            {
                "pattern": "privilege_escalation",
                "operation": "*",
                "condition": lambda data: data.get("requested_permissions", [])
                != data.get("user_permissions", []),
                "severity": "high",
                "description": "Attempted privilege escalation",
            },
        ]

    async def _check_patterns(
        self,
        operation: str,
        data: Dict[str, Any],
        context: Dict[str, Any],
        custom_patterns: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Check for threat patterns."""
        threats = []

        # Check built-in patterns
        all_patterns = self.threat_patterns + custom_patterns

        for pattern in all_patterns:
            if pattern["operation"] == "*" or pattern["operation"] == operation:
                try:
                    if pattern["condition"](data):
                        # Use pattern name as type for sql_injection compatibility
                        threat_type = pattern["pattern"]
                        if "sql_injection" in threat_type:
                            threat_type = "sql_injection_attempt"

                        threats.append(
                            {
                                "type": threat_type,
                                "pattern": pattern["pattern"],
                                "description": pattern["description"],
                                "severity": pattern["severity"],
                            }
                        )
                except Exception:
                    # Pattern check failed, skip
                    continue

        return threats

    async def _detect_anomalies(
        self,
        operation: str,
        user_id: str,
        data: Dict[str, Any],
        context: Dict[str, Any],
    ) -> float:
        """Detect anomalous behavior."""
        anomaly_score = 0.0

        # Check operation frequency
        operation_count = context.get("user_operation_count", {}).get(operation, 0)
        if operation_count > 50:  # High frequency
            anomaly_score += 30

        # Check operation timing
        current_hour = datetime.utcnow().hour
        if current_hour < 6 or current_hour > 22:  # Outside business hours
            anomaly_score += 20

        # Check data volume
        data_size = data.get("record_count", 0)
        avg_size = context.get("avg_operation_size", 100)
        if data_size > avg_size * 10:  # 10x normal size
            anomaly_score += 40

        # Check location anomaly
        if context.get("location_anomaly", False):
            anomaly_score += 30

        return min(100, anomaly_score)

    async def _check_rate_limits(
        self,
        operation: str,
        user_id: str,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Check for rate limiting violations."""
        threats = []

        # Check request rate from context
        request_rate = context.get("request_rate", 0)
        if request_rate > self.rate_limit_threshold:
            threats.append(
                {
                    "type": "rate_limit_exceeded",
                    "description": f"Rate limit exceeded: {request_rate} requests/min > {self.rate_limit_threshold}",
                    "severity": "high",
                    "rate": request_rate,
                    "threshold": self.rate_limit_threshold,
                }
            )

        return threats

    async def _ml_threat_detection(
        self,
        operation: str,
        user_id: str,
        source_ip: Optional[str],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Use ML-based threat detection."""
        try:
            # Use SDK ThreatDetectionNode for ML detection
            ml_result = self.threat_detector.execute(
                operation=operation, user_id=user_id, source_ip=source_ip, data=data
            )

            # Handle both SDK format and test mock format
            threat_detected = ml_result.get(
                "threat_detected", ml_result.get("threats_detected", False)
            )
            threats = ml_result.get("threats", [])

            # If threats are provided, use their severity for overall result
            if threats:
                highest_severity = max(
                    (threat.get("severity", "low") for threat in threats),
                    key=lambda s: {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(
                        s, 0
                    ),
                )
                description = f"ML threats detected: {len(threats)} threats"
                score = len(threats) * 25  # Base score for ML detected threats
            else:
                highest_severity = ml_result.get("severity", "medium")
                description = ml_result.get("description", "ML-based threat detected")
                score = ml_result.get("threat_score", 0)

            return {
                "threat_detected": threat_detected,
                "score": score,
                "description": description,
                "severity": highest_severity,
                "threats": threats,  # Pass through for threat aggregation
            }

        except Exception:
            # ML detection failed, return safe default
            return {
                "threat_detected": False,
                "score": 0,
                "description": "",
                "severity": "low",
            }

    def _check_sql_injection(self, data: Dict[str, Any]) -> bool:
        """Check for SQL injection patterns."""
        sql_patterns = [
            "' OR '1'='1",
            "'; DROP TABLE",
            "UNION SELECT",
            "/**/",
            "--",
            "xp_cmdshell",
            "EXEC sp_",
            "'; EXEC",
        ]

        # Check all string values in data
        for value in self._extract_strings(data):
            for pattern in sql_patterns:
                if pattern.lower() in value.lower():
                    return True

        return False

    def _extract_strings(self, obj: Any) -> List[str]:
        """Recursively extract all string values from an object."""
        strings = []

        if isinstance(obj, str):
            strings.append(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                strings.extend(self._extract_strings(value))
        elif isinstance(obj, list):
            for item in obj:
                strings.extend(self._extract_strings(item))

        return strings

    def _get_recommendations(
        self, threats: List[Dict[str, Any]], risk_level: str
    ) -> List[str]:
        """Get security recommendations based on detected threats."""
        recommendations = []

        if risk_level == "critical":
            recommendations.append("Block this operation immediately")
            recommendations.append("Notify security team")
            recommendations.append("Review user permissions and access")
        elif risk_level == "high":
            recommendations.append("Require additional authentication")
            recommendations.append("Log detailed audit trail")
            recommendations.append("Monitor user activity closely")

        # Specific recommendations based on threat types
        for threat in threats:
            if threat["type"] == "sql_injection_attempt":
                recommendations.append("Sanitize all input parameters")
                recommendations.append("Use parameterized queries")
            elif threat["type"] == "mass_data_export":
                recommendations.append("Implement data export limits")
                recommendations.append("Require approval for large exports")

        return list(set(recommendations))  # Remove duplicates

    def _get_active_methods(self) -> List[str]:
        """Get list of active detection methods."""
        methods = []

        if self.enable_pattern_matching:
            methods.append("pattern_matching")
        if self.enable_anomaly_detection:
            methods.append("anomaly_detection")
        if self.enable_ml_detection:
            methods.append("ml_detection")

        return methods
