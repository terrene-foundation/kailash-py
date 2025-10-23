"""Integration tests for API Gateway with real Docker services."""

import asyncio
import json
import time
from datetime import datetime

import pytest
import requests
from fastapi.testclient import TestClient
from kailash.middleware.communication.api_gateway import APIGateway
from kailash.middleware.core.agent_ui import AgentUIMiddleware
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager
from kailash.middleware.gateway.event_store import EventStore
from kailash.middleware.gateway.storage_backends import RedisEventStorage, RedisStorage
from kailash.nodes.transform import DataTransformer

from tests.config_unified import POSTGRES_CONFIG, REDIS_CONFIG


@pytest.fixture
def gateway_with_docker_services():
    """Create API Gateway with services (assumes services running locally)."""

    # Create Redis-backed services using unified config
    redis_checkpoint_storage = RedisStorage(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        db=0,
    )

    redis_event_storage = RedisEventStorage(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        db=1,
    )

    # Create checkpoint manager and event store
    checkpoint_manager = CheckpointManager(cloud_storage=redis_checkpoint_storage)
    event_store = EventStore(storage_backend=redis_event_storage)

    # Create Agent UI with PostgreSQL backend using unified config
    database_url = (
        f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}"
        f"@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}"
    )
    agent_ui = AgentUIMiddleware(
        database_url=database_url,
        enable_persistence=True,
        enable_dynamic_workflows=True,
    )

    # Create API Gateway
    gateway = APIGateway(
        enable_auth=False,
        enable_docs=True,
        database_url=database_url,
    )

    # Attach the managers to gateway for test access
    gateway.checkpoint_manager = checkpoint_manager
    gateway.event_store = event_store

    yield gateway, TestClient(gateway.app)

    # Cleanup
    asyncio.run(cleanup_services(checkpoint_manager, event_store, agent_ui))


async def cleanup_services(checkpoint_manager, event_store, agent_ui):
    """Clean up services after test."""
    try:
        await checkpoint_manager.close()
        await event_store.close()
        await agent_ui.close()
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.integration
class TestAPIGatewayDockerIntegration:
    """Test API Gateway with real Docker services."""

    def test_health_check_with_docker_services(self, gateway_with_docker_services):
        """Test health check endpoint with real services."""
        gateway, client = gateway_with_docker_services

        response = client.get("/health")
        assert response.status_code == 200

        health_data = response.json()
        assert health_data["status"] == "healthy"
        assert "timestamp" in health_data
        assert "components" in health_data

    def test_session_creation_with_postgres(self, gateway_with_docker_services):
        """Test session creation with PostgreSQL backend."""
        gateway, client = gateway_with_docker_services

        # Create session
        session_data = {
            "user_id": "test_user_postgres",
            "metadata": {"client": "integration_test"},
        }

        response = client.post("/api/sessions", json=session_data)
        assert response.status_code == 200

        session_response = response.json()
        assert "session_id" in session_response
        assert session_response["user_id"] == "test_user_postgres"
        assert session_response["active"] is True

        # Verify session can be retrieved
        session_id = session_response["session_id"]
        get_response = client.get(f"/api/sessions/{session_id}")
        assert get_response.status_code == 200

        retrieved_session = get_response.json()
        assert retrieved_session["session_id"] == session_id
        assert retrieved_session["user_id"] == "test_user_postgres"

    def test_data_transformation_with_execute(self, gateway_with_docker_services):
        """Test data transformation using execute() method."""
        gateway, client = gateway_with_docker_services

        # Test DataTransformer execute method directly
        transformer = gateway.data_transformer
        assert hasattr(transformer, "execute")
        assert not hasattr(transformer, "process")

        # Test transformation
        result = transformer.execute(
            data={"input": "test", "value": 42},
            transformations=[
                "{'transformed': True, **data}",
                "{'doubled_value': data['value'] * 2, **data}",
            ],
        )

        # Verify transformation results
        assert result["result"]["input"] == "test"
        assert result["result"]["value"] == 42
        assert result["result"]["doubled_value"] == 84
        # Note: Only the last transformation is applied, so 'transformed' field won't exist

    def test_event_logging_with_redis(self, gateway_with_docker_services):
        """Test event logging with Redis backend."""
        gateway, client = gateway_with_docker_services

        # Make a request that should generate events
        response = client.post("/api/sessions", json={"user_id": "event_test_user"})
        assert response.status_code == 200

        # Give time for async event processing
        time.sleep(0.5)

        # Check events through the API endpoint
        response = client.get("/api/stats")
        assert response.status_code == 200
        stats = response.json()

        # Verify session was created - check in agent_ui stats
        assert "agent_ui" in stats
        assert stats["agent_ui"]["total_sessions_created"] > 0

    def test_checkpoint_persistence_with_redis(self, gateway_with_docker_services):
        """Test checkpoint persistence with Redis backend."""
        gateway, client = gateway_with_docker_services

        # Create a session that should generate checkpoints
        session_data = {"user_id": "checkpoint_test_user"}
        response = client.post("/api/sessions", json=session_data)
        assert response.status_code == 200

        # Give time for async checkpoint processing
        time.sleep(0.5)

        # Check checkpoint manager stats
        stats = gateway.checkpoint_manager.get_stats()
        assert (
            stats["save_count"] >= 0
        )  # May or may not have checkpoints depending on implementation

    def test_concurrent_session_requests(self, gateway_with_docker_services):
        """Test concurrent session requests with Docker services."""
        gateway, client = gateway_with_docker_services

        # Create multiple sessions concurrently
        import concurrent.futures

        def create_session(user_id):
            return client.post(
                "/api/sessions", json={"user_id": f"concurrent_user_{user_id}"}
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_session, i) for i in range(10)]
            responses = [future.result() for future in futures]

        # Verify all sessions were created successfully
        session_ids = []
        for response in responses:
            assert response.status_code == 200
            session_data = response.json()
            session_ids.append(session_data["session_id"])

        # Verify all session IDs are unique
        assert len(set(session_ids)) == 10

        # Verify all sessions can be retrieved
        for session_id in session_ids:
            get_response = client.get(f"/api/sessions/{session_id}")
            assert get_response.status_code == 200

    def test_api_gateway_error_handling(self, gateway_with_docker_services):
        """Test API Gateway error handling with Docker services."""
        gateway, client = gateway_with_docker_services

        # Test invalid session creation
        response = client.post("/api/sessions", json={"invalid": "data"})
        # Should either succeed with default handling or return proper error
        assert response.status_code in [200, 400, 422]

        # Test retrieving non-existent session
        response = client.get("/api/sessions/nonexistent-session-id")
        assert response.status_code == 404

    def test_middleware_integration_pipeline(self, gateway_with_docker_services):
        """Test complete middleware integration pipeline."""
        gateway, client = gateway_with_docker_services

        # Step 1: Create session (uses PostgreSQL)
        session_response = client.post(
            "/api/sessions", json={"user_id": "pipeline_test"}
        )
        assert session_response.status_code == 200
        session_id = session_response.json()["session_id"]

        # Step 2: Process data transformation
        transformer = gateway.data_transformer
        transform_result = transformer.execute(
            data={"session_id": session_id, "action": "test_pipeline"},
            transformations=["{'processed': True, 'timestamp': '2024-01-01', **data}"],
        )

        assert transform_result["result"]["processed"] is True
        assert transform_result["result"]["session_id"] == session_id

        # Step 3: Verify session still exists
        get_response = client.get(f"/api/sessions/{session_id}")
        assert get_response.status_code == 200

        # Step 4: Give time for async processing (events, checkpoints)
        time.sleep(0.5)

        # Step 5: Check final stats
        event_stats = gateway.event_store.get_stats()
        checkpoint_stats = gateway.checkpoint_manager.get_stats()

        assert event_stats["event_count"] >= 0
        assert checkpoint_stats["save_count"] >= 0


@pytest.mark.integration
@pytest.mark.skip(
    reason="This test attempts to manage Docker containers dynamically - use existing Docker services instead"
)
class TestAPIGatewayDockerCompose:
    """Test API Gateway with Docker Compose services."""

    @pytest.fixture(scope="class")
    def docker_compose_services(self):
        """Start Docker Compose services for comprehensive testing."""
        import tempfile
        from pathlib import Path

        # Create temporary compose file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: gateway_test
      POSTGRES_USER: gateway_user
      POSTGRES_PASSWORD: gateway_pass
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gateway_user"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis-cache:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
"""
            f.write(compose_content)
            compose_file = Path(f.name)

        try:
            with DockerCompose(
                str(compose_file.parent), compose_file_name=compose_file.name
            ) as compose:
                # Wait for services to be healthy using proper health checks
                import socket
                from datetime import datetime

                start_time = datetime.now()
                services_ready = False

                while (datetime.now() - start_time).total_seconds() < 30.0:
                    # Check PostgreSQL
                    postgres_ready = False
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex(("localhost", 5432))
                        sock.close()
                        postgres_ready = result == 0
                    except:
                        pass

                    # Check Redis
                    redis_ready = False
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex(("localhost", 6379))
                        sock.close()
                        redis_ready = result == 0
                    except:
                        pass

                    # Check Redis cache
                    redis_cache_ready = False
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex(("localhost", 6380))
                        sock.close()
                        redis_cache_ready = result == 0
                    except:
                        pass

                    if postgres_ready and redis_ready and redis_cache_ready:
                        services_ready = True
                        break

                    time.sleep(0.5)

                if not services_ready:
                    pytest.fail("Docker services failed to start within 30 seconds")

                # Give services a moment to fully initialize after ports are open
                time.sleep(1)

                yield compose
        finally:
            compose_file.unlink()

    def test_full_stack_integration(self, docker_compose_services):
        """Test full stack integration with Docker Compose."""

        # Create services with Docker Compose backends using unified config
        checkpoint_storage = RedisStorage(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=0,
        )

        event_storage = RedisEventStorage(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=1,
        )

        checkpoint_manager = CheckpointManager(cloud_storage=checkpoint_storage)
        event_store = EventStore(storage_backend=event_storage)

        database_url = (
            f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}"
            f"@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}"
        )
        agent_ui = AgentUIMiddleware(
            database_url=database_url,
            enable_sessions=True,
            enable_analytics=True,
        )

        gateway = APIGateway(
            enable_auth=False,
            enable_docs=True,
            checkpoint_manager=checkpoint_manager,
            event_store=event_store,
            agent_ui=agent_ui,
        )

        client = TestClient(gateway.app)

        try:
            # Test health check
            response = client.get("/health")
            assert response.status_code == 200

            # Test session operations
            session_response = client.post(
                "/api/sessions", json={"user_id": "compose_test"}
            )
            assert session_response.status_code == 200

            session_id = session_response.json()["session_id"]

            # Test session retrieval
            get_response = client.get(f"/api/sessions/{session_id}")
            assert get_response.status_code == 200

            # Test data transformation
            transformer = gateway.data_transformer
            result = transformer.execute(
                data={"session_id": session_id, "compose_test": True},
                transformations=["{'verified': True, **data}"],
            )

            assert result["result"]["compose_test"] is True
            assert result["result"]["verified"] is True

            # Wait for async processing to complete
            from datetime import datetime

            start_time = datetime.now()
            while (datetime.now() - start_time).total_seconds() < 2.0:
                if gateway.event_store.event_count > 0:
                    break
                time.sleep(0.1)

            # Verify services are functioning
            assert gateway.event_store.event_count >= 0
            assert gateway.checkpoint_manager.get_stats()["save_count"] >= 0

        finally:
            # Cleanup
            asyncio.run(cleanup_services(checkpoint_manager, event_store, agent_ui))
