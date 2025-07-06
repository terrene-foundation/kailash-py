"""
AI-powered threat detection and analysis node.

This module provides enterprise-grade threat detection capabilities using AI/LLM
for advanced threat analysis, real-time event processing, and automated response.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.mixins import LoggingMixin, PerformanceMixin, SecurityMixin
from kailash.nodes.security.audit_log import AuditLogNode
from kailash.nodes.security.security_event import SecurityEvent, SecurityEventNode

logger = logging.getLogger(__name__)


@register_node()
class ThreatDetectionNode(SecurityMixin, PerformanceMixin, LoggingMixin, Node):
    """AI-powered threat detection and analysis.

    This node provides comprehensive threat detection capabilities including:
    - Real-time event analysis with <100ms response time
    - AI-powered threat pattern recognition
    - Automated response actions
    - Threat intelligence correlation
    - Integration with security event logging

    Example:
        >>> threat_detector = ThreatDetectionNode(
        ...     detection_rules=["brute_force", "privilege_escalation"],
        ...     ai_model="ollama:llama3.2:3b",
        ...     response_actions=["alert", "block_ip"],
        ...     real_time=True
        ... )
        >>>
        >>> events = [
        ...     {"type": "login", "user": "admin", "ip": "192.168.1.100", "failed": True},
        ...     {"type": "login", "user": "admin", "ip": "192.168.1.100", "failed": True},
        ...     {"type": "login", "user": "admin", "ip": "192.168.1.100", "failed": True}
        ... ]
        >>>
        >>> threats = threat_detector.execute(events=events)
        >>> print(f"Detected {len(threats['threats'])} threats")
    """

    def __init__(
        self,
        name: str = "threat_detection",
        detection_rules: Optional[List[str]] = None,
        ai_model: str = "ollama:llama3.2:3b",
        response_actions: Optional[List[str]] = None,
        real_time: bool = True,
        severity_threshold: str = "medium",
        response_time_target_ms: int = 100,
        **kwargs,
    ):
        """Initialize threat detection node.

        Args:
            name: Node name
            detection_rules: List of detection rules to apply
            ai_model: AI model for threat analysis
            response_actions: Automated response actions
            real_time: Enable real-time threat detection
            severity_threshold: Minimum severity to trigger response
            response_time_target_ms: Target response time in milliseconds
            **kwargs: Additional node parameters
        """
        # Set attributes before calling super().__init__()
        self.detection_rules = detection_rules or [
            "brute_force",
            "privilege_escalation",
            "data_exfiltration",
            "insider_threat",
            "anomalous_behavior",
        ]
        self.ai_model = ai_model
        self.response_actions = response_actions or ["alert", "log"]
        self.real_time = real_time
        self.severity_threshold = severity_threshold
        self.response_time_target_ms = response_time_target_ms

        # Initialize parent classes
        super().__init__(name=name, **kwargs)

        # Initialize AI agent for threat analysis
        self.ai_agent = LLMAgentNode(
            name=f"{name}_ai_agent",
            provider="ollama",
            model=ai_model.replace("ollama:", ""),
            temperature=0.1,  # Low temperature for consistent analysis
        )

        # Initialize security event and audit logging
        self.security_event_node = SecurityEventNode(name=f"{name}_security_events")
        self.audit_log_node = AuditLogNode(name=f"{name}_audit_log")

        # Threat detection patterns and rules
        self.threat_patterns = {
            "brute_force": {
                "pattern": "multiple_failed_logins",
                "threshold": 5,
                "time_window": 300,  # 5 minutes
                "severity": "high",
            },
            "privilege_escalation": {
                "pattern": "unauthorized_admin_access",
                "keywords": ["sudo", "admin", "root", "privilege"],
                "severity": "critical",
            },
            "data_exfiltration": {
                "pattern": "large_data_transfer",
                "size_threshold_mb": 100,
                "unusual_hours": True,
                "severity": "critical",
            },
            "insider_threat": {
                "pattern": "abnormal_user_behavior",
                "deviation_threshold": 0.8,
                "severity": "high",
            },
            "anomalous_behavior": {
                "pattern": "statistical_anomaly",
                "confidence_threshold": 0.9,
                "severity": "medium",
            },
        }

        # Response action mappings
        self.response_handlers = {
            "alert": self._send_alert,
            "block_ip": self._block_ip,
            "lock_account": self._lock_account,
            "quarantine": self._quarantine_resource,
            "log": self._log_threat,
        }

        # Performance tracking
        self.detection_stats = {
            "total_events_processed": 0,
            "threats_detected": 0,
            "false_positives": 0,
            "avg_detection_time_ms": 0,
            "last_detection": None,
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters for validation and documentation.

        Returns:
            Dictionary mapping parameter names to NodeParameter objects
        """
        return {
            "events": NodeParameter(
                name="events",
                type=list,
                description="List of security events to analyze for threats",
                required=True,
            ),
            "time_window": NodeParameter(
                name="time_window",
                type=int,
                description="Time window in seconds for threat correlation",
                required=False,
                default=3600,
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                description="Additional context for threat analysis",
                required=False,
                default={},
            ),
        }

    def run(
        self,
        events: List[Dict[str, Any]],
        time_window: int = 3600,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Run threat detection analysis.

        Args:
            events: List of security events to analyze
            time_window: Time window in seconds for threat correlation
            context: Additional context for analysis
            **kwargs: Additional parameters

        Returns:
            Dictionary containing detected threats and analysis results
        """
        start_time = datetime.now(UTC)
        context = context or {}

        try:
            # Validate and sanitize inputs
            safe_params = self.validate_and_sanitize_inputs(
                {"events": events, "time_window": time_window, "context": context}
            )

            events = safe_params["events"]
            time_window = safe_params["time_window"]
            context = safe_params["context"]

            self.log_node_execution("threat_detection_start", event_count=len(events))

            # Run threat detection pipeline
            results = self._analyze_threats(events, time_window, context)

            # Update performance stats
            processing_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            self._update_stats(len(events), len(results["threats"]), processing_time)

            # Log successful detection
            self.log_node_execution(
                "threat_detection_complete",
                threats_found=len(results["threats"]),
                processing_time_ms=processing_time,
            )

            return results

        except Exception as e:
            self.log_error_with_traceback(e, "threat_detection")
            raise

    def _analyze_threats(
        self, events: List[Dict[str, Any]], time_window: int, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze events for threats using rule-based and AI detection.

        Args:
            events: Security events to analyze
            time_window: Time window for correlation
            context: Additional context

        Returns:
            Dictionary with detected threats and analysis
        """
        detected_threats = []
        analysis_results = {
            "rule_based_detections": 0,
            "ai_detections": 0,
            "correlation_matches": 0,
            "response_actions_taken": [],
        }

        # Phase 1: Rule-based detection
        rule_threats = self._detect_rule_based_threats(events, time_window)
        detected_threats.extend(rule_threats)
        analysis_results["rule_based_detections"] = len(rule_threats)

        # Phase 2: AI-powered detection for complex patterns
        if len(events) > 0:
            ai_threats = self._detect_ai_threats(events, context)
            detected_threats.extend(ai_threats)
            analysis_results["ai_detections"] = len(ai_threats)

        # Phase 3: Cross-correlation analysis
        correlated_threats = self._correlate_threats(detected_threats, events)
        analysis_results["correlation_matches"] = len(correlated_threats)

        # Phase 4: Response actions for high-severity threats
        for threat in detected_threats:
            if self._should_trigger_response(threat):
                actions_taken = self._execute_response_actions(threat)
                analysis_results["response_actions_taken"].extend(actions_taken)

        return {
            "success": True,
            "threats": detected_threats,
            "analysis": analysis_results,
            "stats": self.detection_stats,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _detect_rule_based_threats(
        self, events: List[Dict[str, Any]], time_window: int
    ) -> List[Dict[str, Any]]:
        """Detect threats using predefined rules.

        Args:
            events: Events to analyze
            time_window: Time window in seconds

        Returns:
            List of detected threats
        """
        threats = []

        for rule_name in self.detection_rules:
            if rule_name not in self.threat_patterns:
                continue

            pattern = self.threat_patterns[rule_name]
            rule_threats = self._apply_detection_rule(
                events, rule_name, pattern, time_window
            )
            threats.extend(rule_threats)

        return threats

    def _apply_detection_rule(
        self,
        events: List[Dict[str, Any]],
        rule_name: str,
        pattern: Dict[str, Any],
        time_window: int,
    ) -> List[Dict[str, Any]]:
        """Apply a specific detection rule to events.

        Args:
            events: Events to analyze
            rule_name: Name of the detection rule
            pattern: Rule pattern configuration
            time_window: Time window in seconds

        Returns:
            List of threats detected by this rule
        """
        threats = []

        if rule_name == "brute_force":
            threats.extend(self._detect_brute_force(events, pattern, time_window))
        elif rule_name == "privilege_escalation":
            threats.extend(self._detect_privilege_escalation(events, pattern))
        elif rule_name == "data_exfiltration":
            threats.extend(self._detect_data_exfiltration(events, pattern))
        elif rule_name == "insider_threat":
            threats.extend(self._detect_insider_threat(events, pattern))
        elif rule_name == "anomalous_behavior":
            threats.extend(self._detect_anomalous_behavior(events, pattern))

        return threats

    def _detect_brute_force(
        self, events: List[Dict[str, Any]], pattern: Dict[str, Any], time_window: int
    ) -> List[Dict[str, Any]]:
        """Detect brute force attacks.

        Args:
            events: Events to analyze
            pattern: Brute force pattern configuration
            time_window: Time window in seconds

        Returns:
            List of brute force threats
        """
        threats = []
        login_failures = {}

        current_time = datetime.now(UTC)
        cutoff_time = current_time - timedelta(seconds=time_window)

        # Group failed login attempts by user/IP
        for event in events:
            if (
                event.get("type") == "login"
                and event.get("failed", False)
                and event.get("timestamp")
            ):

                event_time = datetime.fromisoformat(
                    event["timestamp"].replace("Z", "+00:00")
                )
                if event_time > cutoff_time:
                    key = f"{event.get('user', 'unknown')}:{event.get('ip', 'unknown')}"
                    if key not in login_failures:
                        login_failures[key] = []
                    login_failures[key].append(event)

        # Check for brute force patterns
        threshold = pattern.get("threshold", 5)
        for key, failed_attempts in login_failures.items():
            if len(failed_attempts) >= threshold:
                user, ip = key.split(":", 1)
                threats.append(
                    {
                        "id": f"brute_force_{user}_{ip}_{int(current_time.timestamp())}",
                        "type": "brute_force",
                        "severity": pattern["severity"],
                        "user": user,
                        "source_ip": ip,
                        "failed_attempts": len(failed_attempts),
                        "time_window": time_window,
                        "detection_time": current_time.isoformat(),
                        "confidence": min(1.0, len(failed_attempts) / (threshold * 2)),
                        "evidence": failed_attempts[
                            :5
                        ],  # Include first 5 attempts as evidence
                    }
                )

        return threats

    def _detect_privilege_escalation(
        self, events: List[Dict[str, Any]], pattern: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect privilege escalation attempts.

        Args:
            events: Events to analyze
            pattern: Privilege escalation pattern configuration

        Returns:
            List of privilege escalation threats
        """
        threats = []
        keywords = pattern.get("keywords", ["sudo", "admin", "root", "privilege"])

        for event in events:
            # Check for privilege escalation indicators
            if event.get("type") in ["command", "access", "authentication"]:
                event_text = json.dumps(event).lower()

                matched_keywords = [kw for kw in keywords if kw in event_text]
                if matched_keywords and event.get("unauthorized", False):
                    threats.append(
                        {
                            "id": f"priv_esc_{event.get('user', 'unknown')}_{int(datetime.now(UTC).timestamp())}",
                            "type": "privilege_escalation",
                            "severity": pattern["severity"],
                            "user": event.get("user", "unknown"),
                            "source_ip": event.get("ip", "unknown"),
                            "matched_keywords": matched_keywords,
                            "detection_time": datetime.now(UTC).isoformat(),
                            "confidence": min(
                                1.0, len(matched_keywords) / len(keywords)
                            ),
                            "evidence": event,
                        }
                    )

        return threats

    def _detect_data_exfiltration(
        self, events: List[Dict[str, Any]], pattern: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect data exfiltration attempts.

        Args:
            events: Events to analyze
            pattern: Data exfiltration pattern configuration

        Returns:
            List of data exfiltration threats
        """
        threats = []
        size_threshold = (
            pattern.get("size_threshold_mb", 100) * 1024 * 1024
        )  # Convert to bytes

        for event in events:
            if event.get("type") == "data_transfer":
                size = event.get("size_bytes", 0)
                if size > size_threshold:
                    # Check for unusual hours if configured
                    unusual_time = False
                    if pattern.get("unusual_hours", False):
                        event_time = datetime.fromisoformat(
                            event.get(
                                "timestamp", datetime.now(UTC).isoformat()
                            ).replace("Z", "+00:00")
                        )
                        hour = event_time.hour
                        unusual_time = hour < 6 or hour > 22  # Outside business hours

                    if unusual_time or size > size_threshold * 2:  # Very large transfer
                        threats.append(
                            {
                                "id": f"data_exfil_{event.get('user', 'unknown')}_{int(datetime.now(UTC).timestamp())}",
                                "type": "data_exfiltration",
                                "severity": pattern["severity"],
                                "user": event.get("user", "unknown"),
                                "source_ip": event.get("ip", "unknown"),
                                "transfer_size_mb": size / (1024 * 1024),
                                "unusual_hours": unusual_time,
                                "detection_time": datetime.now(UTC).isoformat(),
                                "confidence": min(1.0, size / (size_threshold * 3)),
                                "evidence": event,
                            }
                        )

        return threats

    def _detect_insider_threat(
        self, events: List[Dict[str, Any]], pattern: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect insider threat indicators.

        Args:
            events: Events to analyze
            pattern: Insider threat pattern configuration

        Returns:
            List of insider threat detections
        """
        threats = []

        # Simple heuristic-based insider threat detection
        user_behaviors = {}

        for event in events:
            user = event.get("user", "unknown")
            if user not in user_behaviors:
                user_behaviors[user] = {
                    "access_patterns": [],
                    "data_access": [],
                    "time_patterns": [],
                    "unusual_activities": 0,
                }

            # Track unusual activities
            if event.get("unusual", False) or event.get("anomalous", False):
                user_behaviors[user]["unusual_activities"] += 1

            # Track access patterns
            if event.get("type") == "access":
                user_behaviors[user]["access_patterns"].append(event.get("resource"))

            # Track data access
            if event.get("type") == "data_access":
                user_behaviors[user]["data_access"].append(event.get("data_type"))

        # Analyze for insider threat indicators
        for user, behavior in user_behaviors.items():
            risk_score = 0
            indicators = []

            # High unusual activity count
            if behavior["unusual_activities"] > 5:
                risk_score += 0.4
                indicators.append("high_unusual_activity")

            # Diverse data access (potential data gathering)
            if len(set(behavior["data_access"])) > 10:
                risk_score += 0.3
                indicators.append("diverse_data_access")

            # Unusual resource access patterns
            if len(set(behavior["access_patterns"])) > 20:
                risk_score += 0.3
                indicators.append("broad_resource_access")

            if risk_score > pattern.get("deviation_threshold", 0.8):
                threats.append(
                    {
                        "id": f"insider_threat_{user}_{int(datetime.now(UTC).timestamp())}",
                        "type": "insider_threat",
                        "severity": pattern["severity"],
                        "user": user,
                        "risk_score": risk_score,
                        "indicators": indicators,
                        "detection_time": datetime.now(UTC).isoformat(),
                        "confidence": min(1.0, risk_score),
                        "evidence": {
                            "unusual_activities": behavior["unusual_activities"],
                            "unique_data_types": len(set(behavior["data_access"])),
                            "unique_resources": len(set(behavior["access_patterns"])),
                        },
                    }
                )

        return threats

    def _detect_anomalous_behavior(
        self, events: List[Dict[str, Any]], pattern: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect statistical anomalies in behavior.

        Args:
            events: Events to analyze
            pattern: Anomalous behavior pattern configuration

        Returns:
            List of anomalous behavior detections
        """
        threats = []

        # Simple statistical anomaly detection
        event_counts = {}
        time_patterns = {}

        for event in events:
            event_type = event.get("type", "unknown")
            user = event.get("user", "unknown")

            # Count events by type
            if event_type not in event_counts:
                event_counts[event_type] = 0
            event_counts[event_type] += 1

            # Track time patterns
            if event.get("timestamp"):
                try:
                    event_time = datetime.fromisoformat(
                        event["timestamp"].replace("Z", "+00:00")
                    )
                    hour = event_time.hour
                    time_key = f"{user}:{hour}"
                    if time_key not in time_patterns:
                        time_patterns[time_key] = 0
                    time_patterns[time_key] += 1
                except:
                    pass

        # Detect anomalies
        confidence_threshold = pattern.get("confidence_threshold", 0.9)

        # Check for unusual event frequency
        if event_counts:
            avg_count = sum(event_counts.values()) / len(event_counts)
            for event_type, count in event_counts.items():
                if count > avg_count * 3:  # 3x above average
                    confidence = min(1.0, count / (avg_count * 5))
                    if confidence >= confidence_threshold:
                        threats.append(
                            {
                                "id": f"anomaly_{event_type}_{int(datetime.now(UTC).timestamp())}",
                                "type": "anomalous_behavior",
                                "subtype": "unusual_frequency",
                                "severity": pattern["severity"],
                                "event_type": event_type,
                                "frequency": count,
                                "average_frequency": avg_count,
                                "detection_time": datetime.now(UTC).isoformat(),
                                "confidence": confidence,
                                "evidence": {"event_counts": event_counts},
                            }
                        )

        return threats

    def _detect_ai_threats(
        self, events: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Use AI to detect complex threat patterns.

        Args:
            events: Events to analyze
            context: Additional context for analysis

        Returns:
            List of AI-detected threats
        """
        threats = []

        try:
            # Prepare events for AI analysis
            event_summary = self._prepare_events_for_ai(events)

            # Create AI analysis prompt
            prompt = self._create_ai_analysis_prompt(event_summary, context)

            # Run AI analysis
            ai_response = self.ai_agent.execute(
                provider="ollama",
                model=self.ai_model.replace("ollama:", ""),
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse AI response for threats
            ai_threats = self._parse_ai_response(ai_response)
            threats.extend(ai_threats)

        except Exception as e:
            self.log_with_context("WARNING", f"AI threat detection failed: {e}")

        return threats

    def _prepare_events_for_ai(self, events: List[Dict[str, Any]]) -> str:
        """Prepare events for AI analysis.

        Args:
            events: Raw events

        Returns:
            Formatted event summary for AI analysis
        """
        # Limit events for AI analysis (performance)
        sample_events = events[:50] if len(events) > 50 else events

        # Create summary
        summary = {
            "total_events": len(events),
            "event_types": list(set(event.get("type", "unknown") for event in events)),
            "unique_users": list(set(event.get("user", "unknown") for event in events)),
            "unique_ips": list(set(event.get("ip", "unknown") for event in events)),
            "time_range": {
                "start": min(
                    event.get("timestamp", "")
                    for event in events
                    if event.get("timestamp")
                ),
                "end": max(
                    event.get("timestamp", "")
                    for event in events
                    if event.get("timestamp")
                ),
            },
            "sample_events": sample_events,
        }

        return json.dumps(summary, indent=2)

    def _create_ai_analysis_prompt(
        self, event_summary: str, context: Dict[str, Any]
    ) -> str:
        """Create prompt for AI threat analysis.

        Args:
            event_summary: Formatted event summary
            context: Additional context

        Returns:
            AI analysis prompt
        """
        prompt = f"""
You are a cybersecurity expert analyzing security events for potential threats.

CONTEXT:
{json.dumps(context, indent=2) if context else "No additional context provided"}

EVENTS TO ANALYZE:
{event_summary}

TASK:
Analyze these events for security threats that may not be caught by simple rules.
Look for:
1. Complex attack patterns
2. Coordinated activities
3. Subtle indicators of compromise
4. Advanced persistent threats
5. Social engineering attempts

RESPONSE FORMAT:
Return a JSON array of threat objects with this structure:
[
  {{
    "id": "unique_threat_id",
    "type": "threat_type",
    "severity": "low|medium|high|critical",
    "description": "detailed threat description",
    "confidence": 0.0-1.0,
    "indicators": ["indicator1", "indicator2"],
    "evidence": {{"key": "value"}},
    "recommended_actions": ["action1", "action2"]
  }}
]

If no threats are detected, return an empty array: []
"""
        return prompt

    def _parse_ai_response(self, ai_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse AI response for detected threats.

        Args:
            ai_response: Response from AI agent

        Returns:
            List of parsed threats
        """
        threats = []

        try:
            # Extract content from AI response
            content = ai_response.get("result", {}).get("content", "")
            if not content:
                return threats

            # Try to parse JSON response
            import re

            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                threats_data = json.loads(json_match.group())

                for threat_data in threats_data:
                    # Add AI detection metadata
                    threat_data["detection_method"] = "ai_analysis"
                    threat_data["detection_time"] = datetime.now(UTC).isoformat()

                    # Ensure required fields
                    if not threat_data.get("id"):
                        threat_data["id"] = (
                            f"ai_threat_{int(datetime.now(UTC).timestamp())}"
                        )

                    threats.append(threat_data)

        except Exception as e:
            self.log_with_context("WARNING", f"Failed to parse AI response: {e}")

        return threats

    def _correlate_threats(
        self, threats: List[Dict[str, Any]], events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Correlate threats across different detection methods.

        Args:
            threats: Detected threats
            events: Original events

        Returns:
            List of correlated threat patterns
        """
        correlated = []

        # Group threats by user/IP for correlation
        threat_groups = {}

        for threat in threats:
            key_parts = []
            if threat.get("user"):
                key_parts.append(f"user:{threat['user']}")
            if threat.get("source_ip"):
                key_parts.append(f"ip:{threat['source_ip']}")

            if key_parts:
                key = "|".join(key_parts)
                if key not in threat_groups:
                    threat_groups[key] = []
                threat_groups[key].append(threat)

        # Look for correlated patterns
        for key, group_threats in threat_groups.items():
            if len(group_threats) > 1:
                # Multiple threats from same user/IP - potential coordinated attack
                correlated.append(
                    {
                        "id": f"correlated_{key.replace(':', '_').replace('|', '_')}_{int(datetime.now(UTC).timestamp())}",
                        "type": "correlated_attack",
                        "severity": "high",
                        "description": f"Multiple threat types detected from {key}",
                        "related_threats": [t["id"] for t in group_threats],
                        "threat_types": list(set(t["type"] for t in group_threats)),
                        "correlation_score": min(1.0, len(group_threats) / 3),
                        "detection_time": datetime.now(UTC).isoformat(),
                    }
                )

        return correlated

    def _should_trigger_response(self, threat: Dict[str, Any]) -> bool:
        """Determine if threat should trigger automated response.

        Args:
            threat: Threat to evaluate

        Returns:
            True if response should be triggered
        """
        severity = threat.get("severity", "low")
        confidence = threat.get("confidence", 0.0)

        # Response thresholds
        thresholds = {"critical": 0.7, "high": 0.8, "medium": 0.9, "low": 0.95}

        required_confidence = thresholds.get(severity, 0.95)

        # Check if severity meets minimum threshold
        severity_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        min_severity = severity_levels.get(self.severity_threshold, 2)
        threat_severity = severity_levels.get(severity, 1)

        return threat_severity >= min_severity and confidence >= required_confidence

    def _execute_response_actions(self, threat: Dict[str, Any]) -> List[str]:
        """Execute automated response actions for a threat.

        Args:
            threat: Threat that triggered response

        Returns:
            List of actions taken
        """
        actions_taken = []

        for action in self.response_actions:
            try:
                if action in self.response_handlers:
                    self.response_handlers[action](threat)
                    actions_taken.append(action)
                    self.log_with_context(
                        "INFO",
                        f"Executed response action: {action}",
                        threat_id=threat["id"],
                    )
                else:
                    self.log_with_context(
                        "WARNING", f"Unknown response action: {action}"
                    )
            except Exception as e:
                self.log_with_context(
                    "ERROR", f"Failed to execute response action {action}: {e}"
                )

        return actions_taken

    def _send_alert(self, threat: Dict[str, Any]) -> None:
        """Send threat alert.

        Args:
            threat: Threat information
        """
        # Create security event for the alert
        alert_event = {
            "event_type": "threat_alert",
            "severity": threat.get("severity", "medium"),
            "description": f"Threat detected: {threat.get('type', 'unknown')}",
            "metadata": threat,
            "user_id": threat.get("user", "system"),
            "source_ip": threat.get("source_ip", "unknown"),
        }

        self.security_event_node.execute(**alert_event)

    def _block_ip(self, threat: Dict[str, Any]) -> None:
        """Block IP address associated with threat.

        Args:
            threat: Threat information
        """
        ip = threat.get("source_ip")
        if ip and ip != "unknown":
            # Log the IP blocking action
            self.log_with_context(
                "INFO", f"Would block IP: {ip} (threat: {threat['id']})"
            )

            # In a real implementation, this would interface with firewall/network controls
            # For now, just log the action
            block_event = {
                "event_type": "ip_blocked",
                "severity": "high",
                "description": f"IP {ip} blocked due to threat {threat['id']}",
                "metadata": {"blocked_ip": ip, "threat_id": threat["id"]},
                "user_id": "system",
                "source_ip": ip,
            }

            self.security_event_node.execute(**block_event)

    def _lock_account(self, threat: Dict[str, Any]) -> None:
        """Lock user account associated with threat.

        Args:
            threat: Threat information
        """
        user = threat.get("user")
        if user and user != "unknown":
            # Log the account locking action
            self.log_with_context(
                "INFO", f"Would lock account: {user} (threat: {threat['id']})"
            )

            # In a real implementation, this would interface with user management system
            lock_event = {
                "event_type": "account_locked",
                "severity": "high",
                "description": f"Account {user} locked due to threat {threat['id']}",
                "metadata": {"locked_user": user, "threat_id": threat["id"]},
                "user_id": user,
                "source_ip": threat.get("source_ip", "unknown"),
            }

            self.security_event_node.execute(**lock_event)

    def _quarantine_resource(self, threat: Dict[str, Any]) -> None:
        """Quarantine resource associated with threat.

        Args:
            threat: Threat information
        """
        # Log the quarantine action
        self.log_with_context(
            "INFO", f"Would quarantine resource for threat: {threat['id']}"
        )

        quarantine_event = {
            "event_type": "resource_quarantined",
            "severity": "medium",
            "description": f"Resource quarantined due to threat {threat['id']}",
            "metadata": {"threat_id": threat["id"]},
            "user_id": threat.get("user", "system"),
            "source_ip": threat.get("source_ip", "unknown"),
        }

        self.security_event_node.execute(**quarantine_event)

    def _log_threat(self, threat: Dict[str, Any]) -> None:
        """Log threat to audit trail.

        Args:
            threat: Threat information
        """
        # Create audit log entry
        log_entry = {
            "action": "threat_detected",
            "user_id": threat.get("user", "system"),
            "resource_type": "security_event",
            "resource_id": threat["id"],
            "metadata": threat,
            "ip_address": threat.get("source_ip", "unknown"),
        }

        self.audit_log_node.execute(**log_entry)

    def _update_stats(
        self, events_processed: int, threats_detected: int, processing_time_ms: float
    ) -> None:
        """Update detection statistics.

        Args:
            events_processed: Number of events processed
            threats_detected: Number of threats detected
            processing_time_ms: Processing time in milliseconds
        """
        self.detection_stats["total_events_processed"] += events_processed
        self.detection_stats["threats_detected"] += threats_detected
        self.detection_stats["last_detection"] = datetime.now(UTC).isoformat()

        # Update average detection time
        if self.detection_stats["avg_detection_time_ms"] == 0:
            self.detection_stats["avg_detection_time_ms"] = processing_time_ms
        else:
            # Simple moving average
            self.detection_stats["avg_detection_time_ms"] = (
                self.detection_stats["avg_detection_time_ms"] * 0.9
                + processing_time_ms * 0.1
            )

    def analyze_patterns(
        self, time_window: timedelta = timedelta(hours=24)
    ) -> Dict[str, Any]:
        """Analyze historical patterns for threat intelligence.

        Args:
            time_window: Time window for pattern analysis

        Returns:
            Dictionary with pattern analysis results
        """
        return {
            "analysis_type": "historical_patterns",
            "time_window": str(time_window),
            "pattern_summary": "Historical pattern analysis would be implemented here",
            "stats": self.detection_stats,
            "recommendations": [
                "Implement pattern baseline learning",
                "Add threat feed integration",
                "Enable machine learning models",
            ],
        }

    def auto_respond(self, threat: SecurityEvent) -> List[str]:
        """Execute automated response actions for a threat.

        Args:
            threat: Security event representing the threat

        Returns:
            List of response actions taken
        """
        threat_dict = {
            "id": getattr(threat, "correlation_id", None)
            or f"event_{int(datetime.now(UTC).timestamp())}",
            "type": threat.event_type,
            "severity": threat.severity,
            "user": threat.user_id,
            "source_ip": threat.ip_address,
        }

        return self._execute_response_actions(threat_dict)

    def get_detection_stats(self) -> Dict[str, Any]:
        """Get current detection statistics.

        Returns:
            Dictionary with detection statistics
        """
        return {
            **self.detection_stats,
            "rules_enabled": self.detection_rules,
            "response_actions": self.response_actions,
            "ai_model": self.ai_model,
            "real_time_enabled": self.real_time,
            "performance_target_ms": self.response_time_target_ms,
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.execute(**kwargs)
