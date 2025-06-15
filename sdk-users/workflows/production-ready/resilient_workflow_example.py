"""Example demonstrating workflow resilience features.

This example shows how to add retry policies, fallback nodes, and circuit breakers
to standard workflows for enterprise-grade reliability.
"""

import asyncio
from datetime import datetime, timezone

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import RetryStrategy, Workflow, apply_resilience_to_workflow


# Apply resilience features to Workflow class
@apply_resilience_to_workflow
class ResilientWorkflow(Workflow):
    """Workflow with resilience features enabled."""

    pass


async def main():
    """Demonstrate resilience patterns in workflows."""

    # Create a resilient workflow
    workflow = ResilientWorkflow(
        workflow_id="resilient_api_pipeline",
        name="Resilient API Pipeline",
        description="Workflow with retry and fallback patterns",
    )

    # Add primary API node
    workflow.add_node(
        "fetch_data",
        HTTPRequestNode,
        url="https://api.example.com/data",
        method="GET",
        headers={"Authorization": "Bearer ${api_key}"},
    )

    # Configure retry policy for API calls
    workflow.configure_retry(
        "fetch_data",
        max_retries=3,
        strategy=RetryStrategy.EXPONENTIAL,
        base_delay=2.0,
        max_delay=30.0,
        retry_on=[ConnectionError, TimeoutError],
    )

    # Add circuit breaker to prevent cascading failures
    workflow.configure_circuit_breaker(
        "fetch_data", failure_threshold=5, success_threshold=2, timeout=60.0
    )

    # Add backup API as fallback
    workflow.add_node(
        "fetch_data_backup",
        HTTPRequestNode,
        url="https://backup.api.example.com/data",
        method="GET",
    )
    workflow.add_fallback("fetch_data", "fetch_data_backup")

    # Add LLM processing with fallback
    workflow.add_node(
        "process_llm", LLMAgentNode, prompt="Analyze this data: {data}", model="gpt-4"
    )

    workflow.add_node(
        "process_llm_fallback",
        LLMAgentNode,
        prompt="Analyze this data: {data}",
        model="claude-3-sonnet",
    )
    workflow.add_fallback("process_llm", "process_llm_fallback")

    # Configure retry for LLM with linear backoff
    workflow.configure_retry(
        "process_llm", max_retries=2, strategy=RetryStrategy.LINEAR, base_delay=5.0
    )

    # Add error handler
    workflow.add_node(
        "error_handler",
        PythonCodeNode.from_function(
            name="handle_errors",
            func=lambda error, context: {
                "status": "error",
                "message": str(error),
                "context": context,
                "handled_at": datetime.now(timezone.utc).isoformat(),
            },
        ),
    )

    # Connect nodes
    workflow.connect("fetch_data", "process_llm", {"response": "data"})

    # Example: Execute with monitoring
    try:
        result = await workflow.execute(api_key="test_key_123")
        print("Workflow succeeded:", result)
    except Exception as e:
        print("Workflow failed:", e)

        # Check metrics and dead letter queue
        metrics = workflow.get_resilience_metrics()
        print("\nResilience Metrics:")
        print(f"- Circuit breakers: {metrics['circuit_breakers']}")
        print(f"- Dead letter queue size: {metrics['dead_letter_queue_size']}")

        # Process dead letter queue
        dlq = workflow.get_dead_letter_queue()
        for failed_execution in dlq:
            print(f"\nFailed execution at {failed_execution['timestamp']}:")
            print(f"- Node: {failed_execution['node']}")
            print(f"- Error: {failed_execution['error']}")
            print(f"- Attempts: {failed_execution['attempts']}")

    # Example: Manual circuit breaker control
    if workflow._circuit_breakers.get("fetch_data", {}).get("state") == "open":
        print("\nCircuit breaker is open, waiting before reset...")
        await asyncio.sleep(5)
        workflow.reset_circuit_breaker("fetch_data")
        print("Circuit breaker reset")


def demonstrate_retry_strategies():
    """Show different retry strategies."""
    from kailash.workflow.resilience import RetryPolicy

    policies = {
        "immediate": RetryPolicy(strategy=RetryStrategy.IMMEDIATE, max_retries=3),
        "linear": RetryPolicy(strategy=RetryStrategy.LINEAR, base_delay=2.0),
        "exponential": RetryPolicy(strategy=RetryStrategy.EXPONENTIAL, base_delay=1.0),
        "fibonacci": RetryPolicy(strategy=RetryStrategy.FIBONACCI, base_delay=1.5),
    }

    print("\nRetry Strategy Delays:")
    for name, policy in policies.items():
        print(f"\n{name.capitalize()} Strategy:")
        for attempt in range(1, 5):
            delay = policy.calculate_delay(attempt)
            print(f"  Attempt {attempt}: {delay:.1f}s delay")


def demonstrate_enterprise_patterns():
    """Show enterprise resilience patterns."""

    # Pattern 1: Multi-region failover
    workflow = ResilientWorkflow(
        workflow_id="multi_region", name="Multi-Region Service"
    )

    regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]

    # Add nodes for each region
    for i, region in enumerate(regions):
        workflow.add_node(
            f"service_{region}",
            HTTPRequestNode,
            url=f"https://{region}.service.example.com/api",
        )

        # Configure faster retries for regional failover
        workflow.configure_retry(
            f"service_{region}", max_retries=1, strategy=RetryStrategy.IMMEDIATE
        )

        # Add as fallback for previous region
        if i > 0:
            workflow.add_fallback(f"service_{regions[i-1]}", f"service_{region}")

    # Pattern 2: Graceful degradation
    workflow2 = ResilientWorkflow(
        workflow_id="graceful_degradation", name="Feature Degradation"
    )

    # Primary feature - full functionality
    workflow2.add_node("full_analysis", LLMAgentNode, model="gpt-4", max_tokens=2000)

    # Degraded feature - reduced functionality
    workflow2.add_node(
        "basic_analysis", LLMAgentNode, model="gpt-3.5-turbo", max_tokens=500
    )

    # Minimal feature - emergency fallback
    workflow2.add_node(
        "minimal_analysis",
        PythonCodeNode.from_function(
            name="rule_based_analysis",
            func=lambda text: {
                "analysis": "Basic rule-based analysis",
                "confidence": 0.5,
            },
        ),
    )

    # Configure fallback chain
    workflow2.add_fallback("full_analysis", "basic_analysis")
    workflow2.add_fallback("basic_analysis", "minimal_analysis")

    print("\n✅ Enterprise patterns configured")


if __name__ == "__main__":
    print("=== Workflow Resilience Features Demo ===\n")

    # Show retry strategies
    demonstrate_retry_strategies()

    # Show enterprise patterns
    demonstrate_enterprise_patterns()

    # Run async example
    print("\n\nRunning resilient workflow example...")
    # asyncio.execute(main())  # Uncomment to run with real services

    print("\n✅ Resilience features can be added to any workflow!")
    print("   No need for a separate ResilientWorkflow class")
    print(
        "   Just use @apply_resilience_to_workflow decorator or configure on standard Workflow"
    )
