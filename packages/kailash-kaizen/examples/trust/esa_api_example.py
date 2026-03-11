"""
Example: Using APIESA for REST API Integration.

This example demonstrates how to use the APIESA (REST API Enterprise System Agent)
to provide trust-aware access to REST APIs with:
- OpenAPI spec parsing for capability discovery
- Rate limiting enforcement
- Request/response audit logging
- Full HTTP method support (GET, POST, PUT, DELETE, PATCH)
"""

import asyncio
from datetime import datetime, timedelta

from kaizen.trust.authority import OrganizationalAuthorityRegistry
from kaizen.trust.chain import CapabilityType
from kaizen.trust.esa import APIESA, ESAResult, RateLimitConfig, SystemMetadata
from kaizen.trust.operations import CapabilityRequest, TrustOperations
from kaizen.trust.store import PostgresTrustStore


async def example_basic_usage():
    """Example: Basic APIESA usage with generic capabilities."""

    # Setup trust infrastructure
    store = PostgresTrustStore()
    registry = OrganizationalAuthorityRegistry()
    key_manager = TrustKeyManager()
    trust_ops = TrustOperations(registry, key_manager, store)
    await trust_ops.initialize()

    # Register organization authority
    from kaizen.trust.crypto import generate_keypair

    private_key, public_key = generate_keypair()
    key_manager.register_key("org-acme-key", private_key)

    authority = OrganizationalAuthority(
        id="org-acme",
        name="Acme Corporation",
        public_key=public_key,
        signing_key_id="org-acme-key",
        permissions=[AuthorityPermission.CREATE_AGENTS],
    )
    await registry.register_authority(authority)

    # Create APIESA for a REST API
    esa = APIESA(
        system_id="api-crm-001",
        base_url="https://api.crm.example.com",
        trust_ops=trust_ops,
        authority_id="org-acme",
        auth_headers={"Authorization": "Bearer YOUR_API_TOKEN"},
        rate_limit_config=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
        ),
        metadata=SystemMetadata(
            system_type="rest_api",
            description="CRM API for customer data",
            tags=["crm", "customers"],
        ),
    )

    # Establish trust (inherits from organizational authority)
    await esa.establish_trust(authority_id="org-acme")

    print(f"✓ ESA established with {len(esa.capabilities)} capabilities")
    print(f"  Capabilities: {', '.join(esa.capabilities[:3])}...")

    # Now an agent can use the ESA (assuming agent-001 has been established)
    # Note: This would normally be done after agent-001 trust is established

    # Execute GET request
    result = await esa.get("/users", params={"limit": 10})
    print(f"\n✓ GET request completed: {result.status_code}")
    print(f"  Duration: {result.duration_ms}ms")
    print(f"  Success: {result.success}")

    # Execute POST request
    result = await esa.post(
        "/users", data={"name": "John Doe", "email": "john@example.com"}
    )
    print(f"\n✓ POST request completed: {result.status_code}")

    # Get rate limit status
    rate_status = esa.get_rate_limit_status()
    print("\n✓ Rate limit status:")
    print(
        f"  Per second: {rate_status['per_second']['current']}/{rate_status['per_second']['limit']}"
    )
    print(
        f"  Per minute: {rate_status['per_minute']['current']}/{rate_status['per_minute']['limit']}"
    )

    # Get request statistics
    stats = esa.get_request_statistics()
    print("\n✓ Request statistics:")
    print(f"  Total requests: {stats['total_requests']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")
    print(f"  Average duration: {stats['average_duration_ms']}ms")

    # Cleanup
    await esa.cleanup()


async def example_openapi_spec():
    """Example: APIESA with OpenAPI spec for capability discovery."""

    # OpenAPI spec example
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {"title": "CRM API", "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {
                    "summary": "List users",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Maximum number of users to return",
                        }
                    ],
                    "responses": {"200": {"description": "List of users"}},
                },
                "post": {
                    "summary": "Create user",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "User created"}},
                },
            },
            "/users/{id}": {
                "get": {
                    "summary": "Get user by ID",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "User details"}},
                },
                "put": {
                    "summary": "Update user",
                    "responses": {"200": {"description": "User updated"}},
                },
                "delete": {
                    "summary": "Delete user",
                    "responses": {"204": {"description": "User deleted"}},
                },
            },
        },
    }

    # Create APIESA with OpenAPI spec
    esa = APIESA(
        system_id="api-crm-001",
        base_url="https://api.crm.example.com",
        trust_ops=trust_ops,
        authority_id="org-acme",
        openapi_spec=openapi_spec,
    )

    # Establish trust - capabilities will be discovered from spec
    await esa.establish_trust(authority_id="org-acme")

    print("✓ Discovered capabilities from OpenAPI spec:")
    for capability in esa.capabilities:
        print(f"  - {capability}")

        # Get capability metadata
        cap_meta = esa.get_capability_metadata(capability)
        if cap_meta:
            print(f"    Description: {cap_meta.description}")
            print(f"    Type: {cap_meta.capability_type.value}")

    await esa.cleanup()


async def example_with_agent_integration():
    """Example: Full integration with agent trust verification."""

    # Setup (assuming infrastructure is initialized)
    esa = APIESA(
        system_id="api-crm-001",
        base_url="https://api.crm.example.com",
        trust_ops=trust_ops,
        authority_id="org-acme",
    )

    await esa.establish_trust(authority_id="org-acme")

    # Create an agent with capabilities
    await trust_ops.establish(
        agent_id="agent-001",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="get_users",
                capability_type=CapabilityType.ACTION,
                constraints=["read_only"],
            )
        ],
    )

    # Agent executes operation through ESA (with trust verification)
    result = await esa.execute(
        operation="get_users",
        parameters={
            "path": "/users",
            "params": {"limit": 10},
        },
        requesting_agent_id="agent-001",
    )

    print("✓ Operation completed with trust verification")
    print(f"  Success: {result.success}")
    print(f"  Audit anchor: {result.audit_anchor_id}")
    print(f"  Duration: {result.duration_ms}ms")

    # Delegate capability to another agent
    delegation_id = await esa.delegate_capability(
        capability="get_users",
        delegatee_id="agent-002",
        task_id="task-001",
        additional_constraints=["limit:50"],  # Tighter constraint
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )

    print("\n✓ Capability delegated to agent-002")
    print(f"  Delegation ID: {delegation_id}")

    await esa.cleanup()


async def example_rate_limiting():
    """Example: Rate limiting enforcement."""

    esa = APIESA(
        system_id="api-crm-001",
        base_url="https://api.crm.example.com",
        trust_ops=trust_ops,
        authority_id="org-acme",
        rate_limit_config=RateLimitConfig(
            requests_per_second=2,  # Very low for demonstration
            requests_per_minute=10,
            requests_per_hour=100,
        ),
    )

    await esa.establish_trust(authority_id="org-acme")

    # Make rapid requests - rate limiter will automatically throttle
    print("Making 5 rapid requests (rate limit: 2/second)...")

    for i in range(5):
        start = datetime.utcnow()
        result = await esa.get("/users", params={"limit": 1})
        elapsed = (datetime.utcnow() - start).total_seconds()

        print(f"  Request {i+1}: {result.status_code} (waited {elapsed:.2f}s)")

    # Get final rate limit status
    rate_status = esa.get_rate_limit_status()
    print("\n✓ Final rate limit status:")
    print(
        f"  Per second: {rate_status['per_second']['current']}/{rate_status['per_second']['limit']}"
    )

    await esa.cleanup()


async def example_request_logging():
    """Example: Request/response audit logging."""

    esa = APIESA(
        system_id="api-crm-001",
        base_url="https://api.crm.example.com",
        trust_ops=trust_ops,
        authority_id="org-acme",
    )

    await esa.establish_trust(authority_id="org-acme")

    # Make several requests
    await esa.get("/users")
    await esa.post("/users", data={"name": "Alice"})
    await esa.get("/users/123")
    await esa.put("/users/123", data={"name": "Alice Updated"})
    await esa.delete("/users/123")

    # Get request log
    log_entries = esa.get_request_log(limit=10)

    print(f"✓ Request log ({len(log_entries)} entries):")
    for entry in log_entries:
        print(f"  [{entry['timestamp']}] {entry['method']} {entry['path']}")
        print(f"    Status: {entry['status_code']}, Duration: {entry['duration_ms']}ms")

    # Get statistics
    stats = esa.get_request_statistics()
    print("\n✓ Statistics:")
    print(f"  Total: {stats['total_requests']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")
    print(f"  Methods: {stats['methods']}")
    print(f"  Status codes: {stats['status_codes']}")

    await esa.cleanup()


async def example_health_check():
    """Example: ESA health check."""

    esa = APIESA(
        system_id="api-crm-001",
        base_url="https://api.crm.example.com",
        trust_ops=trust_ops,
        authority_id="org-acme",
    )

    await esa.establish_trust(authority_id="org-acme")

    # Perform health check
    health = await esa.health_check()

    print("✓ Health check results:")
    print(f"  Overall healthy: {health['healthy']}")
    print(f"  Established: {health['established']}")
    print("  Checks:")
    for check_name, check_result in health["checks"].items():
        print(f"    - {check_name}: {check_result['status']}")

    print("\n✓ Statistics:")
    for key, value in health["statistics"].items():
        print(f"    {key}: {value}")

    await esa.cleanup()


if __name__ == "__main__":
    print("=" * 60)
    print("APIESA Examples")
    print("=" * 60)

    # Run examples
    # Note: These examples require a running infrastructure setup
    # Uncomment to run specific examples:

    # asyncio.run(example_basic_usage())
    # asyncio.run(example_openapi_spec())
    # asyncio.run(example_with_agent_integration())
    # asyncio.run(example_rate_limiting())
    # asyncio.run(example_request_logging())
    # asyncio.run(example_health_check())

    print("\n✓ All examples defined (uncomment to run)")
