"""
BatchProcessingAgent - Production-Ready Concurrent Batch Processing

Zero-config usage:
    from kaizen.agents import BatchProcessingAgent

    agent = BatchProcessingAgent()

    # Batch processing (primary use case)
    results = await agent.process_batch([
        {"prompt": "Process item 1"},
        {"prompt": "Process item 2"}
    ])
    print(f"Processed {len(results)} items")

    # Single item processing (uses .run())
    result = agent.run(prompt="Process single item")
    print(result["result"])

Progressive configuration:
    agent = BatchProcessingAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.1,
        max_concurrent=20  # Increase throughput
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-3.5-turbo
    KAIZEN_TEMPERATURE=0.1
    KAIZEN_MAX_TOKENS=200
    KAIZEN_MAX_CONCURRENT=10
"""

import os
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from kailash.nodes.base import NodeMetadata

if TYPE_CHECKING:
    from kaizen.tools.registry import ToolRegistry
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.parallel_batch import ParallelBatchStrategy


class BatchProcessingSignature(Signature):
    """Signature for batch data processing."""

    prompt: str = InputField(desc="Data item to process")
    result: str = OutputField(desc="Processed result")


@dataclass
class BatchProcessingConfig:
    """
    Configuration for Batch Processing Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    # LLM configuration
    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "200"))
    )

    # Batch-specific configuration
    max_concurrent: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_CONCURRENT", "10"))
    )

    # Technical configuration
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class BatchProcessingAgent(BaseAgent):
    """
    Production-ready Batch Processing Agent using ParallelBatchStrategy.

    Features:
    - Zero-config with sensible defaults
    - Concurrent batch processing with semaphore limiting
    - Configurable max_concurrent to prevent resource exhaustion
    - Process 1000s of items efficiently
    - Built-in error handling and logging via BaseAgent
    - Maintains result order matching input order

    Inherits from BaseAgent:
    - Signature-based batch processing pattern
    - Parallel execution via ParallelBatchStrategy
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)

    Use Cases:
    - Bulk document analysis and classification
    - Large-scale data transformation
    - High-throughput API processing
    - Batch inference operations
    - ETL pipelines
    - Embarrassingly parallel workloads

    Performance:
    - Concurrent execution with semaphore control
    - Configurable max_concurrent limit (default: 10)
    - Efficient resource utilization without exhaustion
    - Typical throughput: 50-100+ items/sec (mock), 5-10 items/sec (real LLM)

    Usage:
        # Zero-config (easiest)
        import asyncio
        agent = BatchProcessingAgent()

        batch = [{"prompt": f"Process document {i}"} for i in range(100)]
        results = asyncio.run(agent.process_batch(batch))
        print(f"Processed {len(results)} items")

        # With configuration
        agent = BatchProcessingAgent(
            llm_provider="openai",
            model="gpt-4",
            max_concurrent=20
        )

        # Process and inspect results
        batch = [{"prompt": "Analyze sentiment"}, {"prompt": "Extract entities"}]
        results = asyncio.run(agent.process_batch(batch))

        for i, result in enumerate(results):
            print(f"{i+1}. {result.get('result', 'N/A')}")

        # Single item (non-batch)
        single_result = agent.run(prompt="Analyze this text")
        print(single_result.get('result'))
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="BatchProcessingAgent",
        description="Concurrent batch processing with high throughput and semaphore limiting",
        version="1.0.0",
        tags={"ai", "kaizen", "batch", "concurrent", "high-throughput", "parallel"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_concurrent: Optional[int] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[BatchProcessingConfig] = None,
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        **kwargs,
    ):
        """
        Initialize Batch Processing Agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            max_concurrent: Override default max concurrent executions
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = BatchProcessingConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if max_concurrent is not None:
                config = replace(config, max_concurrent=max_concurrent)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or "timeout" not in config.provider_config
        ):
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # Use ParallelBatchStrategy with configured max_concurrent
        strategy = ParallelBatchStrategy(max_concurrent=config.max_concurrent)

        # Initialize BaseAgent
        super().__init__(
            config=config,  # Auto-converted to BaseAgentConfig
            signature=BatchProcessingSignature(),
            strategy=strategy,
            mcp_servers=mcp_servers,
            **kwargs,
        )

        self.batch_config = config
        self.tool_registry = tool_registry

    async def process_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process batch of inputs concurrently.

        Args:
            batch: List of input dictionaries, each with 'prompt' key

        Returns:
            List[Dict[str, Any]]: Results in same order as inputs

        Example:
            >>> import asyncio
            >>> agent = BatchProcessingAgent()
            >>> batch = [
            ...     {"prompt": "Analyze sentiment: Great product!"},
            ...     {"prompt": "Analyze sentiment: Terrible service."}
            ... ]
            >>> results = asyncio.run(agent.process_batch(batch))
            >>> print(f"Processed {len(results)} items")
            Processed 2 items
        """
        if not batch:
            return []

        # Delegate to ParallelBatchStrategy
        results = await self.strategy.execute_batch(self, batch)

        return results


# Convenience function for quick batch processing
async def process_batch_quick(
    items: List[str],
    max_concurrent: int = 10,
    llm_provider: str = "openai",
    model: str = "gpt-3.5-turbo",
) -> List[Dict[str, Any]]:
    """
    Quick batch processing with default configuration.

    Args:
        items: List of prompts to process
        max_concurrent: Maximum concurrent executions
        llm_provider: LLM provider to use
        model: Model to use

    Returns:
        List of processing results

    Example:
        >>> import asyncio
        >>> from kaizen.agents.specialized.batch_processing import process_batch_quick
        >>> results = asyncio.run(process_batch_quick([
        ...     "Summarize: AI is transforming industries",
        ...     "Summarize: Cloud computing enables scalability"
        ... ]))
        >>> print(f"Processed {len(results)} items")
    """
    agent = BatchProcessingAgent(
        max_concurrent=max_concurrent, llm_provider=llm_provider, model=model
    )

    batch = [{"prompt": item} for item in items]
    return await agent.process_batch(batch)
