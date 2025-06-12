"""Example demonstrating MonitoredLLMAgentNode with cost tracking and budget controls.

This example shows how to monitor LLM usage, track costs, and implement
budget controls for enterprise deployments.
"""

from kailash.workflow import Workflow
from kailash.nodes.ai.monitored_llm import MonitoredLLMAgentNode
from kailash.nodes.data import JSONReaderNode


def demonstrate_basic_monitoring():
    """Show basic cost monitoring functionality."""
    print("=== Basic LLM Monitoring ===\n")
    
    # Create monitored LLM node
    llm_node = MonitoredLLMAgentNode(
        name="analyzer",
        prompt="Summarize this text in 2 sentences: {text}",
        model="gpt-3.5-turbo",
        budget_limit=1.0,  # $1 USD limit
        alert_threshold=0.5  # Alert at 50% usage
    )
    
    # Simulate usage
    texts = [
        "The quick brown fox jumps over the lazy dog. This is a classic pangram.",
        "Machine learning is transforming how we process and understand data.",
        "Cloud computing provides scalable infrastructure for modern applications."
    ]
    
    print("Processing texts with cost monitoring...")
    for i, text in enumerate(texts, 1):
        result = llm_node.run(text=text)
        
        if "monitoring" in result:
            monitoring = result["monitoring"]
            print(f"\nRequest {i}:")
            print(f"  Tokens: {monitoring['tokens']['total']}")
            print(f"  Cost: ${monitoring['cost']['total']:.4f}")
            print(f"  Budget used: ${monitoring['budget']['used']:.4f} / ${monitoring['budget']['limit']}")
    
    # Get usage report
    report = llm_node.get_usage_report()
    print("\n📊 Usage Report:")
    print(f"  Total requests: {report['summary']['requests']}")
    print(f"  Total tokens: {report['summary']['total_tokens']}")
    print(f"  Total cost: ${report['summary']['total_cost']}")
    print(f"  Budget remaining: ${report['budget']['remaining']}")


def demonstrate_budget_controls():
    """Show budget limit enforcement."""
    print("\n\n=== Budget Control Demo ===\n")
    
    # Create node with tight budget
    llm_node = MonitoredLLMAgentNode(
        name="limited_llm",
        prompt="Write a detailed analysis of: {topic}",
        model="gpt-4",  # More expensive model
        budget_limit=0.10,  # $0.10 limit
        alert_threshold=0.7
    )
    
    topics = [
        "artificial intelligence",
        "quantum computing",
        "blockchain technology",
        "renewable energy"
    ]
    
    print("Testing budget limits with expensive model...")
    for topic in topics:
        try:
            result = llm_node.run(topic=topic)
            cost = result["monitoring"]["cost"]["total"]
            print(f"✅ Analyzed '{topic}' - Cost: ${cost:.4f}")
        except ValueError as e:
            print(f"❌ Budget exceeded: {e}")
            break
    
    # Show final usage
    report = llm_node.get_usage_report()
    print(f"\nBudget status: {report['budget']['percentage_used']:.1f}% used")


def demonstrate_multi_model_comparison():
    """Compare costs across different models."""
    print("\n\n=== Multi-Model Cost Comparison ===\n")
    
    models = [
        ("gpt-4", "Most capable, highest cost"),
        ("gpt-3.5-turbo", "Good balance of cost/performance"),
        ("claude-3-haiku", "Fast and affordable"),
    ]
    
    prompt = "Explain quantum computing in simple terms"
    
    print("Comparing model costs for same prompt:\n")
    
    for model_name, description in models:
        node = MonitoredLLMAgentNode(
            name=f"compare_{model_name}",
            prompt=prompt,
            model=model_name,
            max_tokens=150
        )
        
        try:
            result = node.run()
            monitoring = result.get("monitoring", {})
            
            print(f"{model_name} ({description}):")
            print(f"  Tokens: {monitoring['tokens']['total']}")
            print(f"  Cost: ${monitoring['cost']['total']:.6f}")
            print(f"  Time: {monitoring['execution_time_ms']:.0f}ms")
            print()
        except:
            print(f"{model_name}: Not available for testing\n")


def demonstrate_workflow_cost_tracking():
    """Show cost tracking across workflow."""
    print("\n\n=== Workflow Cost Tracking ===\n")
    
    workflow = Workflow(
        workflow_id="cost_aware_pipeline",
        name="Cost-Aware AI Pipeline"
    )
    
    # Multiple LLM steps with monitoring
    workflow.add_node(
        "extract",
        MonitoredLLMAgentNode,
        prompt="Extract key facts from: {text}",
        model="gpt-3.5-turbo",
        budget_limit=0.50
    )
    
    workflow.add_node(
        "analyze",
        MonitoredLLMAgentNode,
        prompt="Analyze these facts and identify patterns: {facts}",
        model="gpt-4",
        budget_limit=1.00
    )
    
    workflow.add_node(
        "summarize",
        MonitoredLLMAgentNode,
        prompt="Create executive summary: {analysis}",
        model="gpt-3.5-turbo",
        budget_limit=0.25
    )
    
    # Connect nodes
    workflow.connect("extract", "analyze", {"output": "facts"})
    workflow.connect("analyze", "summarize", {"output": "analysis"})
    
    # Execute with sample data
    sample_text = """
    Recent advances in renewable energy have made solar and wind power 
    increasingly competitive with fossil fuels. Battery storage technology 
    is solving intermittency issues, while smart grids optimize distribution.
    """
    
    print("Executing cost-tracked workflow...")
    result = workflow.execute(text=sample_text)
    
    # Aggregate costs
    total_cost = 0
    print("\nCost breakdown by step:")
    
    for node_id in ["extract", "analyze", "summarize"]:
        if node_id in result:
            monitoring = result[node_id].get("monitoring", {})
            cost = monitoring.get("cost", {}).get("total", 0)
            total_cost += cost
            print(f"  {node_id}: ${cost:.4f}")
    
    print(f"\nTotal workflow cost: ${total_cost:.4f}")


def demonstrate_custom_pricing():
    """Show custom pricing configuration."""
    print("\n\n=== Custom Pricing Configuration ===\n")
    
    # Custom pricing for private/fine-tuned models
    custom_llm = MonitoredLLMAgentNode(
        name="custom_model",
        prompt="Process this request: {input}",
        model="company-fine-tuned-gpt",
        custom_pricing={
            "prompt_token_cost": 0.00005,  # $0.05 per 1K tokens
            "completion_token_cost": 0.00010  # $0.10 per 1K tokens
        },
        cost_multiplier=1.2  # 20% markup for infrastructure
    )
    
    result = custom_llm.run(input="Test custom pricing")
    
    print("Custom model pricing:")
    print(f"  Base cost: ${result['monitoring']['cost']['total']:.6f}")
    print(f"  With 20% markup: ${result['monitoring']['cost']['total'] * 1.2:.6f}")


def demonstrate_usage_analytics():
    """Show detailed usage analytics."""
    print("\n\n=== Usage Analytics ===\n")
    
    # Create node with analytics
    analytics_llm = MonitoredLLMAgentNode(
        name="analytics_demo",
        prompt="Answer: {question}",
        model="gpt-3.5-turbo",
        enable_analytics=True,
        track_history=True,
        history_limit=100
    )
    
    # Simulate various requests
    questions = [
        "What is machine learning?",
        "Explain neural networks",
        "How does backpropagation work?",
        "What are transformers in AI?",
        "Describe attention mechanisms"
    ]
    
    print("Running requests for analytics...")
    for q in questions:
        analytics_llm.run(question=q)
    
    # Get detailed analytics
    report = analytics_llm.get_usage_report()
    analytics = report.get("analytics", {})
    
    print("\n📈 Analytics Report:")
    print(f"  Average tokens/request: {analytics.get('average_tokens_per_request', 0)}")
    print(f"  Average cost/request: ${analytics.get('average_cost_per_request', 0):.4f}")
    print(f"  Average execution time: {analytics.get('average_execution_time_ms', 0):.0f}ms")
    print(f"  Cost per 1K tokens: ${analytics.get('cost_per_1k_tokens', 0):.4f}")
    
    # Recent usage
    print("\n📊 Recent Usage:")
    for usage in report.get("recent_usage", [])[-3:]:
        print(f"  {usage['timestamp']}: {usage['tokens']} tokens, ${usage['cost']:.4f}")


def demonstrate_export_capabilities():
    """Show data export for analysis."""
    print("\n\n=== Usage Data Export ===\n")
    
    # Create node and generate some usage
    export_llm = MonitoredLLMAgentNode(
        name="export_demo",
        prompt="Translate to French: {text}",
        model="gpt-3.5-turbo"
    )
    
    texts = ["Hello", "Good morning", "Thank you"]
    for text in texts:
        export_llm.run(text=text)
    
    # Export as JSON
    json_export = export_llm.export_usage_data(format="json")
    print("JSON Export (truncated):")
    print(json_export[:200] + "...")
    
    # Export as CSV
    csv_export = export_llm.export_usage_data(format="csv")
    print("\nCSV Export:")
    print(csv_export)


def demonstrate_budget_reset():
    """Show budget management features."""
    print("\n\n=== Budget Management ===\n")
    
    # Create node with small budget
    managed_llm = MonitoredLLMAgentNode(
        name="managed",
        prompt="Process: {data}",
        model="gpt-3.5-turbo",
        budget_limit=0.01  # $0.01 limit
    )
    
    # Use up budget
    try:
        managed_llm.run(data="First request")
        managed_llm.run(data="Second request")
    except ValueError:
        print("❌ Budget exceeded as expected")
    
    print(f"Budget used: ${managed_llm._total_cost:.4f}")
    
    # Reset budget
    print("\nResetting budget...")
    managed_llm.reset_budget()
    
    # Can use again
    result = managed_llm.run(data="After reset")
    print("✅ Can process requests after budget reset")
    
    # Full reset
    print("\nFull usage reset...")
    managed_llm.reset_usage()
    report = managed_llm.get_usage_report()
    print(f"Total requests after reset: {report['summary']['requests']}")


if __name__ == "__main__":
    print("=== MonitoredLLMAgentNode Examples ===\n")
    
    # Run demonstrations
    demonstrate_basic_monitoring()
    demonstrate_budget_controls()
    demonstrate_multi_model_comparison()
    # demonstrate_workflow_cost_tracking()  # Commented to avoid actual API calls
    demonstrate_custom_pricing()
    demonstrate_usage_analytics()
    demonstrate_export_capabilities()
    demonstrate_budget_reset()
    
    print("\n\n✅ MonitoredLLMAgentNode provides comprehensive cost control:")
    print("   - Real-time token counting and cost calculation")
    print("   - Budget limits with alerts")
    print("   - Detailed analytics and reporting")
    print("   - Multi-model cost comparison")
    print("   - Export capabilities for analysis")
    print("   - Custom pricing support")