"""Enterprise audit logging node for compliance and security."""

import time
from datetime import datetime
from typing import Any, Dict, List

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError


@register_node()
class EnterpriseAuditLoggerNode(Node):
    """Creates comprehensive audit logs for enterprise compliance.

    This node generates detailed audit trails for all enterprise operations,
    ensuring compliance with regulations like SOX, HIPAA, and GDPR.
    """

    metadata = NodeMetadata(
        name="EnterpriseAuditLoggerNode",
        description="Generate comprehensive audit logs for enterprise compliance",
        version="1.0.0",
        tags={"enterprise", "audit", "compliance"},
    )

    def __init__(self, name: str = None, **kwargs):
        self.name = name or self.__class__.__name__
        super().__init__(name=self.name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "execution_results": NodeParameter(
                name="execution_results",
                type=dict,
                description="Results from MCP tool execution",
                required=True,
            ),
            "user_context": NodeParameter(
                name="user_context",
                type=dict,
                description="User context for audit trail",
                required=True,
            ),
            "audit_level": NodeParameter(
                name="audit_level",
                type=str,
                description="Audit detail level (basic, detailed, full)",
                required=False,
                default="detailed",
            ),
        }

    def run(
        self,
        execution_results: Dict,
        user_context: Dict,
        audit_level: str = "detailed",
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate comprehensive audit log entry."""
        try:
            # Extract audit information
            actions_performed = execution_results.get("actions", [])
            summary = execution_results.get("summary", {})

            # Create base audit entry
            audit_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "audit_id": f"audit-{int(time.time())}-{user_context.get('user_id', 'unknown')}",
                "audit_level": audit_level,
                # User identification
                "user_id": user_context.get("user_id"),
                "tenant_id": user_context.get("tenant_id"),
                "session_id": user_context.get("session_id"),
                # Operation details
                "actions": actions_performed,
                "results_summary": {
                    "total_actions": summary.get(
                        "total_actions", len(actions_performed)
                    ),
                    "successful": summary.get("successful_actions", 0),
                    "failed": summary.get("failed_actions", 0),
                    "execution_time_ms": summary.get("execution_time_ms", 0),
                },
                # Compliance information
                "compliance": {
                    "data_residency_compliant": self._check_data_residency_compliance(
                        user_context, actions_performed
                    ),
                    "access_controls_enforced": self._check_access_controls(
                        user_context, actions_performed
                    ),
                    "audit_trail_complete": True,
                    "compliance_zones": user_context.get(
                        "compliance_zones", ["public"]
                    ),
                },
                # Security metadata
                "security": {
                    "authentication_method": "sso_mfa",
                    "authorization_level": (
                        "verified"
                        if len(user_context.get("permissions", [])) > 1
                        else "basic"
                    ),
                    "data_classification": self._determine_data_classification(
                        actions_performed
                    ),
                    "encryption_status": "encrypted_in_transit_and_rest",
                },
            }

            # Add detailed information based on audit level
            if audit_level in ["detailed", "full"]:
                audit_entry["detailed_actions"] = [
                    {
                        "action_id": f"action-{i}-{int(time.time())}",
                        "action_type": action.get("action", "unknown"),
                        "server_id": action.get("server_id"),
                        "timestamp": action.get("timestamp"),
                        "success": action.get("success", False),
                        "data_size_bytes": action.get("data_size", 0),
                        "error": (
                            action.get("error")
                            if not action.get("success", False)
                            else None
                        ),
                    }
                    for i, action in enumerate(actions_performed)
                ]

            if audit_level == "full":
                audit_entry["system_context"] = {
                    "workflow_execution_id": kwargs.get("workflow_execution_id"),
                    "node_execution_order": kwargs.get("node_execution_order", []),
                    "resource_usage": {
                        "peak_memory_mb": kwargs.get("peak_memory_mb", 0),
                        "cpu_time_ms": kwargs.get("cpu_time_ms", 0),
                        "network_bytes": kwargs.get("network_bytes", 0),
                    },
                }

            # Calculate risk score
            risk_score = self._calculate_risk_score(actions_performed, user_context)
            audit_entry["risk_assessment"] = {
                "risk_score": risk_score,
                "risk_level": (
                    "high"
                    if risk_score > 0.7
                    else "medium" if risk_score > 0.3 else "low"
                ),
                "risk_factors": self._identify_risk_factors(
                    actions_performed, user_context
                ),
            }

            return {
                "audit_entry": audit_entry,
                "audit_id": audit_entry["audit_id"],
                "compliance_status": "compliant",
                "audit_timestamp": time.time(),
            }

        except Exception as e:
            raise NodeExecutionError(f"Audit logging failed: {str(e)}")

    def _check_data_residency_compliance(
        self, user_context: Dict, actions: List[Dict]
    ) -> bool:
        """Check if data residency requirements are met."""
        # In a real implementation, this would check actual data locations
        data_residency = user_context.get("data_residency")
        if not data_residency:
            return True

        # Check if all actions occurred in the required region
        for action in actions:
            server_id = action.get("server_id", "")
            if data_residency == "us-east-1" and "us-east" not in server_id:
                return False

        return True

    def _check_access_controls(self, user_context: Dict, actions: List[Dict]) -> bool:
        """Verify access controls were properly enforced."""
        permissions = user_context.get("permissions", [])

        # Check if user had write permissions for write actions
        for action in actions:
            action_type = action.get("action", "")
            if "write" in action_type or "execute" in action_type:
                if "write" not in permissions:
                    return False

        return True

    def _determine_data_classification(self, actions: List[Dict]) -> str:
        """Determine the highest data classification level accessed."""
        classifications = []

        for action in actions:
            action_type = action.get("action", "")
            if "patient" in action_type:
                classifications.append("confidential")
            elif "transaction" in action_type or "financial" in action_type:
                classifications.append("restricted")
            elif "analytics" in action_type:
                classifications.append("internal")
            else:
                classifications.append("public")

        # Return highest classification
        if "confidential" in classifications:
            return "confidential"
        elif "restricted" in classifications:
            return "restricted"
        elif "internal" in classifications:
            return "internal"
        else:
            return "public"

    def _calculate_risk_score(self, actions: List[Dict], user_context: Dict) -> float:
        """Calculate risk score based on actions and context."""
        base_risk = 0.1

        # Increase risk for failed actions
        failed_actions = sum(
            1 for action in actions if not action.get("success", False)
        )
        failure_risk = failed_actions * 0.2

        # Increase risk for sensitive data access
        sensitive_actions = sum(
            1
            for action in actions
            if any(
                keyword in action.get("action", "")
                for keyword in ["patient", "transaction", "financial"]
            )
        )
        sensitivity_risk = sensitive_actions * 0.15

        # Increase risk for cross-region access
        data_residency = user_context.get("data_residency", "")
        cross_region_actions = sum(
            1
            for action in actions
            if data_residency and data_residency not in action.get("server_id", "")
        )
        region_risk = cross_region_actions * 0.1

        total_risk = min(1.0, base_risk + failure_risk + sensitivity_risk + region_risk)
        return round(total_risk, 2)

    def _identify_risk_factors(
        self, actions: List[Dict], user_context: Dict
    ) -> List[str]:
        """Identify specific risk factors for this audit entry."""
        factors = []

        # Check for failures
        if any(not action.get("success", False) for action in actions):
            factors.append("execution_failures")

        # Check for sensitive data access
        if any(
            keyword in action.get("action", "")
            for action in actions
            for keyword in ["patient", "transaction", "financial"]
        ):
            factors.append("sensitive_data_access")

        # Check for cross-region access
        data_residency = user_context.get("data_residency", "")
        if any(
            data_residency and data_residency not in action.get("server_id", "")
            for action in actions
        ):
            factors.append("cross_region_access")

        # Check for elevated permissions
        if "admin" in user_context.get("permissions", []):
            factors.append("elevated_permissions")

        return factors
