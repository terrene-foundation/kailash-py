"""
Integration test helpers for Kaizen framework testing.

Provides utilities for Tier 2 (Integration) and Tier 3 (E2E) testing with real Core SDK infrastructure.
NO MOCKING - all utilities work with real services and components.

Based on Kailash Core SDK test infrastructure patterns with Kaizen-specific enhancements.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kaizen.core.agents import Agent
from kaizen.core.config import KaizenConfig
from kaizen.core.framework import Kaizen

from .docker_config import ensure_docker_services

logger = logging.getLogger(__name__)


@dataclass
class WorkflowExecutionResult:
    """Result of workflow execution with validation metadata."""

    results: Dict[str, Any]
    run_id: str
    execution_time_ms: float
    success: bool
    error_message: Optional[str] = None
    validation_results: Optional[Dict[str, Any]] = None


class IntegrationTestSuite:
    """Base class for integration test suites following Kailash patterns."""

    def __init__(self, require_enterprise_services: bool = False):
        """
        Initialize integration test suite.

        Args:
            require_enterprise_services: If True, requires full enterprise stack (Ollama, MongoDB)
        """
        self.require_enterprise_services = require_enterprise_services
        self.kaizen: Optional[Kaizen] = None
        self.runtime: Optional[LocalRuntime] = None
        self._setup_complete = False

    async def setup(self) -> bool:
        """Setup test infrastructure with real services."""
        try:
            # Ensure Docker services are available
            services_ready = await ensure_docker_services(
                enterprise_mode=self.require_enterprise_services
            )
            if not services_ready:
                logger.error("Required Docker services not available")
                return False

            # Initialize Kaizen framework with real configuration
            config = KaizenConfig(
                debug=True,
                memory_enabled=True,
                optimization_enabled=True,
                monitoring_enabled=True if self.require_enterprise_services else False,
            )
            self.kaizen = Kaizen(config=config)

            # Initialize runtime
            self.runtime = LocalRuntime()

            self._setup_complete = True
            logger.info("Integration test suite setup completed")
            return True

        except Exception as e:
            logger.error(f"Integration test suite setup failed: {e}")
            return False

    async def teardown(self):
        """Clean up test resources."""
        if self.kaizen:
            # Clean up agents and signatures
            self.kaizen._agents.clear()
            self.kaizen._signatures.clear()

        self._setup_complete = False
        logger.info("Integration test suite teardown completed")

    def assert_setup_complete(self):
        """Assert that setup was completed successfully."""
        if not self._setup_complete:
            raise RuntimeError(
                "Integration test suite not properly set up. Call setup() first."
            )

    async def create_test_agent(
        self, agent_id: str, config: Dict[str, Any], signature: Optional[str] = None
    ) -> Agent:
        """Create a test agent with real Kaizen framework."""
        self.assert_setup_complete()

        agent = self.kaizen.create_agent(agent_id, config, signature=signature)
        return agent

    async def execute_agent_workflow(
        self, agent: Agent, inputs: Dict[str, Any], validate_outputs: bool = True
    ) -> WorkflowExecutionResult:
        """Execute agent workflow with performance tracking and validation."""
        self.assert_setup_complete()

        start_time = time.time()
        try:
            # Execute using Core SDK pattern
            workflow = agent.compile_workflow()
            results, run_id = self.runtime.execute(workflow.build(), parameters=inputs)

            execution_time_ms = (time.time() - start_time) * 1000

            # Validate results if requested
            validation_results = None
            if validate_outputs:
                validation_results = self._validate_workflow_results(results, agent)

            return WorkflowExecutionResult(
                results=results,
                run_id=run_id,
                execution_time_ms=execution_time_ms,
                success=True,
                validation_results=validation_results,
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Workflow execution failed: {e}")

            return WorkflowExecutionResult(
                results={},
                run_id="",
                execution_time_ms=execution_time_ms,
                success=False,
                error_message=str(e),
            )

    def _validate_workflow_results(
        self, results: Dict[str, Any], agent: Agent
    ) -> Dict[str, Any]:
        """Validate workflow execution results."""
        validation = {
            "has_results": bool(results),
            "result_keys": list(results.keys()) if results else [],
            "non_empty_results": (
                sum(1 for v in results.values() if v is not None) if results else 0
            ),
            "agent_signature_matched": False,
        }

        # Check if results match agent signature expectations
        if agent.signature:
            expected_outputs = agent.signature.define_outputs()
            validation["agent_signature_matched"] = all(
                key in results for key in expected_outputs.keys()
            )

        return validation

    async def wait_for_condition(
        self,
        condition: Callable[[], bool],
        timeout: float = 10.0,
        poll_interval: float = 0.1,
        error_message: Optional[str] = None,
    ) -> bool:
        """Wait for a condition to become true (adapted from Kailash test helpers)."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if await asyncio.get_event_loop().run_in_executor(None, condition):
                    return True
            except Exception:
                pass  # Condition might raise exceptions while waiting
            await asyncio.sleep(poll_interval)

        if error_message:
            logger.error(f"Timeout waiting for condition: {error_message}")
        return False


class MultiAgentCoordinationTestSuite(IntegrationTestSuite):
    """Specialized test suite for multi-agent coordination patterns."""

    def __init__(self):
        super().__init__(require_enterprise_services=True)
        self.coordination_patterns = []

    async def create_agent_team(
        self, team_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Agent]:
        """Create a team of agents for coordination testing."""
        self.assert_setup_complete()

        agents = {}
        for agent_id, config in team_config.items():
            agents[agent_id] = await self.create_test_agent(agent_id, config)

        return agents

    async def execute_coordination_workflow(
        self,
        agents: Dict[str, Agent],
        coordination_pattern: str,
        initial_inputs: Dict[str, Any],
    ) -> WorkflowExecutionResult:
        """Execute multi-agent coordination workflow."""
        self.assert_setup_complete()

        start_time = time.time()
        try:
            # Build coordination workflow using WorkflowBuilder
            workflow = WorkflowBuilder()

            # Add agents as nodes
            for agent_id, agent in agents.items():
                agent_node = agent.to_workflow_node()
                workflow.add_node_instance(agent_id, agent_node)

            # Add coordination connections based on pattern
            if coordination_pattern == "sequential":
                agent_ids = list(agents.keys())
                for i in range(len(agent_ids) - 1):
                    workflow.add_connection(
                        agent_ids[i], "response", agent_ids[i + 1], "input"
                    )
            elif coordination_pattern == "parallel":
                # All agents receive same initial input
                for agent_id in agents.keys():
                    workflow.add_connection("input_node", "data", agent_id, "input")

            # Execute coordination workflow
            results, run_id = self.runtime.execute(
                workflow.build(), parameters=initial_inputs
            )

            execution_time_ms = (time.time() - start_time) * 1000

            return WorkflowExecutionResult(
                results=results,
                run_id=run_id,
                execution_time_ms=execution_time_ms,
                success=True,
                validation_results={"coordination_pattern": coordination_pattern},
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Coordination workflow execution failed: {e}")

            return WorkflowExecutionResult(
                results={},
                run_id="",
                execution_time_ms=execution_time_ms,
                success=False,
                error_message=str(e),
            )


async def validate_workflow_execution(
    workflow: WorkflowBuilder,
    runtime: LocalRuntime,
    parameters: Dict[str, Any] = None,
    expected_outputs: List[str] = None,
    max_execution_time_ms: float = 5000,
) -> WorkflowExecutionResult:
    """
    Validate workflow execution with performance and output checks.

    Args:
        workflow: WorkflowBuilder instance to execute
        runtime: LocalRuntime instance for execution
        parameters: Execution parameters
        expected_outputs: Expected output keys to validate
        max_execution_time_ms: Maximum allowed execution time

    Returns:
        WorkflowExecutionResult with validation metadata
    """
    start_time = time.time()

    try:
        # Execute workflow using Core SDK pattern
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        execution_time_ms = (time.time() - start_time) * 1000

        # Validate execution time
        performance_ok = execution_time_ms <= max_execution_time_ms

        # Validate expected outputs
        output_validation = {}
        if expected_outputs:
            missing_outputs = [key for key in expected_outputs if key not in results]
            output_validation = {
                "expected_outputs": expected_outputs,
                "actual_outputs": list(results.keys()),
                "missing_outputs": missing_outputs,
                "all_outputs_present": len(missing_outputs) == 0,
            }

        validation_results = {
            "performance_ok": performance_ok,
            "execution_time_ms": execution_time_ms,
            "max_allowed_ms": max_execution_time_ms,
            **output_validation,
        }

        return WorkflowExecutionResult(
            results=results,
            run_id=run_id,
            execution_time_ms=execution_time_ms,
            success=True,
            validation_results=validation_results,
        )

    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Workflow execution validation failed: {e}")

        return WorkflowExecutionResult(
            results={},
            run_id="",
            execution_time_ms=execution_time_ms,
            success=False,
            error_message=str(e),
        )


async def setup_test_environment() -> Tuple[Kaizen, LocalRuntime]:
    """
    Setup complete test environment with real infrastructure.

    Returns:
        Tuple of (Kaizen framework, LocalRuntime) ready for testing
    """
    # Ensure Docker services are available
    services_ready = await ensure_docker_services()
    if not services_ready:
        raise RuntimeError("Required Docker services not available for testing")

    # Initialize Kaizen framework with test configuration
    config = KaizenConfig(
        debug=True,
        memory_enabled=True,
        optimization_enabled=True,
        monitoring_enabled=True,
    )
    kaizen = Kaizen(config=config)

    # Initialize runtime
    runtime = LocalRuntime()

    logger.info("Test environment setup completed successfully")
    return kaizen, runtime


async def cleanup_test_environment(kaizen: Kaizen):
    """Clean up test environment resources."""
    if kaizen:
        kaizen._agents.clear()
        kaizen._signatures.clear()
        logger.info("Test environment cleaned up")


# Performance testing utilities
class PerformanceBenchmark:
    """Performance benchmark utilities for integration testing."""

    def __init__(self, name: str):
        self.name = name
        self.measurements = []
        self.start_time = None

    def start(self):
        """Start performance measurement."""
        self.start_time = time.perf_counter()

    def stop(self) -> float:
        """Stop measurement and return duration in milliseconds."""
        if self.start_time is None:
            raise ValueError("Benchmark not started")

        duration_ms = (time.perf_counter() - self.start_time) * 1000
        self.measurements.append(duration_ms)
        self.start_time = None
        return duration_ms

    def get_stats(self) -> Dict[str, float]:
        """Get performance statistics."""
        if not self.measurements:
            return {"count": 0, "avg_ms": 0, "min_ms": 0, "max_ms": 0}

        return {
            "count": len(self.measurements),
            "avg_ms": sum(self.measurements) / len(self.measurements),
            "min_ms": min(self.measurements),
            "max_ms": max(self.measurements),
            "total_ms": sum(self.measurements),
        }

    def assert_performance(self, max_avg_ms: float, max_single_ms: float):
        """Assert performance requirements are met."""
        stats = self.get_stats()
        assert (
            stats["avg_ms"] <= max_avg_ms
        ), f"Average time {stats['avg_ms']:.2f}ms exceeds {max_avg_ms}ms"
        assert (
            stats["max_ms"] <= max_single_ms
        ), f"Max time {stats['max_ms']:.2f}ms exceeds {max_single_ms}ms"


# Error simulation utilities for robust testing
class ErrorSimulator:
    """Utilities for testing error handling and recovery."""

    @staticmethod
    async def simulate_network_timeout(duration_ms: float = 1000):
        """Simulate network timeout scenario."""
        await asyncio.sleep(duration_ms / 1000)

    @staticmethod
    def simulate_memory_pressure() -> Dict[str, Any]:
        """Simulate memory pressure by creating large objects."""
        large_objects = []
        try:
            # Create progressively larger objects until memory pressure
            for i in range(10):
                large_objects.append([0] * (10**6))  # 1M integers
            return {
                "memory_pressure_created": True,
                "objects_created": len(large_objects),
            }
        except MemoryError:
            return {"memory_pressure_created": True, "memory_error_triggered": True}

    @staticmethod
    def create_invalid_config() -> Dict[str, Any]:
        """Create invalid configuration for error testing."""
        return {
            "model": None,  # Invalid model
            "temperature": 2.0,  # Invalid temperature > 1
            "max_tokens": -1,  # Invalid negative tokens
            "timeout": 0.001,  # Very short timeout
        }
