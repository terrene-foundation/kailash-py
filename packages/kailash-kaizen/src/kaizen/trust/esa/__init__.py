"""
Enterprise System Agent (ESA) Module.

ESAs are specialized proxy agents that bridge AI agents with legacy enterprise systems
(databases, REST APIs, SOAP services, etc.). They inherit trust from organizational
authority and enable secure, auditable access to enterprise resources.

Key Concepts:
- Trust Inheritance: ESAs are established by SYSTEM authority type
- Capability Discovery: ESAs automatically discover capabilities from system metadata
- Request Proxying: ESAs validate, proxy, and audit all requests
- Capability Delegation: ESAs delegate capabilities to other agents with constraints

Architecture:
- EnterpriseSystemAgent: Base class for all ESA implementations
- Capability Discovery: Abstract method for subclasses to implement
- Trust Operations: Full integration with TrustOperations (ESTABLISH, VERIFY, AUDIT)
- Audit Trail: Complete audit logging for all proxied requests

Example:
    from kaizen.trust.esa import EnterpriseSystemAgent, SystemMetadata
    from kaizen.trust import TrustOperations, CapabilityType

    class DatabaseESA(EnterpriseSystemAgent):
        async def discover_capabilities(self) -> List[str]:
            # Discover tables and operations
            tables = await self.db.get_tables()
            return [f"read_{table}" for table in tables]

    # Initialize ESA
    esa = DatabaseESA(
        system_id="db-finance-001",
        system_name="Finance Database",
        trust_ops=trust_ops,
        metadata=SystemMetadata(
            system_type="postgresql",
            endpoint="postgresql://...",
        )
    )

    # Establish trust (inherits from organizational authority)
    await esa.establish_trust(authority_id="org-acme")

    # Execute operation with trust verification
    result = await esa.execute(
        operation="read_transactions",
        parameters={"limit": 100},
        requesting_agent_id="agent-001",
    )

    # Delegate capability to another agent
    await esa.delegate_capability(
        capability="read_transactions",
        delegatee_id="agent-002",
        task_id="task-001",
        constraints=["read_only", "limit:100"],
    )
"""

from kaizen.trust.esa.api import APIESA, ESAResult, RateLimitConfig
from kaizen.trust.esa.base import (
    CapabilityMetadata,
    EnterpriseSystemAgent,
    ESAConfig,
    OperationRequest,
    OperationResult,
    SystemConnectionInfo,
    SystemMetadata,
)
from kaizen.trust.esa.database import DatabaseESA, DatabaseType, QueryParseResult
from kaizen.trust.esa.discovery import (
    APICapabilityDiscoverer,
    CapabilityDiscoverer,
    DatabaseCapabilityDiscoverer,
    DiscoveryCache,
    DiscoveryResult,
    DiscoveryStatus,
)
from kaizen.trust.esa.exceptions import (
    ESAAuthorizationError,
    ESACapabilityNotFoundError,
    ESAConnectionError,
    ESADelegationError,
    ESAError,
    ESANotEstablishedError,
    ESAOperationError,
)
from kaizen.trust.esa.registry import (
    ESAAlreadyRegisteredError,
    ESANotFoundError,
    ESARegistration,
    ESARegistry,
    ESARegistryError,
    ESAStore,
    InMemoryESAStore,
    SystemType,
)

__all__ = [
    # Base ESA
    "EnterpriseSystemAgent",
    "SystemMetadata",
    "SystemConnectionInfo",
    "CapabilityMetadata",
    "OperationRequest",
    "OperationResult",
    "ESAConfig",
    # Exceptions
    "ESAError",
    "ESANotEstablishedError",
    "ESACapabilityNotFoundError",
    "ESAOperationError",
    "ESAConnectionError",
    "ESAAuthorizationError",
    "ESADelegationError",
    # Registry
    "ESARegistry",
    "ESAStore",
    "InMemoryESAStore",
    "ESARegistration",
    "SystemType",
    "ESARegistryError",
    "ESAAlreadyRegisteredError",
    "ESANotFoundError",
    # API ESA
    "APIESA",
    "ESAResult",
    "RateLimitConfig",
    # Discovery
    "CapabilityDiscoverer",
    "DatabaseCapabilityDiscoverer",
    "APICapabilityDiscoverer",
    "DiscoveryResult",
    "DiscoveryStatus",
    "DiscoveryCache",
    # Database ESA
    "DatabaseESA",
    "DatabaseType",
    "QueryParseResult",
]
