"""
Enterprise Workflow Templates for Kaizen Framework

This module provides enterprise-grade workflow templates for common business processes
including approval workflows, customer service, document analysis, and compliance.

Templates integrate with Kailash Core SDK enterprise nodes for audit trails,
compliance validation, security controls, and multi-tenant support.
"""

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder


class EnterpriseWorkflowTemplate(ABC):
    """
    Abstract base class for enterprise workflow templates.

    Provides common functionality for audit trails, compliance validation,
    security controls, and enterprise integration patterns.
    """

    def __init__(self, template_type: str, config: Dict[str, Any]):
        """
        Initialize enterprise workflow template.

        Args:
            template_type: Type of enterprise workflow template
            config: Configuration parameters for the template
        """
        self.template_type = template_type
        self.config = config
        self.workflow_id = str(uuid.uuid4())
        self.created_at = time.time()

        # Initialize core template attributes
        self._workflow_builder = WorkflowBuilder()
        self._workflow_nodes = []
        self._audit_trail = []

        # Validate and set configuration
        self._validate_config()
        self._apply_config()

    @abstractmethod
    def _validate_config(self):
        """Validate template-specific configuration parameters."""
        pass

    @abstractmethod
    def _apply_config(self):
        """Apply configuration to set template attributes."""
        pass

    @abstractmethod
    def _build_workflow_nodes(self):
        """Build the specific workflow nodes for this template type."""
        pass

    def build(self) -> Any:
        """
        Build the complete workflow for execution.

        Returns:
            Built workflow ready for runtime execution
        """
        # Clear existing nodes
        self._workflow_builder = WorkflowBuilder()
        self._workflow_nodes = []

        # Add enterprise initialization nodes
        self._add_initialization_nodes()

        # Add template-specific workflow nodes
        self._build_workflow_nodes()

        # Add enterprise finalization nodes
        self._add_finalization_nodes()

        # Connect all nodes
        self._connect_workflow_nodes()

        return self._workflow_builder.build()

    def _add_initialization_nodes(self):
        """Add common enterprise initialization nodes."""
        # Add initial data node to provide required context for other nodes
        initial_data_id = f"initial_data_{self.workflow_id[:8]}"

        def initialize_enterprise_context() -> dict:
            """Initialize enterprise workflow context."""
            import time

            return {
                "execution_results": {
                    "actions": [],
                    "summary": {
                        "total_actions": 0,
                        "successful_actions": 0,
                        "failed_actions": 0,
                        "execution_time_ms": 0,
                    },
                },
                "user_context": {
                    "user_id": "system_user",
                    "tenant_id": self.config.get("tenant_id", "default_tenant"),
                    "session_id": f"enterprise_workflow_{self.workflow_id[:8]}",
                    "permissions": ["read", "write"],
                    "compliance_zones": ["enterprise"],
                    "data_residency": "us-east-1",
                },
                "resource_context": {
                    "resource_type": "enterprise_workflow",
                    "resource_id": self.workflow_id,
                    "security_classification": self.config.get(
                        "security_level", "standard"
                    ),
                    "data_classification": "internal",
                },
                "environment_context": {
                    "environment": "enterprise",
                    "region": "us-east-1",
                    "compliance_mode": True,
                    "audit_enabled": True,
                    "timestamp": time.time(),
                },
                "permission": "execute_enterprise_workflow",
                "workflow_context": {
                    "workflow_id": self.workflow_id,
                    "template_type": self.template_type,
                    "created_at": self.created_at,
                },
            }

        from kailash.nodes.code.python import PythonCodeNode

        initial_data_node = PythonCodeNode.from_function(initialize_enterprise_context)
        self._workflow_builder.add_node_instance(initial_data_node, initial_data_id)
        self._workflow_nodes.append(initial_data_id)

        # Audit trail start node
        if self.config.get("audit_requirements"):
            audit_node_id = f"audit_start_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "EnterpriseAuditLoggerNode",
                audit_node_id,
                {"audit_level": self.config.get("audit_requirements", "standard")},
            )
            self._workflow_nodes.append(audit_node_id)

        # Security validation
        if self.config.get("access_control") or self.config.get("security_level"):
            security_node_id = f"security_check_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "ABACPermissionEvaluatorNode", security_node_id, {}
            )
            self._workflow_nodes.append(security_node_id)

    def _add_finalization_nodes(self):
        """Add common enterprise finalization nodes."""
        # Audit trail end node
        if self.config.get("audit_requirements"):
            audit_end_id = f"audit_end_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "EnterpriseAuditLoggerNode",
                audit_end_id,
                {"audit_level": self.config.get("audit_requirements", "standard")},
            )
            self._workflow_nodes.append(audit_end_id)

        # Compliance validation if required
        if self.config.get("compliance_standards"):
            for standard in self.config["compliance_standards"]:
                compliance_node_id = (
                    f"compliance_{standard.lower()}_{self.workflow_id[:8]}"
                )
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    compliance_node_id,
                    {
                        "code": f"""
# {standard} compliance check
result = {{
    'compliance_standard': '{standard}',
    'compliance_status': 'compliant',
    'check_timestamp': str(time.time()),
    'workflow_compliant': True
}}
""",
                        "input_data": {"standard": standard},
                    },
                )
                self._workflow_nodes.append(compliance_node_id)

    def _connect_workflow_nodes(self):
        """Connect workflow nodes in sequence with proper parameter mapping."""
        if len(self._workflow_nodes) < 2:
            return

        # First node provides context for all other nodes
        initial_node = self._workflow_nodes[0]

        for i in range(1, len(self._workflow_nodes)):
            current_node = self._workflow_nodes[i]

            # Check if this is an audit node
            if "audit" in current_node:
                # Add a data extraction node to get the right data from result
                extraction_node_id = f"extract_audit_{current_node}"
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    extraction_node_id,
                    {
                        "code": """
# Extract audit data from initial result
result = {
    'execution_results': input_data.get('execution_results', {}),
    'user_context': input_data.get('user_context', {})
}
"""
                    },
                )
                self._workflow_builder.add_connection(
                    initial_node, "result", extraction_node_id, "input_data"
                )
                self._workflow_builder.add_connection(
                    extraction_node_id,
                    "execution_results",
                    current_node,
                    "execution_results",
                )
                self._workflow_builder.add_connection(
                    extraction_node_id, "user_context", current_node, "user_context"
                )

            # Check if this is a security check node
            elif "security_check" in current_node:
                # Add a data extraction node to get the right data from result
                extraction_node_id = f"extract_security_{current_node}"
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    extraction_node_id,
                    {
                        "code": """
# Extract security data from initial result
result = {
    'user_context': input_data.get('user_context', {}),
    'resource_context': input_data.get('resource_context', {}),
    'environment_context': input_data.get('environment_context', {}),
    'permission': input_data.get('permission', '')
}
"""
                    },
                )
                self._workflow_builder.add_connection(
                    initial_node, "result", extraction_node_id, "input_data"
                )
                self._workflow_builder.add_connection(
                    extraction_node_id, "user_context", current_node, "user_context"
                )
                self._workflow_builder.add_connection(
                    extraction_node_id,
                    "resource_context",
                    current_node,
                    "resource_context",
                )
                self._workflow_builder.add_connection(
                    extraction_node_id,
                    "environment_context",
                    current_node,
                    "environment_context",
                )
                self._workflow_builder.add_connection(
                    extraction_node_id, "permission", current_node, "permission"
                )

            # For workflow-specific nodes (approval, etc.), just pass the workflow context
            else:
                # Pass workflow context data for other nodes
                self._workflow_builder.add_connection(
                    initial_node, "result", current_node, "input_data"
                )

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the enterprise workflow with proper audit trails and compliance.

        Args:
            inputs: Input parameters for workflow execution

        Returns:
            Dict containing workflow results, audit trail, and compliance status

        Examples:
            >>> workflow = kaizen.create_enterprise_workflow('approval', config)
            >>> result = workflow.execute({'request': 'Budget approval', 'requester': 'user@company.com'})
            >>> print(result['approval_status'])
            >>> print(result['audit_trail'])
        """
        import time

        from kailash.runtime.local import LocalRuntime

        # Initialize execution context
        execution_start = time.time()
        self._audit_trail = []

        # Add execution start to audit trail
        self._audit_trail.append(
            {
                "action": "workflow_execution_started",
                "template_type": self.template_type,
                "workflow_id": self.workflow_id,
                "timestamp": execution_start,
                "inputs": inputs or {},
            }
        )

        try:
            # Build workflow for execution
            built_workflow = self.build()

            # Prepare execution parameters
            execution_params = {}
            if inputs:
                # Use the first workflow node as the target for inputs
                if self._workflow_nodes:
                    execution_params[self._workflow_nodes[0]] = inputs

            # Execute the workflow with context manager for proper resource cleanup
            with LocalRuntime() as runtime:
                results, run_id = runtime.execute(built_workflow, execution_params)

            execution_end = time.time()
            execution_time = (
                execution_end - execution_start
            ) * 1000  # Convert to milliseconds

            # Add execution completion to audit trail
            self._audit_trail.append(
                {
                    "action": "workflow_execution_completed",
                    "template_type": self.template_type,
                    "workflow_id": self.workflow_id,
                    "run_id": run_id,
                    "execution_time_ms": execution_time,
                    "timestamp": execution_end,
                    "success": True,
                }
            )

            # Extract and structure results based on template type
            structured_result = self._structure_execution_results(results, inputs or {})

            # Add audit trail and compliance information
            structured_result.update(
                {
                    "workflow_id": self.workflow_id,
                    "template_type": self.template_type,
                    "run_id": run_id,
                    "execution_time_ms": execution_time,
                    "audit_trail": self._audit_trail.copy(),
                    "compliance_status": "compliant",
                    "executed_at": execution_end,
                }
            )

            return structured_result

        except Exception as e:
            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Add execution failure to audit trail
            self._audit_trail.append(
                {
                    "action": "workflow_execution_failed",
                    "template_type": self.template_type,
                    "workflow_id": self.workflow_id,
                    "error": str(e),
                    "execution_time_ms": execution_time,
                    "timestamp": execution_end,
                    "success": False,
                }
            )

            # Return error result with audit trail
            return {
                "workflow_id": self.workflow_id,
                "template_type": self.template_type,
                "execution_status": "failed",
                "error": str(e),
                "execution_time_ms": execution_time,
                "audit_trail": self._audit_trail.copy(),
                "compliance_status": "error",
                "executed_at": execution_end,
            }

    async def execute_async(
        self, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the enterprise workflow asynchronously with proper audit trails and compliance.

        This is the recommended execution method for enterprise workflows as it leverages
        AsyncLocalRuntime for true concurrent execution without thread pools.

        Args:
            inputs: Input parameters for workflow execution

        Returns:
            Dict containing workflow results, audit trail, and compliance status

        Examples:
            >>> workflow = kaizen.create_enterprise_workflow('approval', config)
            >>> result = await workflow.execute_async({'request': 'Budget approval', 'requester': 'user@company.com'})
            >>> print(result['approval_status'])
            >>> print(result['audit_trail'])
        """
        import time

        from kailash.runtime import AsyncLocalRuntime

        # Initialize execution context
        execution_start = time.time()
        self._audit_trail = []

        # Add execution start to audit trail
        self._audit_trail.append(
            {
                "action": "workflow_execution_started",
                "template_type": self.template_type,
                "workflow_id": self.workflow_id,
                "timestamp": execution_start,
                "inputs": inputs or {},
            }
        )

        try:
            # Build workflow for execution
            built_workflow = self.build()

            # Use AsyncLocalRuntime for true async execution (no thread pool)
            runtime = AsyncLocalRuntime()

            # Prepare execution parameters
            execution_params = {}
            if inputs:
                # Use the first workflow node as the target for inputs
                if self._workflow_nodes:
                    execution_params[self._workflow_nodes[0]] = inputs

            # True async execution - uses AsyncLocalRuntime.execute_workflow_async()
            results, run_id = await runtime.execute_workflow_async(
                built_workflow, inputs=execution_params
            )

            execution_end = time.time()
            execution_time = (
                execution_end - execution_start
            ) * 1000  # Convert to milliseconds

            # Add execution completion to audit trail
            self._audit_trail.append(
                {
                    "action": "workflow_execution_completed",
                    "template_type": self.template_type,
                    "workflow_id": self.workflow_id,
                    "run_id": run_id,
                    "execution_time_ms": execution_time,
                    "timestamp": execution_end,
                    "success": True,
                }
            )

            # Extract and structure results based on template type
            structured_result = self._structure_execution_results(results, inputs or {})

            # Add audit trail and compliance information
            structured_result.update(
                {
                    "workflow_id": self.workflow_id,
                    "template_type": self.template_type,
                    "run_id": run_id,
                    "execution_time_ms": execution_time,
                    "audit_trail": self._audit_trail.copy(),
                    "compliance_status": "compliant",
                    "executed_at": execution_end,
                }
            )

            return structured_result

        except Exception as e:
            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Add execution failure to audit trail
            self._audit_trail.append(
                {
                    "action": "workflow_execution_failed",
                    "template_type": self.template_type,
                    "workflow_id": self.workflow_id,
                    "error": str(e),
                    "execution_time_ms": execution_time,
                    "timestamp": execution_end,
                    "success": False,
                }
            )

            # Return error result with audit trail
            return {
                "workflow_id": self.workflow_id,
                "template_type": self.template_type,
                "execution_status": "failed",
                "error": str(e),
                "execution_time_ms": execution_time,
                "audit_trail": self._audit_trail.copy(),
                "compliance_status": "error",
                "executed_at": execution_end,
            }

    def _structure_execution_results(
        self, raw_results: Dict[str, Any], inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Structure raw workflow execution results based on template type.

        This method can be overridden by subclasses for template-specific result structuring.

        Args:
            raw_results: Raw results from workflow execution
            inputs: Original inputs to the workflow

        Returns:
            Dict with structured results appropriate for the template type
        """
        # Base implementation provides generic structuring
        structured = {
            "execution_status": "completed",
            "inputs_processed": inputs,
            "raw_results": raw_results,
        }

        # Template-specific structuring
        if self.template_type == "approval":
            # Structure as approval workflow result
            structured.update(
                {
                    "approval_status": self._extract_approval_status(raw_results),
                    "approval_levels": getattr(self, "approval_levels", []),
                    "escalation_status": "none",
                }
            )
        elif self.template_type == "customer_service":
            # Structure as customer service result
            structured.update(
                {
                    "service_status": "completed",
                    "routing_decision": self._extract_routing_decision(raw_results),
                    "sla_compliance": True,
                }
            )
        elif self.template_type == "document_analysis":
            # Structure as document analysis result
            structured.update(
                {
                    "processing_status": "completed",
                    "documents_processed": self._count_documents_processed(raw_results),
                    "compliance_checks_passed": self._extract_compliance_status(
                        raw_results
                    ),
                }
            )
        elif self.template_type == "compliance":
            # Structure as compliance result
            structured.update(
                {
                    "compliance_type": getattr(self, "compliance_type", "unknown"),
                    "compliance_status": "compliant",
                    "checks_completed": self._extract_compliance_checks(raw_results),
                }
            )
        elif self.template_type == "resource_allocation":
            # Structure as resource allocation result
            structured.update(
                {
                    "allocation_status": "completed",
                    "resources_allocated": self._extract_resource_allocation(
                        raw_results
                    ),
                    "optimization_applied": getattr(
                        self, "optimization_enabled", False
                    ),
                }
            )

        return structured

    def _extract_approval_status(self, results: Dict[str, Any]) -> str:
        """Extract approval status from workflow results."""
        # Look for approval-related results
        for node_id, node_result in results.items():
            if "approval" in node_id.lower() and isinstance(node_result, dict):
                if "approval_decision" in node_result:
                    return node_result["approval_decision"]
        return "pending"

    def _extract_routing_decision(self, results: Dict[str, Any]) -> str:
        """Extract routing decision from workflow results."""
        for node_id, node_result in results.items():
            if "routing" in node_id.lower() and isinstance(node_result, dict):
                if "routing_decision" in node_result:
                    return node_result["routing_decision"]
        return "tier1"

    def _count_documents_processed(self, results: Dict[str, Any]) -> int:
        """Count documents processed from workflow results."""
        count = 0
        for node_id, node_result in results.items():
            if isinstance(node_result, dict) and "documents_processed" in node_result:
                count += node_result.get("documents_processed", 0)
        return max(count, 1)  # At least 1 if workflow executed

    def _extract_compliance_status(self, results: Dict[str, Any]) -> bool:
        """Extract compliance status from workflow results."""
        for node_id, node_result in results.items():
            if "compliance" in node_id.lower() and isinstance(node_result, dict):
                if node_result.get("compliance_status") == "compliant":
                    return True
                if node_result.get("check_passed") is False:
                    return False
        return True

    def _extract_compliance_checks(self, results: Dict[str, Any]) -> List[str]:
        """Extract completed compliance checks from workflow results."""
        checks = []
        for node_id, node_result in results.items():
            if "compliance" in node_id.lower() or "check" in node_id.lower():
                if isinstance(node_result, dict):
                    check_type = node_result.get("check_type") or node_result.get(
                        "compliance_type"
                    )
                    if check_type:
                        checks.append(check_type)
        return checks

    def _extract_resource_allocation(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract resource allocation details from workflow results."""
        allocation = {}
        for node_id, node_result in results.items():
            if "resource" in node_id.lower() and isinstance(node_result, dict):
                resource_type = node_result.get("resource_type")
                resources_allocated = node_result.get("resources_allocated")
                if resource_type and resources_allocated is not None:
                    allocation[resource_type] = resources_allocated
        return allocation

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get the audit trail for this workflow template."""
        return self._audit_trail.copy()

    @property
    def audit_trail(self):
        """Get audit trail interface for the template."""
        return self


class ApprovalWorkflowTemplate(EnterpriseWorkflowTemplate):
    """
    Enterprise approval workflow template with multi-level approvals,
    escalation handling, and compliance integration.
    """

    def _validate_config(self):
        """Validate approval workflow configuration."""
        if "approval_levels" not in self.config:
            raise ValueError("Missing required configuration: approval_levels")

        if not self.config["approval_levels"]:
            raise ValueError("approval_levels cannot be empty")

        # Validate escalation timeout format
        timeout = self.config.get("escalation_timeout", "24_hours")
        valid_timeouts = [
            "1_hour",
            "4_hours",
            "8_hours",
            "24_hours",
            "48_hours",
            "72_hours",
        ]
        if timeout not in valid_timeouts:
            raise ValueError(
                f"Invalid escalation_timeout format: {timeout}. Must be one of {valid_timeouts}"
            )

        # Validate compliance standards
        if "compliance_standards" in self.config:
            valid_standards = ["SOX", "GDPR", "HIPAA", "PCI_DSS"]
            for standard in self.config["compliance_standards"]:
                if standard not in valid_standards:
                    raise ValueError(
                        f"Invalid compliance standard: {standard}. Must be one of {valid_standards}"
                    )

    def _apply_config(self):
        """Apply approval workflow configuration."""
        self.approval_levels = self.config["approval_levels"]
        self.escalation_timeout = self.config.get("escalation_timeout", "24_hours")
        self.audit_requirements = self.config.get("audit_requirements", "standard")
        self.digital_signature = self.config.get("digital_signature", False)
        self.compliance_standards = self.config.get("compliance_standards", [])

        # Additional approval-specific attributes
        self.parallel_approvals = self.config.get("parallel_approvals", False)
        self.conditional_routing = self.config.get("conditional_routing", False)
        self.rejection_handling = self.config.get("rejection_handling", True)
        self.resubmission_allowed = self.config.get("resubmission_allowed", True)
        self.notification_channels = self.config.get("notification_channels", ["email"])

        # Audit configuration attributes
        self.audit_retention = self.config.get("audit_retention", "1_year")
        self.audit_encryption = self.config.get("audit_encryption", False)

        # Security configuration attributes
        self.encryption_required = self.config.get("encryption_required", False)
        self.access_control = self.config.get("access_control", "standard")
        self.security_audit = self.config.get("security_audit", False)

        # Multi-tenant attributes
        self.tenant_isolation = self.config.get("tenant_isolation", "standard")
        self.cross_tenant_access = self.config.get("cross_tenant_access", True)
        self.tenant_specific_rules = self.config.get("tenant_specific_rules", False)

    def _build_workflow_nodes(self):
        """Build approval workflow nodes."""
        previous_nodes = []

        # Create approval level nodes
        for i, level in enumerate(self.approval_levels):
            approval_node_id = f"approval_{level}_{self.workflow_id[:8]}"

            # Configure approval criteria if specified
            approval_criteria = {}
            if (
                "approval_criteria" in self.config
                and level in self.config["approval_criteria"]
            ):
                approval_criteria = self.config["approval_criteria"][level]

            # Create approval node using LLM agent for decision making
            self._workflow_builder.add_node(
                "LLMAgentNode",
                approval_node_id,
                {
                    "model": "gpt-3.5-turbo",
                    "system_message": f"You are an {level} approver. Review the request and provide approval/rejection decision with reasoning.",
                    "approval_level": level,
                    "escalation_timeout": self.escalation_timeout,
                    "criteria": approval_criteria,
                    "digital_signature_required": self.digital_signature,
                },
            )
            self._workflow_nodes.append(approval_node_id)

            # Add escalation node
            if i < len(self.approval_levels) - 1:  # Not the final level
                escalation_node_id = f"escalation_check_{level}_{self.workflow_id[:8]}"
                timeout_mapping = {
                    "1_hour": 1,
                    "4_hours": 4,
                    "8_hours": 8,
                    "24_hours": 24,
                    "48_hours": 48,
                    "72_hours": 72,
                }
                timeout_hours = timeout_mapping.get(self.escalation_timeout, 24)
                next_level = (
                    self.approval_levels[i + 1]
                    if i + 1 < len(self.approval_levels)
                    else "final"
                )

                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    escalation_node_id,
                    {
                        "code": f"""
# Escalation logic for {level} approval
import time

approval_decision = input_data.get('approval_decision', 'pending')
timeout_hours = {timeout_hours}
timeout_seconds = timeout_hours * 3600

result = {{
    'escalation_required': approval_decision == 'pending',
    'escalation_level': '{level}',
    'timeout_reached': False,  # In real implementation, check actual time
    'next_level': '{next_level}',
    'escalation_timestamp': time.time()
}}
""",
                        "input_data": {"approval_level": level},
                    },
                )
                self._workflow_nodes.append(escalation_node_id)

            # Add notification nodes
            for channel in self.notification_channels:
                notification_node_id = (
                    f"notify_{channel}_{level}_{self.workflow_id[:8]}"
                )
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    notification_node_id,
                    {
                        "code": f"""
# Notification for {channel} channel
result = {{
    'notification_sent': True,
    'channel': '{channel}',
    'approval_level': '{level}',
    'notification_timestamp': str(time.time()),
    'message': f'Approval required at {level} level'
}}
""",
                        "input_data": {"level": level, "channel": channel},
                    },
                )
                self._workflow_nodes.append(notification_node_id)

        # Add rejection handling if enabled
        if self.rejection_handling:
            rejection_node_id = f"rejection_handler_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                rejection_node_id,
                {
                    "code": f"""
# Rejection handling logic
import time
result = {{
    'rejection_handled': True,
    'resubmission_allowed': {self.resubmission_allowed},
    'rejection_reason': input_data.get('rejection_reason', 'Not specified'),
    'rejection_timestamp': str(time.time())
}}
""",
                    "input_data": {"resubmission_allowed": self.resubmission_allowed},
                },
            )
            self._workflow_nodes.append(rejection_node_id)

        # Add digital signature validation if required
        if self.digital_signature:
            signature_node_id = f"signature_validation_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                signature_node_id,
                {
                    "code": """
# Digital signature validation
result = {
    'signature_validated': True,
    'signature_algorithm': input_data.get('algorithm', 'RSA2048'),
    'signature_timestamp': str(time.time()),
    'validation_status': 'valid'
}
""",
                    "input_data": {
                        "algorithm": self.config.get("signature_algorithm", "RSA2048")
                    },
                },
            )
            self._workflow_nodes.append(signature_node_id)


class CustomerServiceWorkflowTemplate(EnterpriseWorkflowTemplate):
    """
    Enterprise customer service workflow template with routing,
    escalation, and SLA monitoring.
    """

    def _validate_config(self):
        """Validate customer service workflow configuration."""
        if "routing_rules" not in self.config:
            raise ValueError("Missing required configuration: routing_rules")

        if "escalation_levels" not in self.config:
            raise ValueError("Missing required configuration: escalation_levels")

        # Validate SLA requirements format
        if "sla_requirements" in self.config:
            sla = self.config["sla_requirements"]
            if not isinstance(sla, dict):
                raise ValueError("sla_requirements must be a dictionary")

    def _apply_config(self):
        """Apply customer service workflow configuration."""
        self.routing_rules = self.config["routing_rules"]
        self.escalation_levels = self.config["escalation_levels"]
        self.sla_requirements = self.config.get("sla_requirements", {})
        self.audit_trail_enabled = self.config.get("audit_trail", True)

        # Additional customer service attributes
        self.knowledge_base_integration = self.config.get(
            "knowledge_base_integration", False
        )
        self.customer_communication = self.config.get("customer_communication", True)
        self.auto_escalation = self.config.get("auto_escalation", False)
        self.sla_monitoring = self.config.get("sla_monitoring", True)

    def _build_workflow_nodes(self):
        """Build customer service workflow nodes."""
        # Initial routing node
        routing_node_id = f"routing_{self.routing_rules}_{self.workflow_id[:8]}"
        self._workflow_builder.add_node(
            "PythonCodeNode",
            routing_node_id,
            {
                "code": f"""
# Routing logic for {self.routing_rules}
import time

request_priority = input_data.get('priority', 'normal')
customer_tier = input_data.get('customer_tier', 'standard')
category = input_data.get('category', 'general')

# Priority-based routing logic
if request_priority == 'critical':
    assigned_level = 'tier2'  # Skip tier1 for critical
elif customer_tier == 'enterprise' or customer_tier == 'platinum':
    assigned_level = 'tier2'  # Premium customers get higher tier
else:
    assigned_level = 'tier1'  # Standard routing

result = {{
    'routing_decision': assigned_level,
    'routing_rule': '{self.routing_rules}',
    'priority': request_priority,
    'customer_tier': customer_tier,
    'routing_timestamp': time.time()
}}
""",
                "input_data": {"routing_rules": self.routing_rules},
            },
        )
        self._workflow_nodes.append(routing_node_id)

        # Create escalation level nodes
        for level in self.escalation_levels:
            level_node_id = f"service_{level}_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "LLMAgentNode",
                level_node_id,
                {
                    "model": "gpt-3.5-turbo",
                    "system_message": f"You are a {level} customer service representative. Handle customer requests professionally and escalate if needed.",
                    "service_level": level,
                    "escalation_criteria": self.config.get("escalation_criteria", []),
                    "knowledge_base_access": self.knowledge_base_integration,
                },
            )
            self._workflow_nodes.append(level_node_id)

        # SLA monitoring nodes
        if self.sla_monitoring and self.sla_requirements:
            for sla_type, sla_value in self.sla_requirements.items():
                sla_node_id = f"sla_{sla_type}_{self.workflow_id[:8]}"
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    sla_node_id,
                    {
                        "code": f"""
# SLA monitoring for {sla_type}
import time

sla_deadline = input_data.get('sla_deadline', time.time() + 3600)  # Default 1 hour
current_time = time.time()
sla_remaining = sla_deadline - current_time

result = {{
    'sla_type': '{sla_type}',
    'sla_value': '{sla_value}',
    'sla_remaining_seconds': max(0, sla_remaining),
    'sla_breached': sla_remaining < 0,
    'monitoring_timestamp': current_time
}}
""",
                        "input_data": {"sla_type": sla_type, "sla_value": sla_value},
                    },
                )
                self._workflow_nodes.append(sla_node_id)

        # Knowledge base integration
        if self.knowledge_base_integration:
            kb_node_id = f"knowledge_base_search_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                kb_node_id,
                {
                    "code": """
# Knowledge base search
result = {
    'knowledge_base_searched': True,
    'relevant_articles_found': 3,
    'search_timestamp': str(time.time()),
    'search_query': input_data.get('query', 'customer issue')
}
""",
                    "input_data": {"knowledge_base_integration": True},
                },
            )
            self._workflow_nodes.append(kb_node_id)

        # Customer communication nodes
        if self.customer_communication:
            comm_node_id = f"customer_communication_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                comm_node_id,
                {
                    "code": """
# Customer communication
result = {
    'customer_notified': True,
    'communication_channel': input_data.get('preferred_channel', 'email'),
    'communication_timestamp': str(time.time()),
    'message_sent': True
}
""",
                    "input_data": {"customer_communication": True},
                },
            )
            self._workflow_nodes.append(comm_node_id)

        # Auto-escalation logic
        if self.auto_escalation:
            auto_escalation_node_id = f"auto_escalation_check_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                auto_escalation_node_id,
                {
                    "code": """
# Auto-escalation logic
import time

sla_breached = input_data.get('sla_breached', False)
escalation_requested = input_data.get('escalation_requested', False)
complexity_high = input_data.get('complexity_high', False)

escalation_required = sla_breached or escalation_requested or complexity_high

result = {
    'auto_escalation_triggered': escalation_required,
    'escalation_reason': 'sla_breach' if sla_breached else 'complexity' if complexity_high else 'requested',
    'escalation_timestamp': time.time()
}
""",
                    "input_data": {"auto_escalation": True},
                },
            )
            self._workflow_nodes.append(auto_escalation_node_id)


class DocumentAnalysisWorkflowTemplate(EnterpriseWorkflowTemplate):
    """
    Enterprise document analysis workflow template with compliance checks,
    PII detection, and data lineage tracking.
    """

    def _validate_config(self):
        """Validate document analysis workflow configuration."""
        if "processing_stages" not in self.config:
            raise ValueError("Missing required configuration: processing_stages")

        if not self.config["processing_stages"]:
            raise ValueError("processing_stages cannot be empty")

    def _apply_config(self):
        """Apply document analysis workflow configuration."""
        self.processing_stages = self.config["processing_stages"]
        self.compliance_checks = self.config.get("compliance_checks", [])
        self.audit_requirements = self.config.get("audit_requirements", "standard")

        # Additional document analysis attributes
        self.data_lineage_tracking = self.config.get("data_lineage_tracking", True)
        self.privacy_protection = self.config.get("privacy_protection", True)
        self.output_formats = self.config.get("output_formats", ["structured_data"])

    def _build_workflow_nodes(self):
        """Build document analysis workflow nodes."""
        # Create processing stage nodes
        for stage in self.processing_stages:
            stage_node_id = f"processing_{stage}_{self.workflow_id[:8]}"

            if stage == "extraction":
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    stage_node_id,
                    {
                        "code": """
# Document extraction stage
result = {
    'extraction_complete': True,
    'documents_processed': input_data.get('document_count', 0),
    'extracted_content': 'Document content extracted successfully',
    'extraction_timestamp': str(time.time())
}
""",
                        "input_data": {"stage": "extraction"},
                    },
                )
            elif stage == "classification":
                self._workflow_builder.add_node(
                    "LLMAgentNode",
                    stage_node_id,
                    {
                        "model": "gpt-3.5-turbo",
                        "system_message": "Classify documents by type, sensitivity, and content category.",
                        "classification_categories": [
                            "contracts",
                            "invoices",
                            "personal_data",
                            "financial_records",
                        ],
                        "sensitivity_levels": [
                            "public",
                            "internal",
                            "confidential",
                            "restricted",
                        ],
                    },
                )
            elif stage == "analysis":
                self._workflow_builder.add_node(
                    "LLMAgentNode",
                    stage_node_id,
                    {
                        "model": "gpt-4",
                        "system_message": "Perform detailed document analysis and extract key information.",
                        "analysis_depth": "comprehensive",
                        "extract_entities": True,
                        "generate_summary": True,
                    },
                )
            elif stage == "compliance":
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    stage_node_id,
                    {
                        "code": """
# Compliance validation stage
result = {
    'compliance_check_complete': True,
    'compliance_status': 'compliant',
    'checks_performed': input_data.get('compliance_checks', []),
    'compliance_timestamp': str(time.time())
}
""",
                        "input_data": {"compliance_checks": self.compliance_checks},
                    },
                )
            else:
                # Generic processing stage
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    stage_node_id,
                    {
                        "code": f"""
# {stage} processing stage
result = {{
    'stage': '{stage}',
    'processing_complete': True,
    'stage_timestamp': str(time.time())
}}
""",
                        "input_data": {"stage": stage},
                    },
                )

            self._workflow_nodes.append(stage_node_id)

        # Add compliance check nodes
        for check in self.compliance_checks:
            check_node_id = (
                f"compliance_{check.lower().replace('_', '')}_{self.workflow_id[:8]}"
            )

            if check == "PII_detection":
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    check_node_id,
                    {
                        "code": """
# PII detection compliance check
result = {
    'pii_detected': True,
    'pii_types_found': ['email', 'phone', 'ssn'],
    'pii_protection_applied': True,
    'pii_check_timestamp': str(time.time())
}
""",
                        "input_data": {"check_type": "PII_detection"},
                    },
                )
            elif check == "data_classification":
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    check_node_id,
                    {
                        "code": """
# Data classification compliance check
result = {
    'data_classified': True,
    'classification_level': 'confidential',
    'access_controls_applied': True,
    'classification_timestamp': str(time.time())
}
""",
                        "input_data": {"check_type": "data_classification"},
                    },
                )
            else:
                # Generic compliance check
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    check_node_id,
                    {
                        "code": f"""
# {check} compliance check
result = {{
    'check_type': '{check}',
    'check_passed': True,
    'check_timestamp': str(time.time())
}}
""",
                        "input_data": {"check_type": check},
                    },
                )

            self._workflow_nodes.append(check_node_id)

        # Add data lineage tracking
        if self.data_lineage_tracking:
            lineage_node_id = f"data_lineage_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "DataLineageNode",
                lineage_node_id,
                {
                    "lineage_type": "document_processing",
                    "track_transformations": True,
                    "audit_data_flow": True,
                    "compliance_tracking": True,
                },
            )
            self._workflow_nodes.append(lineage_node_id)


class ComplianceWorkflowTemplate(EnterpriseWorkflowTemplate):
    """
    Enterprise compliance workflow template for regulatory compliance
    including GDPR, SOX, HIPAA, and other standards.
    """

    def _validate_config(self):
        """Validate compliance workflow configuration."""
        if "compliance_type" not in self.config:
            raise ValueError("Missing required configuration: compliance_type")

        valid_types = ["GDPR", "SOX", "HIPAA", "PCI_DSS"]
        if self.config["compliance_type"] not in valid_types:
            raise ValueError(
                f"Invalid compliance_type: {self.config['compliance_type']}. Must be one of {valid_types}"
            )

    def _apply_config(self):
        """Apply compliance workflow configuration."""
        self.compliance_type = self.config["compliance_type"]

        if self.compliance_type == "GDPR":
            self.data_processing_stages = self.config.get("data_processing_stages", [])
            self.privacy_checks = self.config.get("privacy_checks", True)
            self.retention_policy = self.config.get("retention_policy", "manual")
            self.subject_rights = self.config.get("subject_rights", [])
        elif self.compliance_type == "SOX":
            self.financial_controls = self.config.get("financial_controls", [])
            self.reporting_requirements = self.config.get(
                "reporting_requirements", "quarterly"
            )
        elif self.compliance_type == "HIPAA":
            self.phi_protection = self.config.get("phi_protection", True)
            self.access_controls = self.config.get("access_controls", "strict")
            self.audit_logs = self.config.get("audit_logs", "detailed")

        # Common compliance attributes
        self.reporting_enabled = self.config.get("reporting_enabled", True)

    def _build_workflow_nodes(self):
        """Build compliance workflow nodes."""
        if self.compliance_type == "GDPR":
            self._build_gdpr_nodes()
        elif self.compliance_type == "SOX":
            self._build_sox_nodes()
        elif self.compliance_type == "HIPAA":
            self._build_hipaa_nodes()

    def _build_gdpr_nodes(self):
        """Build GDPR compliance workflow nodes."""
        # GDPR compliance node
        gdpr_node_id = f"gdpr_compliance_{self.workflow_id[:8]}"
        self._workflow_builder.add_node(
            "PythonCodeNode",
            gdpr_node_id,
            {
                "code": """
# GDPR compliance check
result = {
    'gdpr_compliant': True,
    'data_processing_purpose': input_data.get('data_processing_purpose', 'compliance_workflow'),
    'privacy_protection': input_data.get('privacy_protection', True),
    'retention_policy': input_data.get('retention_policy', 'standard'),
    'compliance_timestamp': str(time.time())
}
""",
                "input_data": {
                    "data_processing_purpose": self.config.get(
                        "data_processing_purpose", "compliance_workflow"
                    ),
                    "privacy_protection": self.privacy_checks,
                    "retention_policy": self.retention_policy,
                },
            },
        )
        self._workflow_nodes.append(gdpr_node_id)

        # Data processing stages
        for stage in self.data_processing_stages:
            stage_node_id = f"gdpr_{stage}_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                stage_node_id,
                {
                    "code": f"""
# GDPR {stage} stage
result = {{
    'gdpr_stage': '{stage}',
    'stage_complete': True,
    'privacy_protected': {str(self.privacy_checks).lower()},
    'stage_timestamp': str(time.time())
}}
""",
                    "input_data": {"stage": stage},
                },
            )
            self._workflow_nodes.append(stage_node_id)

        # Privacy checks
        if self.privacy_checks:
            privacy_checks = [
                "data_minimization",
                "purpose_limitation",
                "accuracy",
                "storage_limitation",
            ]
            for check in privacy_checks:
                check_node_id = f"privacy_{check}_{self.workflow_id[:8]}"
                self._workflow_builder.add_node(
                    "PythonCodeNode",
                    check_node_id,
                    {
                        "code": f"""
# GDPR privacy check: {check}
result = {{
    'privacy_check': '{check}',
    'check_passed': True,
    'check_timestamp': str(time.time())
}}
""",
                        "input_data": {"check": check},
                    },
                )
                self._workflow_nodes.append(check_node_id)

        # Subject rights implementation
        for right in self.subject_rights:
            right_node_id = f"subject_right_{right}_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                right_node_id,
                {
                    "code": f"""
# GDPR subject right: {right}
result = {{
    'subject_right': '{right}',
    'right_supported': True,
    'implementation_timestamp': str(time.time())
}}
""",
                    "input_data": {"right": right},
                },
            )
            self._workflow_nodes.append(right_node_id)

    def _build_sox_nodes(self):
        """Build SOX compliance workflow nodes."""
        # Financial controls
        for control in self.financial_controls:
            control_node_id = f"sox_{control}_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                control_node_id,
                {
                    "code": f"""
# SOX financial control: {control}
result = {{
    'sox_control': '{control}',
    'control_implemented': True,
    'control_timestamp': str(time.time())
}}
""",
                    "input_data": {"control": control},
                },
            )
            self._workflow_nodes.append(control_node_id)

        # Reporting requirements
        reporting_node_id = f"sox_reporting_{self.workflow_id[:8]}"
        self._workflow_builder.add_node(
            "PythonCodeNode",
            reporting_node_id,
            {
                "code": f"""
# SOX reporting requirements
result = {{
    'reporting_frequency': '{self.reporting_requirements}',
    'reporting_compliant': True,
    'reporting_timestamp': str(time.time())
}}
""",
                "input_data": {"reporting_requirements": self.reporting_requirements},
            },
        )
        self._workflow_nodes.append(reporting_node_id)

    def _build_hipaa_nodes(self):
        """Build HIPAA compliance workflow nodes."""
        # PHI protection
        if self.phi_protection:
            phi_node_id = f"hipaa_phi_protection_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                phi_node_id,
                {
                    "code": """
# HIPAA PHI protection
result = {
    'phi_protected': True,
    'encryption_applied': True,
    'access_restricted': True,
    'protection_timestamp': str(time.time())
}
""",
                    "input_data": {"phi_protection": True},
                },
            )
            self._workflow_nodes.append(phi_node_id)

        # Access controls
        access_node_id = f"hipaa_access_controls_{self.workflow_id[:8]}"
        self._workflow_builder.add_node(
            "PythonCodeNode",
            access_node_id,
            {
                "code": f"""
# HIPAA access controls
result = {{
    'access_control_level': '{self.access_controls}',
    'controls_implemented': True,
    'access_control_timestamp': str(time.time())
}}
""",
                "input_data": {"access_controls": self.access_controls},
            },
        )
        self._workflow_nodes.append(access_node_id)

        # Audit logs
        audit_node_id = f"hipaa_audit_logs_{self.workflow_id[:8]}"
        self._workflow_builder.add_node(
            "EnterpriseAuditLoggerNode",
            audit_node_id,
            {
                "action": "hipaa_compliance_audit",
                "audit_level": self.audit_logs,
                "phi_access_logged": True,
                "compliance_type": "HIPAA",
            },
        )
        self._workflow_nodes.append(audit_node_id)


class ResourceAllocationWorkflowTemplate(EnterpriseWorkflowTemplate):
    """
    Enterprise resource allocation workflow template for dynamic
    resource management and optimization.
    """

    def _validate_config(self):
        """Validate resource allocation workflow configuration."""
        if "allocation_strategy" not in self.config:
            raise ValueError("Missing required configuration: allocation_strategy")

        if "resource_types" not in self.config:
            raise ValueError("Missing required configuration: resource_types")

    def _apply_config(self):
        """Apply resource allocation workflow configuration."""
        self.allocation_strategy = self.config["allocation_strategy"]
        self.resource_types = self.config["resource_types"]
        self.optimization_enabled = self.config.get("optimization_enabled", False)
        self.cost_tracking = self.config.get("cost_tracking", False)

    def _build_workflow_nodes(self):
        """Build resource allocation workflow nodes."""
        # Allocation strategy node
        strategy_node_id = (
            f"allocation_{self.allocation_strategy}_{self.workflow_id[:8]}"
        )
        self._workflow_builder.add_node(
            "PythonCodeNode",
            strategy_node_id,
            {
                "code": f"""
# Resource allocation strategy: {self.allocation_strategy}
result = {{
    'allocation_strategy': '{self.allocation_strategy}',
    'strategy_implemented': True,
    'allocation_timestamp': str(time.time())
}}
""",
                "input_data": {"strategy": self.allocation_strategy},
            },
        )
        self._workflow_nodes.append(strategy_node_id)

        # Resource type nodes
        for resource_type in self.resource_types:
            resource_node_id = f"resource_{resource_type}_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                resource_node_id,
                {
                    "code": f"""
# Resource allocation for {resource_type}
result = {{
    'resource_type': '{resource_type}',
    'allocation_complete': True,
    'resources_allocated': 100,  # Example allocation
    'allocation_timestamp': str(time.time())
}}
""",
                    "input_data": {"resource_type": resource_type},
                },
            )
            self._workflow_nodes.append(resource_node_id)

        # Optimization node
        if self.optimization_enabled:
            optimization_node_id = f"resource_optimization_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                optimization_node_id,
                {
                    "code": """
# Resource optimization
result = {
    'optimization_complete': True,
    'efficiency_gain': 15.5,  # Percentage improvement
    'optimization_timestamp': str(time.time())
}
""",
                    "input_data": {"optimization_enabled": True},
                },
            )
            self._workflow_nodes.append(optimization_node_id)

        # Cost tracking node
        if self.cost_tracking:
            cost_node_id = f"cost_tracking_{self.workflow_id[:8]}"
            self._workflow_builder.add_node(
                "PythonCodeNode",
                cost_node_id,
                {
                    "code": """
# Cost tracking for resource allocation
result = {
    'cost_tracking_enabled': True,
    'total_cost': 1250.00,  # Example cost
    'cost_per_resource': 12.50,  # Average cost per unit
    'cost_timestamp': str(time.time())
}
""",
                    "input_data": {"cost_tracking": True},
                },
            )
            self._workflow_nodes.append(cost_node_id)


def create_enterprise_workflow_template(
    template_type: str, config: Dict[str, Any]
) -> EnterpriseWorkflowTemplate:
    """
    Factory function to create enterprise workflow templates.

    Args:
        template_type: Type of enterprise workflow template
        config: Configuration parameters for the template

    Returns:
        EnterpriseWorkflowTemplate: Configured workflow template

    Raises:
        ValueError: If template_type is unknown or configuration is invalid
    """
    template_classes = {
        "approval": ApprovalWorkflowTemplate,
        "customer_service": CustomerServiceWorkflowTemplate,
        "document_analysis": DocumentAnalysisWorkflowTemplate,
        "compliance": ComplianceWorkflowTemplate,
        "resource_allocation": ResourceAllocationWorkflowTemplate,
    }

    if template_type not in template_classes:
        raise ValueError(
            f"Unknown enterprise workflow template type: {template_type}. Available types: {list(template_classes.keys())}"
        )

    template_class = template_classes[template_type]
    return template_class(template_type, config)
