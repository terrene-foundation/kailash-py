"""Enterprise tenant assignment node for multi-tenant workflows."""

import time
from typing import Any, Dict

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError


@register_node()
class TenantAssignmentNode(Node):
    """Assigns tenant context based on user authentication information.

    This node takes authenticated user information and assigns appropriate
    tenant context including permissions, tier, and compliance settings.
    """

    metadata = NodeMetadata(
        name="TenantAssignmentNode",
        description="Assigns tenant context for multi-tenant applications",
        version="1.0.0",
        tags={"enterprise", "tenant", "security"},
    )

    def __init__(self, name: str = None, **kwargs):
        self.name = name or self.__class__.__name__
        super().__init__(name=self.name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                description="Authenticated user ID",
                required=True,
            ),
            "verified": NodeParameter(
                name="verified",
                type=bool,
                description="Whether user passed MFA verification",
                required=False,
                default=False,
            ),
            "attributes": NodeParameter(
                name="attributes",
                type=dict,
                description="User attributes from SSO",
                required=False,
                default={},
            ),
        }

    def run(
        self, user_id: str, verified: bool = False, attributes: Dict = None, **kwargs
    ) -> Dict[str, Any]:
        """Assign tenant based on user information."""
        try:
            if attributes is None:
                attributes = {}

            # Extract email from user_id or attributes
            email = (
                user_id
                if "@" in user_id
                else attributes.get("email", "unknown@example.com")
            )

            # Determine tenant based on email domain
            if "@healthcare" in email:
                tenant = {
                    "id": "healthcare-corp",
                    "tier": "enterprise",
                    "compliance_zones": ["hipaa", "gdpr"],
                    "data_residency": "us-east-1",
                }
            elif "@finance" in email:
                tenant = {
                    "id": "finance-inc",
                    "tier": "premium",
                    "compliance_zones": ["sox", "pci_dss"],
                    "data_residency": "us-east-1",
                }
            else:
                tenant = {
                    "id": "default",
                    "tier": "standard",
                    "compliance_zones": ["public"],
                    "data_residency": "us-west-1",
                }

            # Create user context
            user_context = {
                "user_id": user_id,
                "tenant_id": tenant["id"],
                "permissions": ["read", "write"] if verified else ["read"],
                "session_id": f"session-{int(time.time())}",
                "compliance_zones": tenant["compliance_zones"],
                "data_residency": tenant["data_residency"],
            }

            return {
                "tenant": tenant,
                "user_context": user_context,
                "assignment_timestamp": time.time(),
            }

        except Exception as e:
            raise NodeExecutionError(f"Tenant assignment failed: {str(e)}")
