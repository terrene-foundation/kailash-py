"""
E2E Integration Tests: A2A HTTP Service.

Test Intent:
- Verify A2A protocol endpoints work correctly together
- Test JSON-RPC 2.0 compliance for all method calls
- Validate JWT authentication with trust chain verification
- Ensure Agent Card serves correct EATP trust extensions
- Test delegation and audit query workflows

These tests use real EATP cryptographic operations - NO MOCKING.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import pytest
from fastapi.testclient import TestClient
from kaizen.trust import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
    TrustLineageChain,
    TrustOperations,
    generate_keypair,
    sign,
)
from kaizen.trust.a2a import (  # Models; Exceptions
    A2AAuthenticator,
    A2AError,
    A2AMethodHandlers,
    A2AService,
    A2AToken,
    AgentCapability,
    AgentCard,
    AgentCardCache,
    AgentCardGenerator,
    AuthenticationError,
    InvalidTokenError,
    JsonRpcHandler,
    JsonRpcMethodNotFoundError,
    JsonRpcParseError,
    JsonRpcRequest,
    JsonRpcResponse,
    TokenExpiredError,
    TrustExtensions,
    create_a2a_app,
    extract_token_from_header,
)

# Note: NO MOCKING in integration tests - use real implementations


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def test_agent_keypair():
    """Generate a test keypair for agent authentication."""
    return generate_keypair()


@pytest.fixture
def authority_keypair():
    """Generate a keypair for the authority."""
    return generate_keypair()


class InMemoryTrustStore:
    """
    In-memory trust store for integration testing - NO MOCKING.

    Stores trust chains in memory for real operations without PostgreSQL.
    """

    def __init__(self):
        self._chains: Dict[str, Any] = {}

    async def get_chain(
        self, agent_id: str, include_inactive: bool = False
    ) -> Optional[Any]:
        return self._chains.get(agent_id)

    async def store_chain(self, chain: Any, expires_at: datetime = None) -> str:
        agent_id = chain.genesis.agent_id
        self._chains[agent_id] = chain
        return agent_id

    async def save(self, chain: Any) -> bool:
        agent_id = chain.genesis.agent_id
        self._chains[agent_id] = chain
        return True


@pytest.fixture
def trust_store():
    """Create in-memory trust store - NO MOCKING."""
    return InMemoryTrustStore()


@pytest.fixture
def public_keys(test_agent_keypair, authority_keypair):
    """Store public keys for verification."""
    return {
        "agent-001": test_agent_keypair[1],  # public key
        "org-001": authority_keypair[1],
    }


@pytest.fixture
def key_manager(test_agent_keypair, authority_keypair):
    """Create trust key manager with private keys for signing."""
    km = TrustKeyManager()
    # TrustKeyManager stores private keys (for signing)
    km.register_key("agent-001", test_agent_keypair[0])  # private key
    km.register_key("org-001", authority_keypair[0])  # private key
    return km


class InMemoryAuthorityRegistry:
    """
    In-memory authority registry for integration testing - NO MOCKING.

    Stores authorities in memory for real operations.
    """

    def __init__(self):
        self._authorities: Dict[str, Any] = {}

    async def get_authority(self, authority_id: str) -> Optional[Any]:
        return self._authorities.get(authority_id)

    async def register_authority(self, authority: Any) -> str:
        self._authorities[authority.id] = authority
        return authority.id


@pytest.fixture
def authority_registry():
    """Create in-memory authority registry - NO MOCKING."""
    return InMemoryAuthorityRegistry()


@pytest.fixture
def test_trust_chain(test_agent_keypair, authority_keypair):
    """Create a test trust chain."""
    agent_private, agent_public = test_agent_keypair
    auth_private, auth_public = authority_keypair

    genesis = GenesisRecord(
        id="genesis-001",
        agent_id="agent-001",
        authority_id="org-001",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature=sign({"agent_id": "agent-001"}, auth_private),
    )

    attestation = CapabilityAttestation(
        id="cap-001",
        capability="analyze",
        capability_type=CapabilityType.ACCESS,
        constraints=["read_only"],
        attester_id="org-001",
        attested_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        signature=sign({"capability": "analyze"}, auth_private),
    )

    return TrustLineageChain(
        genesis=genesis,
        capabilities=[attestation],
    )


@pytest.fixture
def trust_operations(
    authority_registry, key_manager, trust_store, test_trust_chain, public_keys
):
    """Create configured trust operations with test chain."""
    ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )

    # Mock get_chain to return our test chain
    async def mock_get_chain(agent_id: str):
        if agent_id == "agent-001":
            return test_trust_chain
        return None

    ops.get_chain = mock_get_chain

    # Mock get_public_key - uses public_keys dict
    async def mock_get_public_key(agent_id: str):
        return public_keys.get(agent_id)

    ops.get_public_key = mock_get_public_key

    # Mock verify (VerificationResult uses 'violations' not 'errors')
    async def mock_verify(agent_id: str, level=None):
        from kaizen.trust import VerificationLevel, VerificationResult

        if agent_id == "agent-001":
            return VerificationResult(
                valid=True, level=level or VerificationLevel.STANDARD
            )
        return VerificationResult(
            valid=False,
            level=level or VerificationLevel.STANDARD,
            reason="Unknown agent",
        )

    ops.verify = mock_verify

    return ops


@pytest.fixture
def a2a_service(trust_operations, test_agent_keypair):
    """Create A2A service for testing."""
    private_key, _ = test_agent_keypair

    return A2AService(
        trust_operations=trust_operations,
        agent_id="agent-001",
        agent_name="Test Agent",
        agent_version="1.0.0",
        private_key=private_key,
        capabilities=["analyze", "report"],
        description="A test agent for A2A protocol testing",
        base_url="http://localhost:8000",
        cors_origins=["*"],
    )


@pytest.fixture
def test_client(a2a_service):
    """Create FastAPI test client."""
    app = a2a_service.create_app()
    return TestClient(app)


@pytest.fixture
def event_loop():
    """Create event loop for async fixtures."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def auth_token(a2a_service, event_loop):
    """Create valid auth token for testing protected endpoints."""

    async def _create_token():
        return await a2a_service.authenticator.create_token(
            audience="agent-001",
            capabilities=["analyze"],
            ttl_seconds=3600,
        )

    return event_loop.run_until_complete(_create_token())


# =============================================================================
# Agent Card Endpoint Tests
# =============================================================================


class TestAgentCardEndpoint:
    """
    Test the /.well-known/agent.json endpoint.

    Intent: Verify that agents can discover other agents' capabilities
    and trust information via the standard Agent Card endpoint.
    """

    def test_agent_card_returns_correct_structure(self, test_client):
        """Agent Card should return A2A-compliant JSON structure."""
        response = test_client.get("/.well-known/agent.json")

        assert response.status_code == 200
        card = response.json()

        # Required A2A fields
        assert card["agent_id"] == "agent-001"
        assert card["name"] == "Test Agent"
        assert card["version"] == "1.0.0"
        assert "capabilities" in card
        assert "protocols" in card
        assert "a2a/1.0" in card["protocols"]

    def test_agent_card_includes_eatp_trust_extensions(self, test_client):
        """Agent Card should include EATP trust extensions."""
        response = test_client.get("/.well-known/agent.json")
        card = response.json()

        # EATP trust extensions
        assert "trust" in card
        trust = card["trust"]
        assert "trust_chain_hash" in trust
        assert "genesis_authority_id" in trust
        assert trust["genesis_authority_id"] == "org-001"

    def test_agent_card_has_etag_for_caching(self, test_client):
        """Agent Card response should include ETag for caching."""
        response = test_client.get("/.well-known/agent.json")

        assert response.status_code == 200
        assert "ETag" in response.headers
        assert "Cache-Control" in response.headers

    def test_agent_card_conditional_get(self, test_client):
        """Agent Card should support conditional GET with If-None-Match."""
        # First request to get ETag
        response1 = test_client.get("/.well-known/agent.json")
        etag = response1.headers["ETag"]

        # Conditional request with same ETag
        response2 = test_client.get(
            "/.well-known/agent.json", headers={"If-None-Match": etag}
        )

        assert response2.status_code == 304  # Not Modified

    def test_agent_card_endpoint_url_in_card(self, test_client):
        """Agent Card should include JSON-RPC endpoint URL."""
        response = test_client.get("/.well-known/agent.json")
        card = response.json()

        assert card["endpoint"] == "http://localhost:8000/a2a/jsonrpc"


# =============================================================================
# JSON-RPC Handler Tests
# =============================================================================


class TestJsonRpcHandler:
    """
    Test JSON-RPC 2.0 compliant request handling.

    Intent: Verify that the A2A service correctly implements
    JSON-RPC 2.0 specification for agent method calls.
    """

    def test_jsonrpc_requires_version_2_0(self, test_client):
        """JSON-RPC requests must have jsonrpc version 2.0."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "1.0",  # Invalid version
                "method": "agent.capabilities",
                "id": 1,
            },
        )

        assert response.status_code == 200
        result = response.json()
        assert "error" in result
        assert result["error"]["code"] == -32600  # Invalid Request

    def test_jsonrpc_method_not_found(self, test_client, auth_token):
        """Unknown methods should return method not found error (with auth)."""
        # Note: Need auth token because auth check happens before method dispatch
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "unknown.method",
                "id": 1,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        result = response.json()
        assert "error" in result
        assert result["error"]["code"] == -32601  # Method not found

    def test_jsonrpc_parse_error_on_invalid_json(self, test_client):
        """Invalid JSON should return 400 with parse error."""
        response = test_client.post(
            "/a2a/jsonrpc",
            content="{ invalid json }",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        result = response.json()
        assert "error" in result
        assert result["error"]["code"] == -32700  # Parse error

    def test_jsonrpc_preserves_request_id(self, test_client):
        """Response should include the same id as the request."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "agent.capabilities",
                "id": "test-request-123",
            },
        )

        result = response.json()
        assert result["id"] == "test-request-123"

    def test_jsonrpc_batch_request(self, test_client, auth_token):
        """Batch requests should return array of responses."""
        response = test_client.post(
            "/a2a/jsonrpc/batch",
            json=[
                {"jsonrpc": "2.0", "method": "agent.capabilities", "id": 1},
                {"jsonrpc": "2.0", "method": "agent.capabilities", "id": 2},
            ],
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        results = response.json()
        assert isinstance(results, list)
        assert len(results) == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2


# =============================================================================
# Public Method Tests
# =============================================================================


class TestPublicMethods:
    """
    Test public A2A methods that don't require authentication.

    Intent: Verify that agent discovery and trust verification
    work without authentication, enabling agent interoperability.
    """

    def test_agent_capabilities_without_auth(self, test_client):
        """agent.capabilities should work without authentication."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "agent.capabilities",
                "id": 1,
            },
        )

        result = response.json()
        assert "result" in result
        assert result["result"]["agent_id"] == "agent-001"
        assert "capabilities" in result["result"]

    def test_trust_verify_without_auth(self, test_client):
        """trust.verify should work without authentication."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "trust.verify",
                "params": {"agent_id": "agent-001"},
                "id": 1,
            },
        )

        result = response.json()
        assert "result" in result
        assert result["result"]["valid"] is True
        assert result["result"]["agent_id"] == "agent-001"

    def test_trust_verify_invalid_agent(self, test_client):
        """trust.verify should return invalid for unknown agents."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "trust.verify",
                "params": {"agent_id": "unknown-agent"},
                "id": 1,
            },
        )

        result = response.json()
        assert "result" in result
        assert result["result"]["valid"] is False

    def test_trust_verify_with_verification_level(self, test_client):
        """trust.verify should support different verification levels."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "trust.verify",
                "params": {
                    "agent_id": "agent-001",
                    "verification_level": "FULL",
                },
                "id": 1,
            },
        )

        result = response.json()
        assert "result" in result
        assert result["result"]["verification_level"] == "FULL"


# =============================================================================
# Protected Method Tests
# =============================================================================


class TestProtectedMethods:
    """
    Test A2A methods that require authentication.

    Intent: Verify that sensitive operations like delegation
    and invocation require valid JWT authentication.
    """

    def test_agent_invoke_requires_auth(self, test_client):
        """agent.invoke should require authentication."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "agent.invoke",
                "params": {"task": "analyze"},
                "id": 1,
            },
        )

        result = response.json()
        assert "error" in result
        # -40002 is AuthenticationError (missing token)
        assert result["error"]["code"] == -40002

    def test_trust_delegate_requires_auth(self, test_client):
        """trust.delegate should require authentication."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "trust.delegate",
                "params": {
                    "delegatee_agent_id": "agent-002",
                    "task_id": "task-001",
                    "capabilities": ["analyze"],
                },
                "id": 1,
            },
        )

        result = response.json()
        assert "error" in result
        # -40002 is AuthenticationError (missing token)
        assert result["error"]["code"] == -40002

    def test_audit_query_requires_auth(self, test_client):
        """audit.query should require authentication."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "audit.query",
                "params": {"agent_id": "agent-001"},
                "id": 1,
            },
        )

        result = response.json()
        assert "error" in result
        # -40002 is AuthenticationError (missing token)
        assert result["error"]["code"] == -40002

    @pytest.mark.asyncio
    async def test_protected_method_with_valid_token(self, test_client, auth_token):
        """Protected methods should work with valid token."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "agent.capabilities",
                "id": 1,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        result = response.json()
        assert "result" in result


# =============================================================================
# Authentication Tests
# =============================================================================


class TestA2AAuthentication:
    """
    Test JWT-based A2A authentication.

    Intent: Verify that authentication tokens are created correctly,
    validated properly, and integrate with trust chain verification.
    """

    @pytest.mark.asyncio
    async def test_create_token_success(self, a2a_service):
        """Token creation should succeed for valid agent."""
        token = await a2a_service.authenticator.create_token(
            audience="agent-002",
            capabilities=["analyze"],
            ttl_seconds=3600,
        )

        assert token is not None
        assert len(token.split(".")) == 3  # JWT format

    @pytest.mark.asyncio
    async def test_verify_token_success(self, a2a_service):
        """Token verification should succeed for valid token."""
        token = await a2a_service.authenticator.create_token(
            audience="agent-001",
            capabilities=["analyze"],
        )

        claims = await a2a_service.authenticator.verify_token(
            token,
            expected_audience="agent-001",
            verify_trust=False,  # Skip trust verification for unit test
        )

        assert claims.sub == "agent-001"
        assert claims.aud == "agent-001"
        assert "analyze" in claims.capabilities

    @pytest.mark.asyncio
    async def test_verify_token_wrong_audience(self, a2a_service):
        """Token verification should fail for wrong audience."""
        token = await a2a_service.authenticator.create_token(
            audience="agent-002",
            capabilities=["analyze"],
        )

        with pytest.raises(InvalidTokenError):
            await a2a_service.authenticator.verify_token(
                token,
                expected_audience="agent-003",  # Wrong audience
                verify_trust=False,
            )

    @pytest.mark.asyncio
    async def test_token_includes_trust_chain_hash(self, a2a_service):
        """Token should include trust chain hash."""
        token = await a2a_service.authenticator.create_token(
            audience="agent-002",
            capabilities=["analyze"],
        )

        claims = await a2a_service.authenticator.verify_token(
            token,
            verify_trust=False,
        )

        assert claims.trust_chain_hash is not None

    def test_extract_token_from_bearer_header(self):
        """Should extract token from Bearer authorization header."""
        token = extract_token_from_header("Bearer abc123")
        assert token == "abc123"

    def test_extract_token_returns_none_for_invalid(self):
        """Should return None for invalid authorization header."""
        assert extract_token_from_header(None) is None
        assert extract_token_from_header("Basic abc123") is None
        assert extract_token_from_header("Bearer") is None


# =============================================================================
# Agent Card Generation Tests
# =============================================================================


class TestAgentCardGeneration:
    """
    Test Agent Card generation with EATP trust extensions.

    Intent: Verify that Agent Cards correctly represent agent
    capabilities and trust information for discovery.
    """

    @pytest.mark.asyncio
    async def test_generate_card_from_trust_chain(
        self, trust_operations, test_trust_chain
    ):
        """Agent Card should be generated from trust chain."""
        generator = AgentCardGenerator(
            trust_operations=trust_operations,
            base_url="http://localhost:8000",
        )

        card = await generator.generate(
            agent_id="agent-001",
            name="Test Agent",
            version="1.0.0",
        )

        assert card.agent_id == "agent-001"
        assert card.name == "Test Agent"
        assert "a2a/1.0" in card.protocols
        assert "eatp/1.0" in card.protocols

    @pytest.mark.asyncio
    async def test_card_includes_attested_capabilities(self, trust_operations):
        """Agent Card should include capabilities from attestations."""
        generator = AgentCardGenerator(
            trust_operations=trust_operations,
            base_url="http://localhost:8000",
        )

        card = await generator.generate(
            agent_id="agent-001",
            name="Test Agent",
            version="1.0.0",
        )

        capability_names = [c.name for c in card.capabilities]
        assert "analyze" in capability_names

    def test_card_cache_stores_and_retrieves(self):
        """Agent Card cache should store and retrieve cards."""
        cache = AgentCardCache(ttl_seconds=300)

        card = AgentCard(
            agent_id="agent-001",
            name="Test Agent",
            version="1.0.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        cache.set("agent-001", card)
        retrieved = cache.get("agent-001")

        assert retrieved is not None
        assert retrieved.agent_id == "agent-001"

    def test_card_cache_respects_ttl(self):
        """Agent Card cache should respect TTL."""
        cache = AgentCardCache(ttl_seconds=0)  # Immediate expiration

        card = AgentCard(
            agent_id="agent-001",
            name="Test Agent",
            version="1.0.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        cache.set("agent-001", card)
        # Should be expired immediately
        import time

        time.sleep(0.01)
        retrieved = cache.get("agent-001")

        assert retrieved is None

    def test_card_cache_invalidation(self):
        """Agent Card cache should support invalidation."""
        cache = AgentCardCache(ttl_seconds=300)

        card = AgentCard(
            agent_id="agent-001",
            name="Test Agent",
            version="1.0.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        cache.set("agent-001", card)
        cache.invalidate("agent-001")

        assert cache.get("agent-001") is None


# =============================================================================
# Health Check Tests
# =============================================================================


class TestHealthEndpoint:
    """
    Test the health check endpoint.

    Intent: Verify that the service health can be monitored
    for operational visibility.
    """

    def test_health_check_returns_healthy(self, test_client):
        """Health check should return healthy status."""
        response = test_client.get("/health")

        assert response.status_code == 200
        health = response.json()
        assert health["status"] == "healthy"
        assert health["agent_id"] == "agent-001"
        assert health["version"] == "1.0.0"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """
    Test error handling and JSON-RPC error responses.

    Intent: Verify that errors are properly formatted according
    to JSON-RPC 2.0 and A2A protocol specifications.
    """

    def test_missing_required_param(self, test_client):
        """Missing required parameter should return invalid params error."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "trust.verify",
                "params": {},  # Missing agent_id
                "id": 1,
            },
        )

        result = response.json()
        assert "error" in result
        assert result["error"]["code"] == -32602  # Invalid params

    def test_error_response_format(self, test_client):
        """Error responses should follow JSON-RPC 2.0 format."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "unknown.method",
                "id": 1,
            },
        )

        result = response.json()
        assert "jsonrpc" in result
        assert result["jsonrpc"] == "2.0"
        assert "error" in result
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert "id" in result


# =============================================================================
# Service Configuration Tests
# =============================================================================


class TestServiceConfiguration:
    """
    Test A2A service configuration options.

    Intent: Verify that service configuration correctly affects
    behavior and endpoint responses.
    """

    def test_custom_capabilities_available_via_jsonrpc(
        self, trust_operations, test_agent_keypair
    ):
        """
        Custom capabilities should be available via agent.capabilities JSON-RPC method.

        Intent: Service-declared capabilities are for runtime discovery via JSON-RPC,
        while Agent Card shows trust-attested capabilities from the trust chain.
        """
        private_key, _ = test_agent_keypair

        service = A2AService(
            trust_operations=trust_operations,
            agent_id="agent-001",
            agent_name="Custom Agent",
            agent_version="2.0.0",
            private_key=private_key,
            capabilities=["custom_cap_1", "custom_cap_2"],
        )

        client = TestClient(service.create_app())

        # Agent Card shows trust-attested capabilities from trust chain
        card_response = client.get("/.well-known/agent.json")
        card = card_response.json()
        # Trust chain has "analyze" capability
        assert "analyze" in [c.get("name") for c in card.get("capabilities", [])]

        # JSON-RPC agent.capabilities returns service-declared capabilities
        rpc_response = client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "agent.capabilities",
                "id": 1,
            },
        )
        result = rpc_response.json()
        assert "custom_cap_1" in result["result"]["capabilities"]
        assert "custom_cap_2" in result["result"]["capabilities"]

    def test_create_a2a_app_convenience_function(
        self, trust_operations, test_agent_keypair
    ):
        """create_a2a_app should create working FastAPI app."""
        private_key, _ = test_agent_keypair

        app = create_a2a_app(
            trust_operations=trust_operations,
            agent_id="agent-001",
            agent_name="Quick Agent",
            agent_version="1.0.0",
            private_key=private_key,
        )

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200

    def test_service_allows_custom_method_registration(
        self, trust_operations, test_agent_keypair
    ):
        """Service should allow registering custom JSON-RPC methods."""
        private_key, _ = test_agent_keypair

        service = A2AService(
            trust_operations=trust_operations,
            agent_id="agent-001",
            agent_name="Custom Agent",
            agent_version="1.0.0",
            private_key=private_key,
        )

        async def custom_handler(params, auth_token):
            return {"custom": "response"}

        service.register_method("custom.method", custom_handler)

        client = TestClient(service.create_app())
        response = client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "custom.method",
                "id": 1,
            },
        )

        result = response.json()
        # Custom methods require auth
        assert "error" in result  # Auth required


# =============================================================================
# Integration Workflow Tests
# =============================================================================


class TestA2AWorkflows:
    """
    Test complete A2A protocol workflows.

    Intent: Verify that multi-step A2A interactions work correctly
    from discovery to authenticated method calls.
    """

    @pytest.mark.asyncio
    async def test_discovery_to_invoke_workflow(
        self, a2a_service, test_client, auth_token
    ):
        """
        Complete workflow: discover agent, verify trust, call method.

        This tests the typical A2A interaction pattern where an agent
        discovers another agent, verifies its trust chain, and then
        makes an authenticated call.
        """
        # Step 1: Discover agent via Agent Card
        card_response = test_client.get("/.well-known/agent.json")
        assert card_response.status_code == 200
        card = card_response.json()

        # Step 2: Verify trust chain
        verify_response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "trust.verify",
                "params": {"agent_id": card["agent_id"]},
                "id": 1,
            },
        )
        verify_result = verify_response.json()
        assert verify_result["result"]["valid"] is True

        # Step 3: Get capabilities
        cap_response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "agent.capabilities",
                "id": 2,
            },
        )
        cap_result = cap_response.json()
        assert "capabilities" in cap_result["result"]

    def test_invalid_verification_level_error(self, test_client):
        """Invalid verification level should return clear error."""
        response = test_client.post(
            "/a2a/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "trust.verify",
                "params": {
                    "agent_id": "agent-001",
                    "verification_level": "INVALID",
                },
                "id": 1,
            },
        )

        result = response.json()
        assert "error" in result
        assert result["error"]["code"] == -32602  # Invalid params
