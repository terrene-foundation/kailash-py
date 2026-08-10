"""
Standardized Test Fixtures for Example Tests

This module provides standardized fixtures to remove boilerplate and ensure
consistent test environment, setup, and data across all example tests.

Key Features:
- Standardized example module imports (no sys.path pollution)
- Standard test configurations (mock, async, real LLM)
- Standard mock providers with realistic outputs
- Common test data for validation
- Standardized assertions and helpers
"""

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

# Import helper for safe example module loading
from example_import_helper import import_example_module

# Import Kaizen core components
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import Signature
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
from kaizen.strategies.single_shot import SingleShotStrategy

# Import standard mock providers
from tests.utils.mock_providers import MockLLMProvider

# ============================================================================
# EXAMPLE MODULE LOADING FIXTURES
# ============================================================================


@dataclass
class ExampleModule:
    """Container for loaded example module components."""

    module: Any
    workflow_function: Optional[Any] = None
    agent_classes: Dict[str, type] = None
    config_classes: Dict[str, type] = None

    def __post_init__(self):
        if self.agent_classes is None:
            self.agent_classes = {}
        if self.config_classes is None:
            self.config_classes = {}


@pytest.fixture
def load_example():
    """
    Factory fixture to load any example module without sys.path pollution.

    Usage:
        def test_example(load_example):
            example = load_example("examples/1-single-agent/simple-qa")
            agent = example.agent_classes["SimpleQAAgent"](config)
    """

    def _load(example_path: str, auto_discover: bool = True) -> ExampleModule:
        """
        Load example module and optionally auto-discover components.

        Args:
            example_path: Relative path to example (e.g., "examples/1-single-agent/simple-qa")
            auto_discover: Auto-discover agent/config classes (default: True)
        """
        module = import_example_module(example_path)

        example_module = ExampleModule(module=module)

        if auto_discover:
            # Auto-discover workflow function
            if hasattr(module, "workflow"):
                example_module.workflow_function = module.workflow
            else:
                # Try common workflow function patterns
                for name in dir(module):
                    if name.endswith("_workflow") and callable(getattr(module, name)):
                        example_module.workflow_function = getattr(module, name)
                        break

            # Auto-discover agent classes (end with "Agent")
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseAgent)
                    and obj is not BaseAgent
                    and name.endswith("Agent")
                ):
                    example_module.agent_classes[name] = obj

            # Auto-discover config classes (end with "Config")
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and name.endswith("Config")
                    and name != "BaseAgentConfig"
                ):
                    example_module.config_classes[name] = obj

        return example_module

    return _load


@pytest.fixture
def simple_qa_example(load_example):
    """Pre-loaded simple-qa example."""
    return load_example("examples/1-single-agent/simple-qa")


@pytest.fixture
def chain_of_thought_example(load_example):
    """Pre-loaded chain-of-thought example."""
    return load_example("examples/1-single-agent/chain-of-thought")


@pytest.fixture
def rag_research_example(load_example):
    """Pre-loaded rag-research example."""
    return load_example("examples/1-single-agent/rag-research")


@pytest.fixture
def code_generation_example(load_example):
    """Pre-loaded code-generation example."""
    return load_example("examples/1-single-agent/code-generation")


@pytest.fixture
def memory_agent_example(load_example):
    """Pre-loaded memory-agent example."""
    return load_example("examples/1-single-agent/memory-agent")


# ============================================================================
# STANDARD TEST CONFIGURATIONS
# ============================================================================


@pytest.fixture
def mock_config():
    """Standard mock configuration for unit tests."""
    return {
        "llm_provider": "mock",
        "model": "gpt-3.5-turbo",
        "temperature": 0.7,
        "max_tokens": 1000,
    }


@pytest.fixture
def async_config():
    """Standard async configuration for async strategy tests."""
    return {
        "llm_provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 2000,
    }


@pytest.fixture
def real_llm_config():
    """Standard real LLM configuration (requires API key)."""
    return {
        "llm_provider": "openai",
        "model": "gpt-3.5-turbo",
        "temperature": 0.3,
        "max_tokens": 1500,
    }


@pytest.fixture
def shared_memory_pool():
    """Standard shared memory pool for multi-agent tests."""
    return SharedMemoryPool()


# ============================================================================
# MOCK PROVIDERS WITH REALISTIC OUTPUTS
# ============================================================================


@pytest.fixture
def mock_llm_provider():
    """Standard mock LLM provider with realistic responses."""
    return MockLLMProvider()


@pytest.fixture
def mock_qa_response():
    """Standard mock response for QA tasks."""
    return {
        "answer": "This is a mock answer to the question.",
        "confidence": "0.95",
        "reasoning": "Mock reasoning for the answer",
        "sources": "[]",
    }


@pytest.fixture
def mock_code_generation_response():
    """Standard mock response for code generation tasks."""
    return {
        "code": "def example_function():\n    return 'Hello, World!'",
        "explanation": "This is a simple example function",
        "test_cases": '["test_basic_functionality", "test_edge_cases"]',
        "documentation": "Example function documentation",
        "confidence": "0.9",
    }


@pytest.fixture
def mock_rag_response():
    """Standard mock response for RAG tasks."""
    return {
        "answer": "Mock RAG answer based on retrieved documents",
        "documents": '[{"content": "Document 1", "score": 0.95}, {"content": "Document 2", "score": 0.85}]',
        "confidence": "0.9",
        "sources": '["source1", "source2"]',
    }


@pytest.fixture
def mock_cot_response():
    """Standard mock response for chain-of-thought tasks."""
    return {
        "thoughts": '["Step 1: Analyze", "Step 2: Process", "Step 3: Conclude"]',
        "final_answer": "Mock chain-of-thought final answer",
        "confidence": "0.88",
        "reasoning_depth": "3",
    }


# ============================================================================
# COMMON TEST DATA
# ============================================================================


@pytest.fixture
def test_queries():
    """Standard test queries for various tasks."""
    return {
        "simple": "What is the capital of France?",
        "complex": "Explain the relationship between quantum mechanics and general relativity",
        "code": "Write a function to calculate fibonacci numbers",
        "empty": "",
        "long": "This is a very long query. " * 100,
        "special_chars": "Test query with special characters: @#$%^&*()",
        "multilingual": "こんにちは世界",  # "Hello World" in Japanese
    }


@pytest.fixture
def test_documents():
    """Standard test documents for RAG tasks."""
    return [
        {
            "id": "doc1",
            "content": "Paris is the capital and most populous city of France.",
            "metadata": {"source": "geography", "score": 0.95},
        },
        {
            "id": "doc2",
            "content": "The Eiffel Tower is located in Paris, France.",
            "metadata": {"source": "landmarks", "score": 0.85},
        },
        {
            "id": "doc3",
            "content": "France is a country in Western Europe.",
            "metadata": {"source": "geography", "score": 0.80},
        },
    ]


@pytest.fixture
def test_code_snippets():
    """Standard test code snippets for code generation tasks."""
    return {
        "python": "def add(a, b):\n    return a + b",
        "javascript": "function add(a, b) { return a + b; }",
        "invalid": "this is not valid code {}[]",
        "empty": "",
        "complex": """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
""",
    }


# ============================================================================
# STANDARD ASSERTIONS AND HELPERS
# ============================================================================


@pytest.fixture
def assert_agent_result():
    """Standard assertion helper for agent results."""

    def _assert(result: Dict[str, Any], required_keys: List[str] = None):
        """
        Assert that agent result has required structure.

        Args:
            result: Agent execution result
            required_keys: List of required keys (default: ["answer"])
        """
        assert isinstance(result, dict), "Result must be a dictionary"
        assert len(result) > 0, "Result must not be empty"

        if required_keys is None:
            required_keys = []

        # Check for error handling
        if "error" in result:
            # Error results should have error and error_type
            assert "error" in result, "Error result must have 'error' key"
        else:
            # Success results should have required keys
            for key in required_keys:
                assert key in result, f"Result missing required key: {key}"

    return _assert


@pytest.fixture
def assert_async_strategy():
    """Standard assertion helper for async strategy usage."""

    def _assert(agent: BaseAgent):
        """Assert that agent uses AsyncSingleShotStrategy."""
        assert isinstance(
            agent.strategy, AsyncSingleShotStrategy
        ), f"Expected AsyncSingleShotStrategy, got {type(agent.strategy).__name__}"
        assert inspect.iscoroutinefunction(
            agent.strategy.execute
        ), "Strategy execute method must be async"

    return _assert


@pytest.fixture
def assert_sync_strategy():
    """Standard assertion helper for sync strategy usage."""

    def _assert(agent: BaseAgent):
        """Assert that agent uses SingleShotStrategy."""
        assert isinstance(
            agent.strategy, SingleShotStrategy
        ), f"Expected SingleShotStrategy, got {type(agent.strategy).__name__}"

    return _assert


@pytest.fixture
def assert_shared_memory():
    """Standard assertion helper for shared memory usage."""

    def _assert(
        shared_pool: SharedMemoryPool,
        agent_id: str,
        expected_count: int = 1,
        tags: Optional[List[str]] = None,
    ):
        """
        Assert that shared memory has expected insights.

        Args:
            shared_pool: SharedMemoryPool instance
            agent_id: Agent ID to check
            expected_count: Expected number of insights
            tags: Optional tags to filter by
        """
        insights = shared_pool.read_relevant(
            agent_id=agent_id,
            tags=tags or [],
            exclude_own=False,  # Include own insights for testing
        )

        assert (
            len(insights) >= expected_count
        ), f"Expected at least {expected_count} insights, found {len(insights)}"

        # Verify insight structure
        for insight in insights:
            assert "agent_id" in insight, "Insight missing agent_id"
            assert "content" in insight, "Insight missing content"
            assert "tags" in insight, "Insight missing tags"

    return _assert


@pytest.fixture
def measure_performance():
    """Standard performance measurement helper."""

    def _measure(operation: callable, max_duration_ms: float = 1000) -> float:
        """
        Measure operation performance.

        Args:
            operation: Callable to measure
            max_duration_ms: Maximum allowed duration (default: 1000ms)

        Returns:
            Actual duration in milliseconds
        """
        import time

        start = time.time()
        operation()
        duration_ms = (time.time() - start) * 1000

        assert (
            duration_ms <= max_duration_ms
        ), f"Operation took {duration_ms:.2f}ms, exceeding {max_duration_ms}ms limit"

        return duration_ms

    return _measure


# ============================================================================
# ASYNC TEST HELPERS
# ============================================================================


@pytest.fixture
def run_async():
    """Helper to run async functions in sync tests."""

    def _run(coro):
        """Run coroutine and return result."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    return _run


# ============================================================================
# ERROR HANDLING FIXTURES
# ============================================================================


@pytest.fixture
def error_test_cases():
    """Standard error test cases for validation."""
    return {
        "empty_input": {"input": "", "expected_error": "INVALID_INPUT"},
        "invalid_config": {
            "config": {"model": None},
            "expected_error": "INVALID_CONFIG",
        },
        "timeout": {"timeout": 0.001, "expected_error": "TIMEOUT"},
    }


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


@pytest.fixture
def validate_config():
    """Standard config validation helper."""

    def _validate(config_class: type, config_dict: Dict[str, Any]):
        """
        Validate that config class accepts config dict.

        Args:
            config_class: Config class to test
            config_dict: Config dictionary
        """
        # Create config instance
        config = config_class(**config_dict)

        # Verify all fields are set
        for key, value in config_dict.items():
            if hasattr(config, key):
                assert (
                    getattr(config, key) == value
                ), f"Config field {key} not set correctly"

        return config

    return _validate


@pytest.fixture
def validate_agent_initialization():
    """Standard agent initialization validation helper."""

    def _validate(agent_class: type, config: Any):
        """
        Validate that agent initializes correctly.

        Args:
            agent_class: Agent class to test
            config: Configuration for agent
        """
        # Create agent
        agent = agent_class(config=config)

        # Verify core attributes
        assert hasattr(agent, "config"), "Agent missing config"
        assert hasattr(agent, "signature"), "Agent missing signature"
        assert hasattr(agent, "strategy"), "Agent missing strategy"
        assert hasattr(agent, "agent_id"), "Agent missing agent_id"

        # Verify config auto-extraction worked
        assert isinstance(
            agent.config, (BaseAgentConfig, dict)
        ), "Agent config not properly initialized"

        # Verify signature
        assert isinstance(
            agent.signature, Signature
        ), "Agent signature not properly initialized"

        # Verify strategy
        assert agent.strategy is not None, "Agent strategy not initialized"

        return agent

    return _validate


# ============================================================================
# PYTEST MARKERS FOR EXAMPLE TESTS
# ============================================================================


def pytest_configure(config):
    """Add custom markers for example tests."""
    config.addinivalue_line(
        "markers", "async_migration: Tests for async strategy migration"
    )
    config.addinivalue_line(
        "markers", "memory_integration: Tests for shared memory integration"
    )
    config.addinivalue_line(
        "markers", "ux_improvements: Tests for UX improvement features"
    )
    config.addinivalue_line(
        "markers", "race_conditions: Tests for race condition prevention"
    )
    config.addinivalue_line(
        "markers", "backward_compatibility: Tests for backward compatibility"
    )
