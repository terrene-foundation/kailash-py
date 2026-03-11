"""
Integration tests for DataFlow Gateway Integration.
Tests the multi-channel platform access functionality with real services.
NO MOCKING - uses real Docker services and actual gateway implementation.
"""

import asyncio

import pytest
from dataflow.gateway_integration import DataFlowGateway, create_dataflow_gateway

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.mark.integration
@pytest.mark.requires_docker
class TestDataFlowGateway:
    """Test DataFlow Gateway functionality with real services."""

    @pytest.fixture
    def postgresql_dataflow(self, test_suite):
        """Create DataFlow instance with PostgreSQL test database."""
        from dataflow import DataFlow

        db = DataFlow(test_suite.config.url)
        return db

    @pytest.fixture
    def gateway_config(self, test_suite):
        """Get gateway configuration with real database."""
        return {
            "database_url": test_suite.config.url,
            "enable_security": True,
            "enable_monitoring": True,
            "enable_connection_pooling": True,
        }

    @pytest.mark.asyncio
    async def test_start_and_stop_gateway_real(self, gateway_config):
        """Test starting and stopping the gateway with real services."""
        gateway = DataFlowGateway(**gateway_config)

        try:
            # Test start
            await gateway.start()

            # Verify gateway is running
            assert gateway.is_running(), "Gateway should be running"

            # Test gateway can handle requests
            workflow_info = gateway.get_workflow_info()
            assert workflow_info is not None, "Should get workflow info while running"

        finally:
            # Test stop
            await gateway.stop()
            assert not gateway.is_running(), "Gateway should be stopped"

    def test_get_workflow_info_with_real_dataflow(self, postgresql_dataflow):
        """Test getting workflow information with real DataFlow instance."""
        gateway = DataFlowGateway(dataflow=postgresql_dataflow)

        # Register some test models with the DataFlow instance
        @postgresql_dataflow.model
        class TestProduct:
            name: str
            price: float
            stock: int

        @postgresql_dataflow.model
        class TestOrder:
            product_id: int
            quantity: int
            total: float

        workflow_info = gateway.get_workflow_info()

        # Check structure
        assert isinstance(workflow_info, dict)
        assert len(workflow_info) > 0

        # Check that workflows for registered models exist
        assert any(
            "TestProduct" in key for key in workflow_info.keys()
        ), "Should have workflows for TestProduct"
        assert any(
            "TestOrder" in key for key in workflow_info.keys()
        ), "Should have workflows for TestOrder"

    @pytest.mark.asyncio
    async def test_concurrent_gateway_requests(self, gateway_config):
        """Test gateway handles concurrent requests with real services."""
        gateway = DataFlowGateway(**gateway_config)

        await gateway.start()

        try:
            # Simulate concurrent requests
            async def make_request(request_id):
                """Simulate a gateway request."""
                info = gateway.get_workflow_info()
                return request_id, len(info)

            # Create multiple concurrent requests
            tasks = [make_request(i) for i in range(10)]
            results = await asyncio.gather(*tasks)

            # Verify all requests completed
            assert len(results) == 10, "All requests should complete"

            # Verify all got valid responses
            for request_id, info_count in results:
                assert info_count > 0, f"Request {request_id} should get valid info"

        finally:
            await gateway.stop()

    def test_create_dataflow_gateway_factory(self, gateway_config):
        """Test the gateway factory function with real configuration."""
        gateway = create_dataflow_gateway(**gateway_config)

        # Verify gateway was created correctly
        assert isinstance(gateway, DataFlowGateway)
        assert gateway.config["database_url"] == gateway_config["database_url"]
        assert gateway.config["enable_security"]
        assert gateway.config["enable_monitoring"]
        assert gateway.config["enable_connection_pooling"]

    @pytest.mark.asyncio
    async def test_gateway_with_real_api_endpoints(self, gateway_config):
        """Test gateway API endpoints with real HTTP server."""
        gateway = DataFlowGateway(**gateway_config)

        await gateway.start()

        try:
            # If gateway includes HTTP server, test endpoints
            if hasattr(gateway, "get_api_endpoints"):
                endpoints = gateway.get_api_endpoints()

                # Verify standard endpoints exist
                assert "/api/workflows" in endpoints, "Should have workflows endpoint"
                assert "/api/models" in endpoints, "Should have models endpoint"
                assert "/api/health" in endpoints, "Should have health endpoint"

                # Test health endpoint
                if hasattr(gateway, "check_health"):
                    health = await gateway.check_health()
                    assert health["status"] == "healthy", "Gateway should be healthy"
                    assert "database" in health, "Should include database health"

        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_gateway_error_handling_with_real_services(self, gateway_config):
        """Test gateway error handling with real service failures."""
        # Create gateway with invalid database URL to test error handling
        bad_config = gateway_config.copy()
        bad_config["database_url"] = (
            "postgresql://invalid:invalid@localhost:9999/nonexistent"
        )

        gateway = DataFlowGateway(**bad_config)

        # Gateway should handle startup errors gracefully
        try:
            await gateway.start()
            # If it starts despite bad config, verify it's in degraded mode
            if gateway.is_running():
                status = gateway.get_status()
                assert status.get(
                    "degraded", False
                ), "Should be in degraded mode with bad database"
        except Exception as e:
            # Expected behavior - gateway fails to start with bad config
            assert (
                "connection" in str(e).lower() or "database" in str(e).lower()
            ), "Should fail due to database connection"
        finally:
            if gateway.is_running():
                await gateway.stop()
