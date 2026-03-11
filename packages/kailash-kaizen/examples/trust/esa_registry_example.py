"""
ESA Registry Example.

Demonstrates how to use the ESARegistry for managing Enterprise System Agents,
including registration, discovery, health monitoring, and retrieval.
"""

import asyncio
from typing import Any, Dict, List

from kaizen.trust.authority import OrganizationalAuthorityRegistry
from kaizen.trust.chain import CapabilityType
from kaizen.trust.esa import (
    EnterpriseSystemAgent,
    ESAConfig,
    ESARegistry,
    InMemoryESAStore,
    SystemConnectionInfo,
    SystemMetadata,
    SystemType,
)
from kaizen.trust.operations import CapabilityRequest, TrustOperations
from kaizen.trust.store import PostgresTrustStore

# =========================================================================
# Mock ESA Implementations for Demo
# =========================================================================


class MockDatabaseESA(EnterpriseSystemAgent):
    """Mock Database ESA for demonstration."""

    async def discover_capabilities(self) -> List[str]:
        """Discover database capabilities."""
        # Simulate discovering tables
        return [
            "read_users",
            "write_users",
            "read_transactions",
            "write_transactions",
            "read_audit_log",
        ]

    async def execute_operation(
        self,
        operation: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """Execute database operation."""
        # Simulate database query
        if operation.startswith("read_"):
            table = operation.replace("read_", "")
            limit = parameters.get("limit", 10)
            return {
                "table": table,
                "rows": [{"id": i, "data": f"row_{i}"} for i in range(limit)],
                "count": limit,
            }
        elif operation.startswith("write_"):
            table = operation.replace("write_", "")
            return {
                "table": table,
                "rows_affected": 1,
                "success": True,
            }
        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def validate_connection(self) -> bool:
        """Validate database connection."""
        # Simulate connection check
        return True


class MockRestAPIESA(EnterpriseSystemAgent):
    """Mock REST API ESA for demonstration."""

    async def discover_capabilities(self) -> List[str]:
        """Discover API endpoints."""
        # Simulate discovering REST API endpoints
        return [
            "get_products",
            "create_product",
            "update_product",
            "delete_product",
            "search_products",
        ]

    async def execute_operation(
        self,
        operation: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """Execute API operation."""
        # Simulate API call
        if operation == "get_products":
            return {
                "products": [
                    {"id": 1, "name": "Product A", "price": 99.99},
                    {"id": 2, "name": "Product B", "price": 149.99},
                ],
                "total": 2,
            }
        elif operation == "search_products":
            query = parameters.get("query", "")
            return {
                "products": [{"id": 1, "name": f"Product matching '{query}'"}],
                "total": 1,
            }
        else:
            return {"success": True, "operation": operation}

    async def validate_connection(self) -> bool:
        """Validate API connection."""
        # Simulate connection check
        return True


# =========================================================================
# Example Functions
# =========================================================================


async def example_basic_registration():
    """Example: Basic ESA registration and retrieval."""
    print("\n" + "=" * 70)
    print("Example 1: Basic ESA Registration and Retrieval")
    print("=" * 70)

    # 1. Setup trust infrastructure
    trust_store = PostgresTrustStore()
    authority_registry = OrganizationalAuthorityRegistry()
    from kaizen.trust.operations import TrustKeyManager

    key_manager = TrustKeyManager()

    trust_ops = TrustOperations(authority_registry, key_manager, trust_store)
    await trust_ops.initialize()

    # Create organizational authority
    from kaizen.trust.crypto import generate_ed25519_keypair

    private_key, public_key = generate_ed25519_keypair()
    key_manager.register_key("org-acme-key", private_key)

    from kaizen.trust.authority import (
        AuthorityPermission,
        AuthorityType,
        OrganizationalAuthority,
    )

    authority = OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="org-acme-key",
        permissions={AuthorityPermission.CREATE_AGENTS},
    )
    await authority_registry.register_authority(authority)

    # 2. Create ESA Registry
    registry = ESARegistry(
        trust_operations=trust_ops,
        enable_health_monitoring=False,  # Disable for demo
    )
    await registry.initialize()

    # 3. Create and register a Database ESA
    print("\n→ Creating Database ESA...")
    db_esa = MockDatabaseESA(
        system_id="db-finance-001",
        system_name="Finance Database",
        trust_ops=trust_ops,
        connection_info=SystemConnectionInfo(
            endpoint="postgresql://localhost:5432/finance",
        ),
        metadata=SystemMetadata(
            system_type="postgresql",
            version="14.5",
            vendor="PostgreSQL",
            description="Finance department database",
            tags=["finance", "production"],
            compliance_tags=["SOX", "PCI-DSS"],
        ),
    )

    # Establish trust
    print("→ Establishing trust...")
    await db_esa.establish_trust(authority_id="org-acme")

    # Register in registry
    print("→ Registering in registry...")
    esa_id = await registry.register(db_esa)
    print(f"✓ Registered ESA: {esa_id}")

    # 4. Retrieve ESA
    print("\n→ Retrieving ESA from registry...")
    retrieved_esa = await registry.get(esa_id)
    print(f"✓ Retrieved: {retrieved_esa.system_name}")
    print(f"  - System ID: {retrieved_esa.system_id}")
    print(f"  - Type: {retrieved_esa.metadata.system_type}")
    print(f"  - Established: {retrieved_esa.is_established}")
    print(f"  - Capabilities: {len(retrieved_esa.capabilities)}")

    # 5. Get registry statistics
    print("\n→ Registry Statistics:")
    stats = registry.get_statistics()
    for key, value in stats.items():
        print(f"  - {key}: {value}")

    await registry.shutdown()
    print("\n✓ Example completed")


async def example_multiple_esas_by_type():
    """Example: Register multiple ESAs and retrieve by type."""
    print("\n" + "=" * 70)
    print("Example 2: Multiple ESAs and Type-Based Retrieval")
    print("=" * 70)

    # Setup (same as example 1)
    trust_store = PostgresTrustStore()
    authority_registry = OrganizationalAuthorityRegistry()
    from kaizen.trust.operations import TrustKeyManager

    key_manager = TrustKeyManager()

    trust_ops = TrustOperations(authority_registry, key_manager, trust_store)
    await trust_ops.initialize()

    from kaizen.trust.crypto import generate_ed25519_keypair

    private_key, public_key = generate_ed25519_keypair()
    key_manager.register_key("org-acme-key", private_key)

    from kaizen.trust.authority import (
        AuthorityPermission,
        AuthorityType,
        OrganizationalAuthority,
    )

    authority = OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="org-acme-key",
        permissions={AuthorityPermission.CREATE_AGENTS},
    )
    await authority_registry.register_authority(authority)

    registry = ESARegistry(
        trust_operations=trust_ops,
        enable_health_monitoring=False,
    )
    await registry.initialize()

    # 1. Register multiple databases
    print("\n→ Registering multiple Database ESAs...")
    for i, db_name in enumerate(["finance", "hr", "inventory"]):
        db_esa = MockDatabaseESA(
            system_id=f"db-{db_name}-001",
            system_name=f"{db_name.title()} Database",
            trust_ops=trust_ops,
            connection_info=SystemConnectionInfo(
                endpoint=f"postgresql://localhost:5432/{db_name}",
            ),
            metadata=SystemMetadata(
                system_type="postgresql",
                description=f"{db_name.title()} database",
            ),
        )
        await db_esa.establish_trust(authority_id="org-acme")
        esa_id = await registry.register(db_esa)
        print(f"  ✓ Registered: {esa_id}")

    # 2. Register REST APIs
    print("\n→ Registering REST API ESAs...")
    for i, api_name in enumerate(["product-api", "order-api"]):
        api_esa = MockRestAPIESA(
            system_id=f"api-{api_name}-001",
            system_name=f"{api_name.title()} API",
            trust_ops=trust_ops,
            connection_info=SystemConnectionInfo(
                endpoint=f"https://api.example.com/{api_name}",
            ),
            metadata=SystemMetadata(
                system_type="rest_api",
                description=f"{api_name.title()} REST API",
            ),
        )
        await api_esa.establish_trust(authority_id="org-acme")
        esa_id = await registry.register(api_esa)
        print(f"  ✓ Registered: {esa_id}")

    # 3. List all ESAs
    print("\n→ All registered ESAs:")
    all_esas = await registry.list_all()
    for esa in all_esas:
        print(f"  - {esa.system_id}: {esa.system_name} ({esa.metadata.system_type})")

    # 4. List by type
    print("\n→ Database ESAs only:")
    db_esas = await registry.list_by_type(SystemType.DATABASE)
    for esa in db_esas:
        print(f"  - {esa.system_id}: {esa.system_name}")

    print("\n→ REST API ESAs only:")
    api_esas = await registry.list_by_type(SystemType.REST_API)
    for esa in api_esas:
        print(f"  - {esa.system_id}: {esa.system_name}")

    # 5. Registry statistics
    print("\n→ Registry Statistics:")
    stats = registry.get_statistics()
    for key, value in stats.items():
        print(f"  - {key}: {value}")

    await registry.shutdown()
    print("\n✓ Example completed")


async def example_health_monitoring():
    """Example: ESA health monitoring."""
    print("\n" + "=" * 70)
    print("Example 3: Health Monitoring")
    print("=" * 70)

    # Setup
    trust_store = PostgresTrustStore()
    authority_registry = OrganizationalAuthorityRegistry()
    from kaizen.trust.operations import TrustKeyManager

    key_manager = TrustKeyManager()

    trust_ops = TrustOperations(authority_registry, key_manager, trust_store)
    await trust_ops.initialize()

    from kaizen.trust.crypto import generate_ed25519_keypair

    private_key, public_key = generate_ed25519_keypair()
    key_manager.register_key("org-acme-key", private_key)

    from kaizen.trust.authority import (
        AuthorityPermission,
        AuthorityType,
        OrganizationalAuthority,
    )

    authority = OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="org-acme-key",
        permissions={AuthorityPermission.CREATE_AGENTS},
    )
    await authority_registry.register_authority(authority)

    registry = ESARegistry(
        trust_operations=trust_ops,
        enable_health_monitoring=True,
        health_check_interval_seconds=60,  # 1 minute
    )
    await registry.initialize()

    # 1. Register an ESA
    print("\n→ Registering ESA...")
    db_esa = MockDatabaseESA(
        system_id="db-finance-001",
        system_name="Finance Database",
        trust_ops=trust_ops,
        connection_info=SystemConnectionInfo(
            endpoint="postgresql://localhost:5432/finance",
        ),
        metadata=SystemMetadata(
            system_type="postgresql",
        ),
    )
    await db_esa.establish_trust(authority_id="org-acme")
    esa_id = await registry.register(db_esa)
    print(f"✓ Registered: {esa_id}")

    # 2. Check health status
    print("\n→ Checking health status...")
    health = await registry.get_health_status(esa_id)
    print("✓ Health Status:")
    print(f"  - Healthy: {health['healthy']}")
    print(f"  - System ID: {health['system_id']}")
    print(f"  - Established: {health['established']}")
    print("  - Checks:")
    for check_name, check_result in health["checks"].items():
        print(f"    - {check_name}: {check_result.get('status', 'unknown')}")

    # 3. Get all health statuses
    print("\n→ All health statuses:")
    all_health = await registry.get_all_health_statuses()
    for esa_id, health_status in all_health.items():
        print(f"  - {esa_id}: {'✓' if health_status['healthy'] else '✗'}")

    await registry.shutdown()
    print("\n✓ Example completed")


async def example_unregister():
    """Example: Unregister an ESA."""
    print("\n" + "=" * 70)
    print("Example 4: ESA Unregistration")
    print("=" * 70)

    # Setup
    trust_store = PostgresTrustStore()
    authority_registry = OrganizationalAuthorityRegistry()
    from kaizen.trust.operations import TrustKeyManager

    key_manager = TrustKeyManager()

    trust_ops = TrustOperations(authority_registry, key_manager, trust_store)
    await trust_ops.initialize()

    from kaizen.trust.crypto import generate_ed25519_keypair

    private_key, public_key = generate_ed25519_keypair()
    key_manager.register_key("org-acme-key", private_key)

    from kaizen.trust.authority import (
        AuthorityPermission,
        AuthorityType,
        OrganizationalAuthority,
    )

    authority = OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="org-acme-key",
        permissions={AuthorityPermission.CREATE_AGENTS},
    )
    await authority_registry.register_authority(authority)

    registry = ESARegistry(
        trust_operations=trust_ops,
        enable_health_monitoring=False,
    )
    await registry.initialize()

    # 1. Register ESAs
    print("\n→ Registering ESAs...")
    esa_ids = []
    for i in range(3):
        db_esa = MockDatabaseESA(
            system_id=f"db-test-{i:03d}",
            system_name=f"Test Database {i}",
            trust_ops=trust_ops,
            connection_info=SystemConnectionInfo(
                endpoint=f"postgresql://localhost:5432/test_{i}",
            ),
            metadata=SystemMetadata(
                system_type="postgresql",
            ),
        )
        await db_esa.establish_trust(authority_id="org-acme")
        esa_id = await registry.register(db_esa)
        esa_ids.append(esa_id)
        print(f"  ✓ Registered: {esa_id}")

    print(f"\n→ Total registered: {len(esa_ids)}")
    stats = registry.get_statistics()
    print(f"  Registry count: {stats['total_registered']}")

    # 2. Unregister one ESA
    print(f"\n→ Unregistering {esa_ids[1]}...")
    success = await registry.unregister(esa_ids[1])
    print(f"  {'✓' if success else '✗'} Unregister result: {success}")

    # 3. Check registry after unregister
    print("\n→ Remaining ESAs:")
    remaining = await registry.list_all()
    for esa in remaining:
        print(f"  - {esa.system_id}")

    stats = registry.get_statistics()
    print(f"\n→ Registry count after unregister: {stats['total_registered']}")

    # 4. Try to get unregistered ESA (should fail)
    print("\n→ Attempting to get unregistered ESA...")
    try:
        await registry.get(esa_ids[1])
        print("  ✗ Should have raised ESANotFoundError")
    except Exception as e:
        print(f"  ✓ Expected error: {type(e).__name__}")

    await registry.shutdown()
    print("\n✓ Example completed")


# =========================================================================
# Main
# =========================================================================


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("ESA Registry Examples")
    print("=" * 70)

    await example_basic_registration()
    await example_multiple_esas_by_type()
    await example_health_monitoring()
    await example_unregister()

    print("\n" + "=" * 70)
    print("All examples completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
