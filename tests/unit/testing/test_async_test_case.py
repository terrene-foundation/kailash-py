"""Unit tests for AsyncWorkflowTestCase."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kailash.nodes import PythonCodeNode
from kailash.testing import AsyncWorkflowTestCase, WorkflowTestResult
from kailash.workflow import AsyncWorkflowBuilder


class TestAsyncWorkflowTestCase:
    """Test the AsyncWorkflowTestCase functionality."""

    @pytest.mark.asyncio
    async def test_test_case_lifecycle(self):
        """Test test case setup and teardown."""
        setup_called = False
        teardown_called = False

        class TestCase(AsyncWorkflowTestCase):
            async def setUp(self):
                nonlocal setup_called
                await super().setUp()
                setup_called = True

            async def tearDown(self):
                nonlocal teardown_called
                await super().tearDown()
                teardown_called = True

        async with TestCase("test_lifecycle") as test:
            assert setup_called
            assert test.test_name == "test_lifecycle"
            assert not teardown_called

        assert teardown_called

    @pytest.mark.asyncio
    async def test_resource_creation_and_cleanup(self):
        """Test resource creation with automatic cleanup."""
        cleanup_called = False

        class MockResource:
            async def cleanup(self):
                nonlocal cleanup_called
                cleanup_called = True

        class MockFactory:
            async def create(self):
                return MockResource()

        async with AsyncWorkflowTestCase("test_resources") as test:
            resource = await test.create_test_resource("test_resource", MockFactory())
            assert isinstance(resource, MockResource)
            assert test.get_resource("test_resource") is resource

        # Cleanup should be called after context exit
        assert cleanup_called

    @pytest.mark.asyncio
    async def test_mock_resource_creation(self):
        """Test creating mock resources."""
        async with AsyncWorkflowTestCase("test_mocks") as test:
            # Create mock resource
            mock_db = await test.create_test_resource(
                "db", lambda: None, mock=True  # Simple factory for mocks
            )

            # Should be a mock
            assert hasattr(mock_db, "execute")
            assert hasattr(mock_db, "fetch")

            # Test calling mock methods
            await mock_db.execute("SELECT 1")
            mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_execution(self):
        """Test workflow execution with test case."""
        async with AsyncWorkflowTestCase("test_execution") as test:
            # Create simple workflow
            workflow = (
                AsyncWorkflowBuilder("test_workflow")
                .add_async_code("start", "result = {'value': 42}")
                .build()
            )

            # Execute workflow
            result = await test.execute_workflow(workflow, {})

            # Check result
            assert isinstance(result, WorkflowTestResult)
            if result.status != "success":
                print(f"Workflow failed: {result.error}")
                print(f"Errors: {result.errors}")
            assert result.status == "success"
            assert result.get_output("start", "value") == 42

    @pytest.mark.asyncio
    async def test_workflow_with_timeout(self):
        """Test workflow execution timeout."""
        async with AsyncWorkflowTestCase("test_timeout") as test:
            # Create slow workflow
            workflow = (
                AsyncWorkflowBuilder("slow_workflow")
                .add_async_code(
                    "slow",
                    """
import asyncio
await asyncio.sleep(2)
result = {'done': True}
""",
                )
                .build()
            )

            # Should timeout
            with pytest.raises(AssertionError, match="timed out"):
                await test.execute_workflow(workflow, {}, timeout=0.1)

    @pytest.mark.asyncio
    async def test_assertions(self):
        """Test assertion helpers."""
        async with AsyncWorkflowTestCase("test_assertions") as test:
            # Create workflow
            workflow = (
                AsyncWorkflowBuilder("test_workflow")
                .add_async_code("node1", "result = {'value': 'test'}")
                .add_async_code("node2", "result = {'number': 123}")
                .add_connection("node1", "result", "node2", "input")
                .build()
            )

            result = await test.execute_workflow(workflow, {})

            # Test assertions
            test.assert_workflow_success(result)
            test.assert_node_output(result, "node1", "test", "value")
            test.assert_node_output(result, "node2", 123, "number")

            # Assertions should be counted
            assert test._assertions_made == 3

    @pytest.mark.asyncio
    async def test_failed_workflow_assertion(self):
        """Test asserting workflow failure."""
        async with AsyncWorkflowTestCase("test_failure") as test:
            # Create failing workflow
            workflow = (
                AsyncWorkflowBuilder("failing_workflow")
                .add_async_code("fail", "raise ValueError('test error')")
                .build()
            )

            result = await test.execute_workflow(workflow, {})

            # Should be failed
            test.assert_workflow_failed(result)

            # Success assertion should fail
            with pytest.raises(AssertionError):
                test.assert_workflow_success(result)

    @pytest.mark.asyncio
    async def test_time_limit_context_manager(self):
        """Test time limit assertion."""
        async with AsyncWorkflowTestCase("test_time_limit") as test:
            # Fast operation should pass
            async with test.assert_time_limit(1.0):
                await asyncio.sleep(0.01)

            # Slow operation should fail
            with pytest.raises(AssertionError, match="exceeding limit"):
                async with test.assert_time_limit(0.01):
                    await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_cleanup_order(self):
        """Test cleanup happens in reverse order."""
        cleanup_order = []

        async def cleanup1():
            cleanup_order.append(1)

        async def cleanup2():
            cleanup_order.append(2)

        async def cleanup3():
            cleanup_order.append(3)

        async with AsyncWorkflowTestCase("test_cleanup_order") as test:
            test.add_cleanup(cleanup1)
            test.add_cleanup(cleanup2)
            test.add_cleanup(cleanup3)

        # Should be reversed
        assert cleanup_order == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_mock_resource_in_workflow(self):
        """Test using mock resources in workflow."""
        async with AsyncWorkflowTestCase("test_mock_workflow") as test:
            # Create mock HTTP client
            mock_http = await test.create_test_resource(
                "http", lambda: Mock(), mock=True
            )

            # Configure the mock after creation (after registry processes it)
            response = AsyncMock()
            response.json = AsyncMock(return_value={"result": "success"})
            response.status = 200
            mock_http.get.return_value = response

            # Create workflow that uses HTTP
            workflow = (
                AsyncWorkflowBuilder("http_workflow")
                .add_async_code(
                    "fetch",
                    """
http = await get_resource("http")
resp = await http.get("https://api.example.com/data")
data = await resp.json()
result = {"api_result": data}
""",
                )
                .build()
            )

            # Execute
            result = await test.execute_workflow(workflow, {})

            # Check result
            test.assert_workflow_success(result)
            assert result.get_output("fetch", "api_result.result") == "success"

            # Check mock was called
            test.assert_resource_called("http", "get", times=1)

    @pytest.mark.asyncio
    async def test_resource_not_found(self):
        """Test getting non-existent resource."""
        async with AsyncWorkflowTestCase("test_not_found") as test:
            with pytest.raises(KeyError, match="not found"):
                test.get_resource("nonexistent")

    @pytest.mark.asyncio
    async def test_workflow_data_processing(self):
        """Test workflow data processing capabilities."""
        async with AsyncWorkflowTestCase("test_processing") as test:
            # Create simple workflow with input
            workflow = (
                AsyncWorkflowBuilder("processing_workflow")
                .add_async_code("double", "result = {'doubled': number * 2}")
                .build()
            )

            # Execute workflow with input
            result = await test.execute_workflow(workflow, {"number": 21})

            # Check processing results
            assert result.status == "success"
            assert result.get_output("double", "doubled") == 42

    @pytest.mark.asyncio
    async def test_nested_output_access(self):
        """Test accessing nested outputs with dot notation."""
        async with AsyncWorkflowTestCase("test_nested") as test:
            workflow = (
                AsyncWorkflowBuilder("nested_workflow")
                .add_async_code(
                    "nested",
                    """
result = {
    "user": {
        "profile": {
            "name": "Test User",
            "id": 123
        }
    }
}
""",
                )
                .build()
            )

            result = await test.execute_workflow(workflow, {})

            # Test nested access
            assert result.get_output("nested", "user.profile.name") == "Test User"
            assert result.get_output("nested", "user.profile.id") == 123
            assert result.get_output("nested", "user.profile.missing") is None
