"""Base class for async workflow testing."""

import asyncio
import functools
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from ..resources.registry import ResourceFactory, ResourceRegistry
from ..runtime.async_local import AsyncLocalRuntime, ExecutionContext
from ..workflow.graph import Workflow
from .mock_registry import MockResourceRegistry

T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass
class WorkflowTestResult:
    """Result from test workflow execution."""

    status: str
    outputs: Dict[str, Any]
    errors: List[tuple[str, Exception]] = field(default_factory=list)
    error: Optional[str] = None
    execution_time: float = 0.0
    node_timings: Dict[str, float] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""

    def get_output(self, node_id: str, key: Optional[str] = None) -> Any:
        """Get output from specific node."""
        output = self.outputs.get(node_id)

        if key and isinstance(output, dict):
            # Handle nested keys
            keys = key.split(".")
            for k in keys:
                if isinstance(output, dict):
                    output = output.get(k)
                else:
                    return None

        return output

    def get_logs(self) -> str:
        """Get formatted logs."""
        return "\n".join(self.logs)

    def print_summary(self):
        """Print execution summary."""
        print(f"Status: {self.status}")
        print(f"Execution time: {self.execution_time:.2f}s")

        if self.errors:
            print(f"Errors: {len(self.errors)}")
            for node_id, error in self.errors:
                print(f"  - {node_id}: {error}")

        print(f"Nodes executed: {len(self.outputs)}")
        for node_id, timing in self.node_timings.items():
            print(f"  - {node_id}: {timing:.3f}s")


class AsyncWorkflowTestCase:
    """Base class for async workflow testing."""

    def __init__(self, test_name: str = None):
        self.test_name = test_name or self.__class__.__name__
        self.resource_registry = ResourceRegistry()
        self.mock_registry = MockResourceRegistry()
        self._cleanup_tasks: List[Callable] = []
        self._test_resources: Dict[str, Any] = {}
        self._assertions_made = 0
        self._start_time: Optional[datetime] = None

    async def setUp(self):
        """Override to set up test resources."""
        self._start_time = datetime.now(timezone.utc)
        logger.info(f"Setting up test: {self.test_name}")

    async def tearDown(self):
        """Override for custom cleanup."""
        logger.info(f"Tearing down test: {self.test_name}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.setUp()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        # Always run tearDown
        try:
            await self.tearDown()
        except Exception as e:
            logger.error(f"Error in tearDown: {e}")

        # Run all cleanup tasks in reverse order
        for task in reversed(self._cleanup_tasks):
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")

        # Clean up registries
        try:
            await self.resource_registry.cleanup()
        except Exception as e:
            logger.error(f"Resource registry cleanup failed: {e}")

        # Log test summary
        if self._start_time:
            duration = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            logger.info(
                f"Test {self.test_name} completed in {duration:.2f}s "
                f"with {self._assertions_made} assertions"
            )

    def add_cleanup(self, cleanup_func: Callable):
        """Register a cleanup function/coroutine."""
        self._cleanup_tasks.append(cleanup_func)

    async def create_test_resource(
        self,
        name: str,
        factory: Union[ResourceFactory, Callable],
        mock: bool = False,
        health_check: Callable = None,
        cleanup_handler: Callable = None,
    ) -> Any:
        """Create a test resource with automatic cleanup."""
        if mock:
            # Create mock resource
            resource = await self.mock_registry.create_mock(name, factory)
        else:
            # Handle callable factories
            if callable(factory) and not hasattr(factory, "create"):
                # Wrap in a proper factory
                class CallableFactory:
                    def __init__(self, func):
                        self.func = func

                    async def create(self):
                        if asyncio.iscoroutinefunction(self.func):
                            return await self.func()
                        return self.func()

                factory = CallableFactory(factory)

            # Register real resource
            self.resource_registry.register_factory(
                name,
                factory,
                health_check=health_check,
                cleanup_handler=cleanup_handler,
            )
            resource = await self.resource_registry.get_resource(name)

        # Store for later access
        self._test_resources[name] = resource

        # Register cleanup if not already handled
        if not cleanup_handler:

            async def default_cleanup():
                if hasattr(resource, "close"):
                    if asyncio.iscoroutinefunction(resource.close):
                        await resource.close()
                    else:
                        resource.close()
                elif hasattr(resource, "cleanup"):
                    if asyncio.iscoroutinefunction(resource.cleanup):
                        await resource.cleanup()
                    else:
                        resource.cleanup()

            self.add_cleanup(default_cleanup)

        return resource

    async def execute_workflow(
        self,
        workflow: Workflow,
        inputs: Dict[str, Any],
        mock_resources: Dict[str, Any] = None,
        timeout: float = 30.0,
        capture_logs: bool = True,
    ) -> WorkflowTestResult:
        """Execute workflow with test environment."""
        # Register mock resources
        if mock_resources:
            for name, mock in mock_resources.items():
                self.mock_registry.register_mock(name, mock)

        # Create a test resource registry that checks mocks first
        class TestResourceRegistry:
            def __init__(self, real_registry, mock_registry):
                self.real_registry = real_registry
                self.mock_registry = mock_registry
                # Copy all attributes from real registry to ensure compatibility
                if real_registry:
                    for attr in dir(real_registry):
                        if not attr.startswith("_") and not hasattr(self, attr):
                            try:
                                setattr(self, attr, getattr(real_registry, attr))
                            except AttributeError:
                                pass

            async def get_resource(self, name: str):
                # Check mock registry first
                mock = self.mock_registry.get_mock(name)
                if mock is not None:
                    return mock
                # Fall back to real resources
                if self.real_registry:
                    return await self.real_registry.get_resource(name)
                raise RuntimeError(f"No resource '{name}' found")

            def register_factory(self, name: str, factory):
                """Delegate factory registration to real registry."""
                if self.real_registry:
                    return self.real_registry.register_factory(name, factory)

            def list_resources(self):
                """List all available resources."""
                resources = []
                if self.real_registry:
                    resources.extend(self.real_registry.list_resources())
                resources.extend(self.mock_registry.list_mocks())
                return resources

            def __getattr__(self, name):
                # Delegate other methods to real registry
                if self.real_registry and hasattr(self.real_registry, name):
                    return getattr(self.real_registry, name)
                raise AttributeError(
                    f"'{type(self).__name__}' has no attribute '{name}'"
                )

        # Create test runtime with test resource registry
        test_registry = TestResourceRegistry(self.resource_registry, self.mock_registry)
        runtime = AsyncLocalRuntime(resource_registry=test_registry)

        # Execute with timeout
        start_time = asyncio.get_event_loop().time()
        logs = []

        try:
            # Execute workflow
            result = await asyncio.wait_for(
                runtime.execute_workflow_async(workflow, inputs), timeout=timeout
            )

            # Convert to test result
            return WorkflowTestResult(
                status="success" if not result.get("errors") else "failed",
                outputs=result.get("results", {}),
                errors=[
                    (node, error) for node, error in result.get("errors", {}).items()
                ],
                error=(
                    list(result.get("errors", {}).values())[0]
                    if result.get("errors")
                    else None
                ),
                execution_time=result.get(
                    "total_duration", asyncio.get_event_loop().time() - start_time
                ),
                node_timings=result.get("execution_times", {}),
                logs=logs,
            )

        except asyncio.TimeoutError:
            raise AssertionError(f"Workflow execution timed out after {timeout}s")
        except Exception as e:
            # Create error result
            return WorkflowTestResult(
                status="failed",
                outputs={},
                error=str(e),
                errors=[("execution", e)],
                execution_time=asyncio.get_event_loop().time() - start_time,
                logs=logs,
            )

    def get_resource(self, name: str) -> Any:
        """Get a test resource by name."""
        if name in self._test_resources:
            return self._test_resources[name]
        raise KeyError(f"Test resource '{name}' not found")

    # Assertion helpers
    def assert_workflow_success(self, result: WorkflowTestResult):
        """Assert workflow completed successfully."""
        self._assertions_made += 1
        assert result.status == "success", (
            f"Workflow failed: {result.error}\n"
            f"Errors: {result.errors}\n"
            f"Logs: {result.get_logs()}"
        )

    def assert_workflow_failed(self, result: WorkflowTestResult):
        """Assert workflow failed."""
        self._assertions_made += 1
        assert result.status == "failed", "Workflow did not fail as expected"

    def assert_node_output(
        self, result: WorkflowTestResult, node_id: str, expected: Any, key: str = None
    ):
        """Assert node output matches expected."""
        self._assertions_made += 1
        actual = result.get_output(node_id, key)
        assert actual == expected, (
            f"Node {node_id} output mismatch\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )

    def assert_resource_called(
        self,
        resource_name: str,
        method_name: str,
        times: int = None,
        with_args: tuple = None,
        with_kwargs: dict = None,
    ):
        """Assert a resource method was called."""
        self._assertions_made += 1
        self.mock_registry.assert_called(
            resource_name,
            method_name,
            times=times,
            with_args=with_args,
            with_kwargs=with_kwargs,
        )

    @asynccontextmanager
    async def assert_time_limit(self, seconds: float):
        """Context manager to assert code completes within time limit."""
        start = asyncio.get_event_loop().time()
        yield
        elapsed = asyncio.get_event_loop().time() - start
        self._assertions_made += 1
        assert elapsed < seconds, (
            f"Operation took {elapsed:.2f}s, " f"exceeding limit of {seconds}s"
        )
