"""Enterprise service discovery node for MCP service management."""

from typing import Any, Dict, List

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError


@register_node()
class MCPServiceDiscoveryNode(Node):
    """Discovers available MCP services based on tenant context and requirements.

    This node manages service discovery for multi-tenant MCP environments,
    ensuring tenants only access services they're authorized to use.
    """

    metadata = NodeMetadata(
        name="MCPServiceDiscoveryNode",
        description="Discovers MCP services for tenant-specific requirements",
        version="1.0.0",
        tags={"enterprise", "mcp", "service-discovery"},
    )

    def __init__(self, name: str = None, **kwargs):
        self.name = name or self.__class__.__name__
        super().__init__(name=self.name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "tenant": NodeParameter(
                name="tenant",
                type=dict,
                description="Tenant information",
                required=True,
            ),
            "user_context": NodeParameter(
                name="user_context",
                type=dict,
                description="User context with permissions",
                required=True,
            ),
            "service_requirements": NodeParameter(
                name="service_requirements",
                type=list,
                description="Required service types",
                required=False,
                default=[],
            ),
        }

    def run(
        self,
        tenant: Dict,
        user_context: Dict,
        service_requirements: List[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Discover available MCP services for the tenant."""
        try:
            if service_requirements is None:
                service_requirements = []

            tenant_id = tenant.get("id", "default")
            compliance_zones = tenant.get("compliance_zones", ["public"])
            data_residency = tenant.get("data_residency", "us-west-1")

            # Define available services per tenant
            available_services = {
                "healthcare-corp": [
                    {
                        "id": "health-analytics-mcp",
                        "type": "analytics",
                        "region": "us-east-1",
                        "compliance": ["hipaa", "gdpr"],
                        "tools": ["patient_analytics", "health_metrics"],
                        "endpoint": "https://health-analytics.mcp.healthcare.com",
                    },
                    {
                        "id": "patient-data-mcp",
                        "type": "data",
                        "region": "us-east-1",
                        "compliance": ["hipaa"],
                        "tools": ["patient_lookup", "medical_records"],
                        "endpoint": "https://patient-data.mcp.healthcare.com",
                    },
                ],
                "finance-inc": [
                    {
                        "id": "transaction-analytics-mcp",
                        "type": "analytics",
                        "region": "us-east-1",
                        "compliance": ["sox", "pci_dss"],
                        "tools": ["transaction_analysis", "fraud_detection"],
                        "endpoint": "https://transaction-analytics.mcp.finance.com",
                    },
                    {
                        "id": "risk-assessment-mcp",
                        "type": "risk",
                        "region": "us-east-1",
                        "compliance": ["sox"],
                        "tools": ["risk_scoring", "compliance_check"],
                        "endpoint": "https://risk-assessment.mcp.finance.com",
                    },
                ],
                "default": [
                    {
                        "id": "general-analytics-mcp",
                        "type": "analytics",
                        "region": "us-west-1",
                        "compliance": ["public"],
                        "tools": ["basic_analytics", "reporting"],
                        "endpoint": "https://general-analytics.mcp.kailash.ai",
                    },
                ],
            }

            # Get services for this tenant
            services = available_services.get(tenant_id, available_services["default"])

            # Filter by service requirements
            if service_requirements:
                services = [s for s in services if s["type"] in service_requirements]

            # Filter by compliance requirements
            user_compliance = set(compliance_zones)
            filtered_services = []
            for service in services:
                service_compliance = set(service.get("compliance", ["public"]))
                if (
                    user_compliance.intersection(service_compliance)
                    or "public" in service_compliance
                ):
                    filtered_services.append(service)

            # Filter by data residency if required
            if data_residency:
                filtered_services = [
                    s for s in filtered_services if s.get("region") == data_residency
                ]

            return {
                "discovered_services": filtered_services,
                "service_count": len(filtered_services),
                "tenant_id": tenant_id,
                "compliance_filters": list(user_compliance),
                "discovery_timestamp": kwargs.get("timestamp", 0),
            }

        except Exception as e:
            raise NodeExecutionError(f"Service discovery failed: {str(e)}")
