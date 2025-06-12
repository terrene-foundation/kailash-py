"""Example demonstrating LLMAgentNode with integrated monitoring features.

This example shows how to use the LLMAgentNode with its built-in monitoring
capabilities for token usage tracking, cost estimation, and budget controls.
"""

import json
from kailash import setup_logging
from kailash.nodes.ai import LLMAgentNode
from kailash.workflow import Workflow


def create_monitored_llm_workflow() -> Workflow:
    """Create a workflow with monitored LLM agent."""
    workflow = Workflow(name="monitored_llm_workflow")
    
    # Add LLM agent with monitoring enabled
    workflow.add_node(
        "llm_analyzer",
        LLMAgentNode(
            # Standard LLM configuration
            provider="openai",
            model="gpt-4",
            
            # Enable monitoring features
            enable_monitoring=True,
            budget_limit=10.0,  # $10 USD limit
            alert_threshold=0.8,  # Alert at 80% of budget
            track_history=True,
            history_limit=100,
            
            # Optional: Custom pricing for specific models
            # custom_pricing={
            #     "prompt_token_cost": 0.00003,
            #     "completion_token_cost": 0.00006
            # }
        )
    )
    
    return workflow


def demonstrate_basic_monitoring():
    """Demonstrate basic LLM usage with monitoring."""
    print("\n=== Basic LLM Monitoring ===")
    
    # Create LLM agent with monitoring
    llm_agent = LLMAgentNode(
        enable_monitoring=True,
        budget_limit=5.0,
        alert_threshold=0.8
    )
    
    # Simulate multiple requests
    messages_list = [
        [{"role": "user", "content": "Explain quantum computing in simple terms"}],
        [{"role": "user", "content": "What are the benefits of renewable energy?"}],
        [{"role": "user", "content": "How does machine learning work?"}],
    ]
    
    for i, messages in enumerate(messages_list, 1):
        print(f"\nRequest {i}:")
        try:
            result = llm_agent.run(
                provider="mock",
                model="gpt-4",
                messages=messages,
                enable_monitoring=True
            )
            
            if result["success"]:
                print(f"Response: {result['response']['content'][:100]}...")
                
                # Check if monitoring data is available
                if "monitoring" in result["usage"]:
                    monitoring = result["usage"]["monitoring"]
                    print(f"Tokens used: {monitoring['tokens']['total']}")
                    print(f"Cost: ${monitoring['cost']['total']:.4f} USD")
                    print(f"Execution time: {monitoring['execution_time_ms']:.1f}ms")
                    print(f"Budget used: ${monitoring['budget']['used']:.2f}/${monitoring['budget']['limit']:.2f}")
            else:
                print(f"Error: {result['error']}")
                
        except Exception as e:
            print(f"Exception: {e}")
    
    # Get usage report
    report = llm_agent.get_usage_report()
    print("\n=== Usage Report ===")
    print(json.dumps(report, indent=2))


def demonstrate_budget_controls():
    """Demonstrate budget limits and alerts."""
    print("\n=== Budget Control Demonstration ===")
    
    # Create agent with low budget for demonstration
    llm_agent = LLMAgentNode(
        enable_monitoring=True,
        budget_limit=0.01,  # $0.01 USD - very low for demo
        alert_threshold=0.5  # Alert at 50%
    )
    
    # Simulate requests until budget exceeded
    for i in range(5):
        try:
            result = llm_agent.run(
                provider="mock",
                model="gpt-4",
                messages=[{"role": "user", "content": f"Request {i+1}"}],
                enable_monitoring=True
            )
            
            if result["success"] and "monitoring" in result["usage"]:
                monitoring = result["usage"]["monitoring"]
                print(f"\nRequest {i+1}: Cost ${monitoring['cost']['total']:.6f}")
                print(f"Total spent: ${monitoring['budget']['used']:.4f}/${monitoring['budget']['limit']:.2f}")
                
                # Check if approaching limit
                if monitoring['budget']['remaining'] and monitoring['budget']['remaining'] < 0.005:
                    print("⚠️ Approaching budget limit!")
                    
        except ValueError as e:
            print(f"\n❌ Budget exceeded: {e}")
            break


def demonstrate_analytics():
    """Demonstrate usage analytics and reporting."""
    print("\n=== Usage Analytics ===")
    
    # Create agent with history tracking
    llm_agent = LLMAgentNode(
        enable_monitoring=True,
        track_history=True,
        history_limit=50
    )
    
    # Simulate various model usage
    test_cases = [
        ("gpt-3.5-turbo", "Short query about weather"),
        ("gpt-4", "Complex analysis of market trends with detailed insights"),
        ("claude-3-haiku", "Quick translation task"),
        ("gpt-4-turbo", "Generate comprehensive report on AI developments"),
    ]
    
    for model, content in test_cases:
        result = llm_agent.run(
            provider="mock",
            model=model,
            messages=[{"role": "user", "content": content}],
            enable_monitoring=True
        )
        
        if result["success"]:
            print(f"✓ {model}: Processed '{content[:30]}...'")
    
    # Get comprehensive report
    report = llm_agent.get_usage_report()
    
    print("\n=== Analytics Report ===")
    if "summary" in report:
        summary = report["summary"]
        print(f"Total requests: {summary['requests']}")
        print(f"Total tokens: {summary['total_tokens']:,}")
        print(f"Total cost: ${summary['total_cost']:.4f}")
        
    if "analytics" in report:
        analytics = report["analytics"]
        print(f"\nAverage tokens/request: {analytics['average_tokens_per_request']}")
        print(f"Average cost/request: ${analytics['average_cost_per_request']:.4f}")
        print(f"Average execution time: {analytics['average_execution_time_ms']:.1f}ms")
        print(f"Cost per 1K tokens: ${analytics['cost_per_1k_tokens']:.4f}")
    
    # Export data
    print("\n=== Export Options ===")
    json_export = llm_agent.export_usage_data(format="json")
    print("JSON export (first 200 chars):")
    print(json_export[:200] + "...")
    
    csv_export = llm_agent.export_usage_data(format="csv")
    print("\nCSV export (first 3 lines):")
    print("\n".join(csv_export.split("\n")[:3]))


def demonstrate_custom_pricing():
    """Demonstrate custom pricing configuration."""
    print("\n=== Custom Pricing Configuration ===")
    
    # Create agent with custom pricing
    llm_agent = LLMAgentNode(
        enable_monitoring=True,
        custom_pricing={
            "prompt_token_cost": 0.00002,  # $0.02 per 1K tokens
            "completion_token_cost": 0.00004  # $0.04 per 1K tokens
        },
        cost_multiplier=1.2  # Add 20% markup
    )
    
    result = llm_agent.run(
        provider="mock",
        model="custom-model",
        messages=[{"role": "user", "content": "Calculate with custom pricing"}],
        enable_monitoring=True
    )
    
    if result["success"] and "monitoring" in result["usage"]:
        monitoring = result["usage"]["monitoring"]
        print(f"Custom pricing calculation:")
        print(f"Prompt cost: ${monitoring['cost']['prompt']:.6f}")
        print(f"Completion cost: ${monitoring['cost']['completion']:.6f}")
        print(f"Total cost (with 20% markup): ${monitoring['cost']['total']:.6f}")


def demonstrate_reset_functions():
    """Demonstrate reset functionality."""
    print("\n=== Reset Functions ===")
    
    llm_agent = LLMAgentNode(
        enable_monitoring=True,
        budget_limit=1.0
    )
    
    # Make some requests
    for i in range(3):
        llm_agent.run(
            provider="mock",
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"Request {i+1}"}],
            enable_monitoring=True
        )
    
    # Check usage before reset
    report_before = llm_agent.get_usage_report()
    print(f"Before reset - Total cost: ${report_before['summary']['total_cost']:.4f}")
    print(f"Before reset - Total tokens: {report_before['summary']['total_tokens']}")
    
    # Reset budget only
    llm_agent.reset_budget()
    print("\n✓ Budget reset")
    
    # Make another request
    llm_agent.run(
        provider="mock",
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "After budget reset"}],
        enable_monitoring=True
    )
    
    # Reset all usage
    llm_agent.reset_usage()
    print("✓ All usage reset")
    
    # Check after full reset
    report_after = llm_agent.get_usage_report()
    print(f"\nAfter full reset - Total cost: ${report_after['summary']['total_cost']:.4f}")
    print(f"After full reset - Total tokens: {report_after['summary']['total_tokens']}")


def main():
    """Run all monitoring demonstrations."""
    setup_logging()
    
    print("LLMAgentNode Monitoring Features Demonstration")
    print("=" * 50)
    
    # Run demonstrations
    demonstrate_basic_monitoring()
    demonstrate_budget_controls()
    demonstrate_analytics()
    demonstrate_custom_pricing()
    demonstrate_reset_functions()
    
    # Show integration in workflow
    print("\n=== Workflow Integration ===")
    workflow = create_monitored_llm_workflow()
    print(f"Created workflow with monitored LLM: {workflow.name}")
    print("Nodes:", list(workflow.nodes.keys()))
    
    print("\n=== Key Features ===")
    print("✓ Token counting for all requests")
    print("✓ Cost estimation with model-specific pricing")
    print("✓ Budget limits with automatic enforcement")
    print("✓ Alert thresholds for proactive monitoring")
    print("✓ Usage history tracking with analytics")
    print("✓ Export capabilities (JSON/CSV)")
    print("✓ Custom pricing support")
    print("✓ Reset functions for billing cycles")


if __name__ == "__main__":
    main()