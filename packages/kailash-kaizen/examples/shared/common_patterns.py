"""
Common Patterns and Utilities for Kaizen Workflow Examples

Shared components, utilities, and base classes used across
all example categories for consistency and reusability.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import dspy

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


# Common Configuration Classes
@dataclass
class BaseAgentConfig:
    """Base configuration for all agents."""

    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 500
    timeout: int = 30
    retry_attempts: int = 3


@dataclass
class MonitoringConfig:
    """Configuration for monitoring and observability."""

    enable_metrics: bool = True
    log_execution_traces: bool = True
    performance_monitoring: bool = True
    alert_on_errors: bool = False
    sla_monitoring: bool = False


@dataclass
class SecurityConfig:
    """Configuration for security features."""

    input_validation: bool = True
    output_sanitization: bool = True
    rate_limiting: bool = False
    audit_logging: bool = True
    compliance_reporting: bool = False


# Common Signature Patterns
class BaseAgentSignature(dspy.Signature):
    """Base signature with common input/output patterns."""

    request_id: str = dspy.InputField(desc="Unique request identifier", default="")
    timestamp: float = dspy.InputField(desc="Request timestamp", default=0.0)

    confidence: float = dspy.OutputField(desc="Confidence in response (0.0-1.0)")
    execution_time_ms: float = dspy.OutputField(desc="Execution time in milliseconds")


class ValidationSignature(dspy.Signature):
    """Common validation signature pattern."""

    input_data: str = dspy.InputField(desc="Data to validate")
    validation_rules: str = dspy.InputField(desc="Validation rules to apply")

    is_valid: bool = dspy.OutputField(desc="Whether input passes validation")
    validation_errors: str = dspy.OutputField(desc="Detailed validation error messages")
    sanitized_data: str = dspy.OutputField(desc="Cleaned and sanitized data")


class AuditSignature(dspy.Signature):
    """Common audit logging signature."""

    event_type: str = dspy.InputField(desc="Type of event being audited")
    event_data: str = dspy.InputField(desc="Event data to be logged")
    user_context: str = dspy.InputField(desc="User context information")

    audit_entry_id: str = dspy.OutputField(desc="Unique audit entry identifier")
    compliance_status: str = dspy.OutputField(desc="Compliance verification status")
    retention_policy: str = dspy.OutputField(desc="Data retention requirements")


# Common Utility Classes
class ExecutionTimer:
    """Utility for measuring execution time with detailed logging."""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None
        self.logger = logging.getLogger(f"timer.{operation_name}")

    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(f"Starting {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = (self.end_time - self.start_time) * 1000
        if exc_type is None:
            self.logger.info(f"Completed {self.operation_name} in {duration:.1f}ms")
        else:
            self.logger.error(
                f"Failed {self.operation_name} after {duration:.1f}ms: {exc_val}"
            )

    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0


class ResponseFormatter:
    """Utility for standardizing response formats across examples."""

    @staticmethod
    def success_response(
        data: Any, execution_time_ms: float, metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Format successful response."""
        return {
            "status": "success",
            "data": data,
            "metadata": {
                "execution_time_ms": round(execution_time_ms, 1),
                "timestamp": time.time(),
                **(metadata or {}),
            },
        }

    @staticmethod
    def error_response(
        error_message: str,
        error_code: str = "UNKNOWN_ERROR",
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Format error response."""
        return {
            "status": "error",
            "error": {"message": error_message, "code": error_code},
            "metadata": {"timestamp": time.time(), **(metadata or {})},
        }


class ConfigurationManager:
    """Utility for managing configuration across different environments."""

    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data

    def get_config(self, environment: str = "dev") -> Dict[str, Any]:
        """Get configuration for specific environment."""
        if environment not in self.config_data:
            raise ValueError(f"Unknown environment: {environment}")

        return self.config_data[environment]

    def get_agent_config(self, environment: str = "dev") -> BaseAgentConfig:
        """Get agent configuration for environment."""
        config = self.get_config(environment)
        llm_config = config.get("llm_config", {})

        return BaseAgentConfig(
            llm_provider=llm_config.get("provider", "openai"),
            model=llm_config.get("model", "gpt-4"),
            temperature=llm_config.get("temperature", 0.1),
            max_tokens=llm_config.get("max_tokens", 500),
            timeout=config.get("workflow_config", {}).get("timeout", 30),
            retry_attempts=config.get("workflow_config", {}).get("retry_attempts", 3),
        )


# Base Agent Classes
class BaseAgent:
    """Base class for all agent implementations."""

    def __init__(self, config: BaseAgentConfig, agent_id: str = "base_agent"):
        self.config = config
        self.agent_id = agent_id
        self.workflow = None
        self.runtime = None
        self.logger = logging.getLogger(f"agent.{agent_id}")
        self._initialize_workflow()

    def _initialize_workflow(self):
        """Initialize the workflow with standard configuration."""
        self.logger.info(f"Initializing {self.agent_id}")

        try:
            self.workflow = WorkflowBuilder()
            self.runtime = LocalRuntime()
            self._configure_agent()

        except Exception as e:
            self.logger.error(f"Failed to initialize {self.agent_id}: {e}")
            raise

    def _configure_agent(self):
        """Configure agent-specific settings. Override in subclasses."""
        pass

    def _validate_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate input data. Override in subclasses for specific validation."""
        if not input_data:
            raise ValueError("Input data cannot be empty")
        return input_data

    def _format_response(
        self, result: Dict[str, Any], execution_time: float
    ) -> Dict[str, Any]:
        """Format agent response with standard metadata."""
        return ResponseFormatter.success_response(
            data=result,
            execution_time_ms=execution_time,
            metadata={
                "agent_id": self.agent_id,
                "model_used": self.config.model,
                "temperature": self.config.temperature,
            },
        )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input data. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement process method")


class MultiAgentCoordinator:
    """Base class for coordinating multiple agents."""

    def __init__(self, agents: Dict[str, BaseAgent]):
        self.agents = agents
        self.logger = logging.getLogger("coordinator")
        self.execution_history = []

    async def coordinate(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Coordinate multiple agents for complex tasks."""
        self.logger.info(
            f"Starting coordination for task: {task.get('task_id', 'unknown')}"
        )

        coordination_start = time.time()
        results = {}

        try:
            # Sequential execution pattern (override for parallel/custom patterns)
            for agent_id, agent in self.agents.items():
                agent_start = time.time()

                # Prepare agent input based on previous results
                agent_input = self._prepare_agent_input(agent_id, task, results)

                # Execute agent
                agent_result = await agent.process(agent_input)
                results[agent_id] = agent_result

                # Log execution
                agent_duration = (time.time() - agent_start) * 1000
                self.logger.info(
                    f"Agent {agent_id} completed in {agent_duration:.1f}ms"
                )

                self.execution_history.append(
                    {
                        "agent_id": agent_id,
                        "execution_time_ms": agent_duration,
                        "timestamp": time.time(),
                    }
                )

            # Synthesize final result
            final_result = self._synthesize_results(results)

            coordination_duration = (time.time() - coordination_start) * 1000

            return ResponseFormatter.success_response(
                data=final_result,
                execution_time_ms=coordination_duration,
                metadata={
                    "agents_executed": len(self.agents),
                    "execution_history": self.execution_history,
                },
            )

        except Exception as e:
            self.logger.error(f"Coordination failed: {e}")
            return ResponseFormatter.error_response(
                error_message=str(e), error_code="COORDINATION_FAILED"
            )

    def _prepare_agent_input(
        self, agent_id: str, task: Dict[str, Any], previous_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare input for specific agent. Override in subclasses."""
        return {
            "task": task,
            "previous_results": previous_results,
            "agent_id": agent_id,
        }

    def _synthesize_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize results from multiple agents. Override in subclasses."""
        return {
            "summary": "Multi-agent coordination completed",
            "agent_results": results,
            "success": True,
        }


# Testing Utilities
class ExampleTestHarness:
    """Test harness for validating example implementations."""

    def __init__(self, example_name: str):
        self.example_name = example_name
        self.test_results = []
        self.logger = logging.getLogger(f"test.{example_name}")

    async def run_functional_tests(
        self, agent: BaseAgent, test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Run functional tests for an agent."""
        self.logger.info(f"Running functional tests for {self.example_name}")

        passed = 0
        failed = 0

        for i, test_case in enumerate(test_cases):
            try:
                result = await agent.process(test_case["input"])

                # Validate result structure
                assert "status" in result
                assert "data" in result
                assert "metadata" in result

                # Check expected outcomes if provided
                if "expected" in test_case:
                    self._validate_expectations(result, test_case["expected"])

                passed += 1
                self.logger.info(f"Test case {i+1} passed")

            except Exception as e:
                failed += 1
                self.logger.error(f"Test case {i+1} failed: {e}")
                self.test_results.append(
                    {"test_case": i + 1, "status": "failed", "error": str(e)}
                )

        return {
            "total_tests": len(test_cases),
            "passed": passed,
            "failed": failed,
            "success_rate": passed / len(test_cases) if test_cases else 0,
        }

    def _validate_expectations(self, result: Dict[str, Any], expected: Dict[str, Any]):
        """Validate result against expectations."""
        for key, expected_value in expected.items():
            if key not in result["data"]:
                raise AssertionError(f"Expected key '{key}' not found in result")

            actual_value = result["data"][key]
            if isinstance(expected_value, dict) and "type" in expected_value:
                # Type checking
                expected_type = expected_value["type"]
                if not isinstance(actual_value, eval(expected_type)):
                    raise AssertionError(
                        f"Expected {key} to be {expected_type}, got {type(actual_value)}"
                    )
            else:
                # Value checking
                if actual_value != expected_value:
                    raise AssertionError(
                        f"Expected {key}={expected_value}, got {actual_value}"
                    )


# Performance Monitoring
class PerformanceMonitor:
    """Monitor performance metrics across all examples."""

    def __init__(self):
        self.metrics = {
            "response_times": [],
            "success_rates": [],
            "error_counts": {},
            "resource_usage": [],
        }

    def record_execution(
        self, execution_time_ms: float, success: bool, error_type: str = None
    ):
        """Record execution metrics."""
        self.metrics["response_times"].append(execution_time_ms)

        if success:
            self.metrics["success_rates"].append(1)
        else:
            self.metrics["success_rates"].append(0)
            if error_type:
                self.metrics["error_counts"][error_type] = (
                    self.metrics["error_counts"].get(error_type, 0) + 1
                )

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        response_times = self.metrics["response_times"]
        success_rates = self.metrics["success_rates"]

        if not response_times:
            return {"status": "no_data"}

        return {
            "response_time_stats": {
                "mean": sum(response_times) / len(response_times),
                "min": min(response_times),
                "max": max(response_times),
                "p95": (
                    sorted(response_times)[int(len(response_times) * 0.95)]
                    if len(response_times) > 20
                    else max(response_times)
                ),
            },
            "success_rate": (
                sum(success_rates) / len(success_rates) if success_rates else 0
            ),
            "total_executions": len(response_times),
            "error_breakdown": self.metrics["error_counts"],
        }
