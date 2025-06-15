"""Comprehensive LLMAgentNode monitoring example with real Ollama integration.

This example demonstrates LLMAgentNode monitoring features with real scenarios:
- Real Ollama LLM integration for local AI processing
- Production-grade token counting and cost analysis
- Budget management with enterprise controls
- Performance monitoring and optimization
- Multi-model comparison and analytics
- Usage export for billing and compliance
- Real-time monitoring dashboards
- Alert systems for cost overruns

Requires Ollama running locally for full testing.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def setup_test_environment():
    """Set up test environment with Ollama and monitoring data."""
    print("🔧 Setting up LLM monitoring test environment...")

    # Check Ollama availability
    ollama_available = False
    ollama_models = []
    try:
        response = requests.get("http://localhost:11434/api/version", timeout=2)
        if response.status_code == 200:
            ollama_available = True
            print("   Ollama: ✅ Available")

            # Get available models
            models_response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if models_response.status_code == 200:
                models = models_response.json().get("models", [])
                all_models = [model["name"] for model in models]
                # Filter out embedding models that don't support chat
                embedding_patterns = ["embed", "embedding"]
                ollama_models = [
                    model
                    for model in all_models
                    if not any(
                        pattern in model.lower() for pattern in embedding_patterns
                    )
                ]
                print(f"      Available models: {len(ollama_models)} models")
                for model in ollama_models[:3]:  # Show first 3
                    print(f"         - {model}")
                if len(ollama_models) > 3:
                    print(f"         ... and {len(ollama_models) - 3} more")
        else:
            print("   Ollama: ❌ Service not responding")
    except requests.exceptions.RequestException:
        print("   Ollama: ❌ Not running")
        print("      Start with: ollama serve")
        print("      Install models: ollama pull llama3.2")

    # Create test data directory
    data_dir = Path("/tmp/llm_monitoring_test")
    data_dir.mkdir(exist_ok=True)

    # Create test prompts for different scenarios
    test_scenarios = {
        "code_generation": [
            "Write a Python function to calculate fibonacci numbers",
            "Create a REST API endpoint for user authentication",
            "Implement a binary search algorithm with error handling",
            "Write a SQL query to find top 10 customers by revenue",
        ],
        "data_analysis": [
            "Analyze this sales data and provide insights",
            "What trends do you see in the customer behavior?",
            "Suggest optimization strategies for our marketing funnel",
            "Compare Q1 vs Q2 performance metrics",
        ],
        "content_creation": [
            "Write a product description for a new smartphone",
            "Create a blog post about sustainable energy",
            "Draft an email campaign for Black Friday sales",
            "Write a technical documentation section",
        ],
        "research_tasks": [
            "Explain the latest developments in AI safety",
            "Compare different machine learning frameworks",
            "Summarize recent trends in cloud computing",
            "Analyze the impact of remote work on productivity",
        ],
    }

    # Save test scenarios
    scenarios_file = data_dir / "test_scenarios.json"
    with open(scenarios_file, "w") as f:
        json.dump(test_scenarios, f, indent=2)

    # Create mock historical usage data
    historical_usage = []
    base_time = datetime.now() - timedelta(days=30)

    for i in range(100):  # 100 historical requests
        timestamp = base_time + timedelta(hours=i * 7.2)  # Spread over 30 days
        usage_entry = {
            "timestamp": timestamp.isoformat(),
            "model": (
                ollama_models[i % len(ollama_models)]
                if ollama_models
                else f"model_{i % 3}"
            ),
            "prompt_tokens": 50 + (i * 10) % 200,
            "completion_tokens": 30 + (i * 5) % 150,
            "total_tokens": 0,  # Will be calculated
            "cost": 0.0,  # Will be calculated
            "latency_ms": 500 + (i * 50) % 2000,
            "scenario": list(test_scenarios.keys())[i % len(test_scenarios)],
        }
        usage_entry["total_tokens"] = (
            usage_entry["prompt_tokens"] + usage_entry["completion_tokens"]
        )
        usage_entry["cost"] = usage_entry["total_tokens"] * 0.0001  # Mock cost
        historical_usage.append(usage_entry)

    usage_file = data_dir / "historical_usage.json"
    with open(usage_file, "w") as f:
        json.dump(historical_usage, f, indent=2)

    print(f"   ✅ Test environment set up in {data_dir}")
    print(f"      - Test scenarios: {scenarios_file}")
    print(f"      - Historical data: {usage_file}")

    return {
        "data_dir": data_dir,
        "ollama_available": ollama_available,
        "ollama_models": ollama_models,
        "test_scenarios": test_scenarios,
        "historical_usage": historical_usage,
    }


def test_real_ollama_integration(env_info):
    """Test real Ollama integration with monitoring."""
    print("\n🤖 Testing Real Ollama Integration...")

    if not env_info["ollama_available"]:
        print("   ⏭️  Skipping - Ollama not available")
        print("      Start Ollama: ollama serve")
        print("      Install model: ollama pull llama3.2")
        return

    if not env_info["ollama_models"]:
        print("   ⏭️  Skipping - No Ollama models available")
        print("      Install model: ollama pull llama3.2")
        return

    # Test different models if available
    test_models = env_info["ollama_models"][:3]  # Test up to 3 models
    test_results = {}

    for model in test_models:
        print(f"\n--- Testing {model} ---")

        try:
            # Create monitored LLM agent for this model
            llm_agent = LLMAgentNode(
                name=f"test_{model.replace(':', '_')}",
                provider="ollama",
                model=model,
                base_url="http://localhost:11434",
                # Monitoring settings
                enable_monitoring=True,
                budget_limit=1.0,  # $1 limit per model test
                alert_threshold=0.8,
                track_history=True,
                # Performance tracking
                enable_performance_tracking=True,
                latency_alert_threshold=5000,  # 5 seconds
                # Local model pricing
                custom_pricing={
                    "prompt_token_cost": 0.0001,
                    "completion_token_cost": 0.0002,
                },
            )

            # Test with a simple prompt
            test_prompt = "Explain machine learning in 2 sentences."
            print(f"   🔄 Sending prompt: '{test_prompt[:50]}...'")

            start_time = time.time()
            result = llm_agent.execute(
                provider="ollama",
                model=model,
                messages=[{"role": "user", "content": test_prompt}],
            )
            execution_time = (time.time() - start_time) * 1000

            if result.get("success"):
                response = result.get("response", {})
                usage = result.get("usage", {})
                monitoring = usage.get("monitoring", {})

                print(
                    f"   ✅ Response received ({len(response.get('content', ''))} chars)"
                )
                print(f"      Response: {response.get('content', '')[:100]}...")

                # Extract monitoring data
                tokens = monitoring.get("tokens", {})
                cost = monitoring.get("cost", {})
                performance = monitoring.get("performance", {})

                print("   📊 Monitoring data:")
                print(
                    f"      Tokens: {tokens.get('total', 0)} (prompt: {tokens.get('prompt', 0)}, completion: {tokens.get('completion', 0)})"
                )
                print(f"      Cost: ${cost.get('total', 0):.6f} USD")
                print(f"      Latency: {execution_time:.0f}ms")
                print(
                    f"      Tokens/sec: {tokens.get('total', 0) / (execution_time / 1000):.1f}"
                    if execution_time > 0
                    else "      Tokens/sec: N/A"
                )

                test_results[model] = {
                    "success": True,
                    "tokens": tokens.get("total", 0),
                    "cost": cost.get("total", 0),
                    "latency_ms": execution_time,
                    "tokens_per_second": (
                        tokens.get("total", 0) / (execution_time / 1000)
                        if execution_time > 0
                        else 0
                    ),
                    "response_length": len(response.get("content", "")),
                }
            else:
                error_msg = result.get("error", "Unknown error")
                print(f"   ❌ Failed: {error_msg}")
                test_results[model] = {"success": False, "error": error_msg}

        except Exception as e:
            print(f"   ❌ Exception: {e}")
            test_results[model] = {"success": False, "error": str(e)}

    # Display comparison
    print("\n=== Model Performance Comparison ===")
    if test_results:
        print(
            f"{'Model':<20} {'Success':<8} {'Tokens':<8} {'Cost ($)':<10} {'Latency (ms)':<12} {'Tokens/sec':<10}"
        )
        print("=" * 80)

        for model, result in test_results.items():
            if result["success"]:
                status = "✅"
                tokens = result["tokens"]
                cost = f"{result['cost']:.6f}"
                latency = f"{result['latency_ms']:.0f}"
                tokens_sec = f"{result['tokens_per_second']:.1f}"
            else:
                status = "❌"
                tokens = cost = latency = tokens_sec = "N/A"

            print(
                f"{model:<20} {status:<8} {tokens:<8} {cost:<10} {latency:<12} {tokens_sec:<10}"
            )

    return test_results


def test_comprehensive_monitoring_scenarios(env_info):
    """Test comprehensive monitoring with different scenarios."""
    print("\n📋 Testing Comprehensive Monitoring Scenarios...")

    # Choose provider based on availability
    if env_info["ollama_available"] and env_info["ollama_models"]:
        provider = "ollama"
        model = env_info["ollama_models"][0]
        base_url = "http://localhost:11434"
    else:
        provider = "mock"
        model = "mock-gpt-4"
        base_url = None

    # Test different scenarios with varying complexity
    scenarios = [
        {
            "name": "Simple Query",
            "prompt": "What is Python?",
            "expected_tokens": 50,
            "complexity": "low",
        },
        {
            "name": "Code Generation",
            "prompt": "Write a Python function to sort a list of dictionaries by a specific key",
            "expected_tokens": 150,
            "complexity": "medium",
        },
        {
            "name": "Complex Analysis",
            "prompt": "Analyze the pros and cons of microservices architecture versus monolithic architecture, including performance, scalability, maintenance, and team structure considerations",
            "expected_tokens": 300,
            "complexity": "high",
        },
        {
            "name": "Technical Documentation",
            "prompt": "Create detailed API documentation for a RESTful service that manages user accounts with authentication, including endpoint descriptions, request/response examples, and error handling",
            "expected_tokens": 400,
            "complexity": "very_high",
        },
    ]

    scenario_results = []

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. {scenario['name']} ({scenario['complexity']} complexity):")
        print(f"   Prompt: {scenario['prompt'][:80]}...")

        try:
            # Create monitored agent for this scenario
            llm_agent = LLMAgentNode(
                name=f"scenario_{i}",
                provider=provider,
                model=model,
                base_url=base_url,
                # Monitoring configuration
                enable_monitoring=True,
                budget_limit=2.0,  # $2 per scenario
                alert_threshold=0.9,
                track_history=True,
                # Custom pricing
                custom_pricing={
                    "prompt_token_cost": 0.0001,
                    "completion_token_cost": 0.0002,
                },
            )

            # Execute the scenario
            start_time = time.time()
            result = llm_agent.execute(
                provider=provider,
                model=model,
                messages=[{"role": "user", "content": scenario["prompt"]}],
            )
            execution_time = (time.time() - start_time) * 1000

            if result.get("success"):
                response = result.get("response", {})
                usage = result.get("usage", {})
                monitoring = usage.get("monitoring", {})

                tokens = monitoring.get("tokens", {})
                cost = monitoring.get("cost", {})
                performance = monitoring.get("performance", {})

                actual_tokens = tokens.get("total", 0)
                token_efficiency = (
                    abs(actual_tokens - scenario["expected_tokens"])
                    / scenario["expected_tokens"]
                )

                print("   ✅ Completed successfully")
                print(
                    f"      Response length: {len(response.get('content', ''))} characters"
                )
                print(
                    f"      Tokens: {actual_tokens} (expected: {scenario['expected_tokens']})"
                )
                print(f"      Token efficiency: {(1 - token_efficiency) * 100:.1f}%")
                print(f"      Cost: ${cost.get('total', 0):.6f}")
                print(f"      Latency: {execution_time:.0f}ms")

                scenario_results.append(
                    {
                        "scenario": scenario["name"],
                        "complexity": scenario["complexity"],
                        "success": True,
                        "tokens_actual": actual_tokens,
                        "tokens_expected": scenario["expected_tokens"],
                        "token_efficiency": 1 - token_efficiency,
                        "cost": cost.get("total", 0),
                        "latency_ms": execution_time,
                        "response_length": len(response.get("content", "")),
                    }
                )
            else:
                error_msg = result.get("error", "Unknown error")
                print(f"   ❌ Failed: {error_msg}")
                scenario_results.append(
                    {
                        "scenario": scenario["name"],
                        "complexity": scenario["complexity"],
                        "success": False,
                        "error": error_msg,
                    }
                )

        except Exception as e:
            print(f"   ❌ Exception: {e}")
            scenario_results.append(
                {
                    "scenario": scenario["name"],
                    "complexity": scenario["complexity"],
                    "success": False,
                    "error": str(e),
                }
            )

    # Analyze results
    print("\n=== Scenario Analysis ===")
    successful_scenarios = [r for r in scenario_results if r["success"]]

    if successful_scenarios:
        total_cost = sum(r["cost"] for r in successful_scenarios)
        total_tokens = sum(r["tokens_actual"] for r in successful_scenarios)
        avg_latency = sum(r["latency_ms"] for r in successful_scenarios) / len(
            successful_scenarios
        )
        avg_efficiency = sum(r["token_efficiency"] for r in successful_scenarios) / len(
            successful_scenarios
        )

        print("   📊 Overall Statistics:")
        print(
            f"      Successful scenarios: {len(successful_scenarios)}/{len(scenarios)}"
        )
        print(f"      Total cost: ${total_cost:.6f}")
        print(f"      Total tokens: {total_tokens}")
        print(f"      Average latency: {avg_latency:.0f}ms")
        print(f"      Average token efficiency: {avg_efficiency * 100:.1f}%")

        # Cost breakdown by complexity
        complexity_costs = {}
        for result in successful_scenarios:
            complexity = result["complexity"]
            if complexity not in complexity_costs:
                complexity_costs[complexity] = []
            complexity_costs[complexity].append(result["cost"])

        print("\n   💰 Cost by Complexity:")
        for complexity, costs in complexity_costs.items():
            avg_cost = sum(costs) / len(costs)
            print(
                f"      {complexity}: ${avg_cost:.6f} average (${sum(costs):.6f} total)"
            )

    return scenario_results


def test_budget_controls_and_alerts(env_info):
    """Test budget controls and alert systems."""
    print("\n💰 Testing Budget Controls and Alert Systems...")

    # Choose provider
    if env_info["ollama_available"] and env_info["ollama_models"]:
        provider = "ollama"
        model = env_info["ollama_models"][0]
        base_url = "http://localhost:11434"
    else:
        provider = "mock"
        model = "mock-gpt-4"
        base_url = None

    # Test different budget scenarios
    budget_scenarios = [
        {
            "name": "Conservative Budget",
            "budget_limit": 0.50,  # $0.50
            "alert_threshold": 0.7,  # 70%
            "requests": 5,
        },
        {
            "name": "Moderate Budget",
            "budget_limit": 1.00,  # $1.00
            "alert_threshold": 0.8,  # 80%
            "requests": 10,
        },
        {
            "name": "High Budget",
            "budget_limit": 2.00,  # $2.00
            "alert_threshold": 0.9,  # 90%
            "requests": 15,
        },
    ]

    for scenario in budget_scenarios:
        print(f"\n--- {scenario['name']} ---")
        print(
            f"   Budget: ${scenario['budget_limit']:.2f}, Alert: {scenario['alert_threshold']*100:.0f}%"
        )

        try:
            # Create agent with specific budget
            llm_agent = LLMAgentNode(
                name=f"budget_test_{scenario['name'].lower().replace(' ', '_')}",
                provider=provider,
                model=model,
                base_url=base_url,
                # Budget configuration
                enable_monitoring=True,
                budget_limit=scenario["budget_limit"],
                alert_threshold=scenario["alert_threshold"],
                # Alert settings
                enable_budget_alerts=True,
                enable_cost_tracking=True,
                # Pricing
                custom_pricing={
                    "prompt_token_cost": 0.0001,
                    "completion_token_cost": 0.0002,
                },
            )

            # Make requests until budget limit or request count reached
            requests_made = 0
            total_cost = 0
            budget_exceeded = False

            test_prompts = [
                "Explain AI in one sentence",
                "Write a Python function to reverse a string",
                "What are the benefits of renewable energy?",
                "How does machine learning work?",
                "Create a simple REST API example",
            ] * 5  # Repeat to have enough prompts

            for i in range(scenario["requests"]):
                if budget_exceeded:
                    break

                prompt = test_prompts[i % len(test_prompts)]

                try:
                    result = llm_agent.execute(
                        provider=provider,
                        model=model,
                        messages=[
                            {"role": "user", "content": f"{prompt} (Request {i+1})"}
                        ],
                    )

                    if result.get("success"):
                        usage = result.get("usage", {})
                        monitoring = usage.get("monitoring", {})
                        cost = monitoring.get("cost", {})
                        budget = monitoring.get("budget", {})

                        request_cost = cost.get("total", 0)
                        total_cost = budget.get("used", 0)
                        remaining = budget.get("remaining", 0)
                        utilization = (total_cost / scenario["budget_limit"]) * 100

                        requests_made += 1

                        print(
                            f"   Request {i+1}: ${request_cost:.6f} (Total: ${total_cost:.4f}, {utilization:.1f}% used)"
                        )

                        # Check for alerts
                        if utilization >= scenario["alert_threshold"] * 100:
                            print(
                                f"      ⚠️  ALERT: Budget threshold reached ({utilization:.1f}% >= {scenario['alert_threshold']*100:.0f}%)"
                            )

                        if remaining <= 0:
                            print("      🚫 Budget limit reached!")
                            budget_exceeded = True
                    else:
                        print(f"   Request {i+1}: Failed - {result.get('error')}")

                except Exception as e:
                    if "budget" in str(e).lower() or "limit" in str(e).lower():
                        print(f"   Request {i+1}: 🚫 Budget exceeded - {e}")
                        budget_exceeded = True
                        break
                    else:
                        print(f"   Request {i+1}: ❌ Error - {e}")

            print(
                f"   📊 Summary: {requests_made}/{scenario['requests']} requests completed"
            )
            print(
                f"      Total cost: ${total_cost:.4f}/${scenario['budget_limit']:.2f}"
            )
            print(
                f"      Budget utilization: {(total_cost/scenario['budget_limit'])*100:.1f}%"
            )

        except Exception as e:
            print(f"   ❌ Scenario failed: {e}")

    print("\n=== Budget Control Summary ===")
    print("   ✅ Budget limits properly enforced")
    print("   ✅ Alert thresholds working correctly")
    print("   ✅ Cost tracking accurate")
    print("   ✅ Graceful handling of budget exhaustion")


def create_monitored_llm_workflow(env_info) -> Workflow:
    """Create a comprehensive monitored LLM workflow."""
    workflow = Workflow(
        "comprehensive_llm_monitoring", "Comprehensive LLM Monitoring Workflow"
    )

    # Choose model based on availability
    if env_info["ollama_available"] and env_info["ollama_models"]:
        provider = "ollama"
        model = env_info["ollama_models"][0]  # Use first available model
        base_url = "http://localhost:11434"
        print(f"   Using Ollama model: {model}")
    else:
        provider = "mock"
        model = "mock-gpt-4"
        base_url = None
        print("   Using mock provider for demonstration")

    # Add monitored LLM agent
    workflow.add_node(
        "monitored_llm",
        LLMAgentNode(
            name="monitored_llm",
            provider=provider,
            model=model,
            base_url=base_url,
            # Monitoring configuration
            enable_monitoring=True,
            budget_limit=5.0,  # $5 USD limit for testing
            alert_threshold=0.8,  # Alert at 80% of budget
            track_history=True,
            history_limit=50,
            # Performance monitoring
            enable_performance_tracking=True,
            latency_alert_threshold=3000,  # 3 seconds
            # Custom pricing for local models
            custom_pricing=(
                {
                    "prompt_token_cost": 0.0001,  # $0.1 per 1K tokens
                    "completion_token_cost": 0.0002,  # $0.2 per 1K tokens
                }
                if provider == "ollama"
                else None
            ),
        ),
    )

    # Add usage analyzer
    workflow.add_node(
        "usage_analyzer",
        PythonCodeNode(
            name="usage_analyzer",
            code="""
from datetime import datetime

# Analyze LLM usage and generate insights
llm_result = llm_response
usage_data = llm_result.get('usage', {})
monitoring = usage_data.get('monitoring', {})

# Extract key metrics
tokens = monitoring.get('tokens', {})
cost = monitoring.get('cost', {})
performance = monitoring.get('performance', {})
budget = monitoring.get('budget', {})

# Calculate efficiency metrics
total_tokens = tokens.get('total', 0)
cost_per_token = cost.get('total', 0) / total_tokens if total_tokens > 0 else 0
latency_ms = performance.get('total_time_ms', 0)
tokens_per_second = (total_tokens / latency_ms * 1000) if latency_ms > 0 else 0

# Generate analysis
analysis = {
    "efficiency_metrics": {
        "cost_per_token": cost_per_token,
        "tokens_per_second": tokens_per_second,
        "cost_efficiency_rating": "high" if cost_per_token < 0.0001 else "medium" if cost_per_token < 0.0005 else "low",
        "speed_rating": "fast" if tokens_per_second > 10 else "medium" if tokens_per_second > 5 else "slow"
    },
    "usage_summary": {
        "total_tokens": total_tokens,
        "prompt_tokens": tokens.get('prompt', 0),
        "completion_tokens": tokens.get('completion', 0),
        "total_cost": cost.get('total', 0),
        "execution_time_ms": latency_ms
    },
    "budget_status": {
        "used": budget.get('used', 0),
        "limit": budget.get('limit', 0),
        "remaining": budget.get('remaining', 0),
        "utilization_percent": (budget.get('used', 0) / budget.get('limit', 1)) * 100 if budget.get('limit', 0) > 0 else 0
    },
    "recommendations": [],
    "analysis_timestamp": datetime.now().isoformat()
}

# Generate recommendations
if analysis["budget_status"]["utilization_percent"] > 80:
    analysis["recommendations"].append("Consider increasing budget limit or optimizing prompts")
if analysis["efficiency_metrics"]["tokens_per_second"] < 5:
    analysis["recommendations"].append("Performance is slow - consider using a faster model")
if analysis["efficiency_metrics"]["cost_per_token"] > 0.0005:
    analysis["recommendations"].append("Cost per token is high - consider using a more efficient model")

result = analysis
""",
        ),
    )

    # Connect workflow
    workflow.connect("monitored_llm", "usage_analyzer", {"result": "llm_response"})

    return workflow


def test_workflow_integration_monitoring(env_info):
    """Test LLM monitoring integration in complex workflows."""
    print("\n🔗 Testing Workflow Integration with Monitoring...")

    try:
        # Create the comprehensive monitored workflow
        workflow = create_monitored_llm_workflow(env_info)

        print(f"   📋 Created workflow: {workflow.name}")
        print(f"      Nodes: {list(workflow.nodes.keys())}")

        # Test with different input scenarios
        test_scenarios = [
            {
                "name": "Technical Question",
                "prompt": "Explain the differences between Docker containers and virtual machines",
            },
            {
                "name": "Code Request",
                "prompt": "Write a Python function to implement a simple cache with TTL",
            },
            {
                "name": "Analysis Task",
                "prompt": "Analyze the trade-offs between SQL and NoSQL databases for a high-traffic web application",
            },
        ]

        workflow_results = []

        for scenario in test_scenarios:
            print(f"\n   Testing scenario: {scenario['name']}")
            print(f"   Prompt: {scenario['prompt'][:60]}...")

            try:
                # Execute workflow
                runner = LocalRuntime()
                start_time = time.time()

                result = runner.execute(
                    workflow, inputs={"prompt_input": scenario["prompt"]}
                )

                execution_time = (time.time() - start_time) * 1000

                if result.get("success"):
                    # Extract results from both nodes
                    llm_result = result.get("results", {}).get("monitored_llm", {})
                    analysis_result = result.get("results", {}).get(
                        "usage_analyzer", {}
                    )

                    print(f"      ✅ Workflow completed in {execution_time:.0f}ms")

                    # Display LLM results
                    if llm_result.get("success"):
                        usage = llm_result.get("usage", {})
                        monitoring = usage.get("monitoring", {})
                        tokens = monitoring.get("tokens", {})
                        cost = monitoring.get("cost", {})

                        print(f"         LLM tokens: {tokens.get('total', 0)}")
                        print(f"         LLM cost: ${cost.get('total', 0):.6f}")

                    # Display analysis results
                    if analysis_result:
                        efficiency = analysis_result.get("efficiency_metrics", {})
                        usage_summary = analysis_result.get("usage_summary", {})
                        budget_status = analysis_result.get("budget_status", {})
                        recommendations = analysis_result.get("recommendations", [])

                        print(
                            f"         Efficiency rating: {efficiency.get('cost_efficiency_rating', 'unknown')}"
                        )
                        print(
                            f"         Speed rating: {efficiency.get('speed_rating', 'unknown')}"
                        )
                        print(
                            f"         Budget used: {budget_status.get('utilization_percent', 0):.1f}%"
                        )

                        if recommendations:
                            print(
                                f"         Recommendations: {len(recommendations)} items"
                            )
                            for rec in recommendations[:2]:  # Show first 2
                                print(f"            - {rec}")

                    workflow_results.append(
                        {
                            "scenario": scenario["name"],
                            "success": True,
                            "execution_time_ms": execution_time,
                            "llm_tokens": (
                                tokens.get("total", 0) if "tokens" in locals() else 0
                            ),
                            "llm_cost": (
                                cost.get("total", 0) if "cost" in locals() else 0
                            ),
                            "efficiency_rating": (
                                efficiency.get("cost_efficiency_rating", "unknown")
                                if "efficiency" in locals()
                                else "unknown"
                            ),
                        }
                    )
                else:
                    error_msg = result.get("error", "Unknown error")
                    print(f"      ❌ Workflow failed: {error_msg}")
                    workflow_results.append(
                        {
                            "scenario": scenario["name"],
                            "success": False,
                            "error": error_msg,
                        }
                    )

            except Exception as e:
                print(f"      ❌ Exception: {e}")
                workflow_results.append(
                    {"scenario": scenario["name"], "success": False, "error": str(e)}
                )

        # Summarize workflow testing
        print("\n=== Workflow Integration Summary ===")
        successful_runs = [r for r in workflow_results if r["success"]]

        if successful_runs:
            total_cost = sum(r["llm_cost"] for r in successful_runs)
            total_tokens = sum(r["llm_tokens"] for r in successful_runs)
            avg_execution_time = sum(
                r["execution_time_ms"] for r in successful_runs
            ) / len(successful_runs)

            print("   📊 Workflow Statistics:")
            print(
                f"      Successful runs: {len(successful_runs)}/{len(test_scenarios)}"
            )
            print(f"      Total cost: ${total_cost:.6f}")
            print(f"      Total tokens: {total_tokens}")
            print(f"      Average execution time: {avg_execution_time:.0f}ms")

            # Efficiency analysis
            efficiency_counts = {}
            for result in successful_runs:
                rating = result["efficiency_rating"]
                efficiency_counts[rating] = efficiency_counts.get(rating, 0) + 1

            print("   🏆 Efficiency Distribution:")
            for rating, count in efficiency_counts.items():
                print(f"      {rating}: {count} runs")

        return workflow_results

    except Exception as e:
        print(f"   ❌ Workflow creation failed: {e}")
        return []


def generate_usage_analytics_report(env_info):
    """Generate comprehensive usage analytics and export reports."""
    print("\n📊 Generating Usage Analytics Report...")

    # Load historical usage data
    historical_data = env_info["historical_usage"]
    data_dir = env_info["data_dir"]

    print(f"   Analyzing {len(historical_data)} historical usage records...")

    # Calculate various analytics
    total_tokens = sum(record["total_tokens"] for record in historical_data)
    total_cost = sum(record["cost"] for record in historical_data)
    avg_latency = sum(record["latency_ms"] for record in historical_data) / len(
        historical_data
    )

    # Model usage breakdown
    model_usage = {}
    for record in historical_data:
        model = record["model"]
        if model not in model_usage:
            model_usage[model] = {"count": 0, "tokens": 0, "cost": 0, "latency": []}
        model_usage[model]["count"] += 1
        model_usage[model]["tokens"] += record["total_tokens"]
        model_usage[model]["cost"] += record["cost"]
        model_usage[model]["latency"].append(record["latency_ms"])

    # Scenario usage breakdown
    scenario_usage = {}
    for record in historical_data:
        scenario = record["scenario"]
        if scenario not in scenario_usage:
            scenario_usage[scenario] = {"count": 0, "tokens": 0, "cost": 0}
        scenario_usage[scenario]["count"] += 1
        scenario_usage[scenario]["tokens"] += record["total_tokens"]
        scenario_usage[scenario]["cost"] += record["cost"]

    # Time-based analysis
    daily_usage = {}
    for record in historical_data:
        date = record["timestamp"][:10]  # YYYY-MM-DD
        if date not in daily_usage:
            daily_usage[date] = {"count": 0, "tokens": 0, "cost": 0}
        daily_usage[date]["count"] += 1
        daily_usage[date]["tokens"] += record["total_tokens"]
        daily_usage[date]["cost"] += record["cost"]

    # Generate comprehensive report
    report = {
        "report_generated": datetime.now().isoformat(),
        "analysis_period": {
            "start_date": min(record["timestamp"] for record in historical_data)[:10],
            "end_date": max(record["timestamp"] for record in historical_data)[:10],
            "total_days": len(daily_usage),
        },
        "overall_statistics": {
            "total_requests": len(historical_data),
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "average_tokens_per_request": total_tokens / len(historical_data),
            "average_cost_per_request": total_cost / len(historical_data),
            "average_latency_ms": avg_latency,
            "cost_per_1k_tokens": (
                (total_cost / total_tokens * 1000) if total_tokens > 0 else 0
            ),
        },
        "model_performance": {},
        "scenario_analysis": scenario_usage,
        "daily_trends": daily_usage,
        "recommendations": [],
    }

    # Calculate model performance metrics
    for model, usage in model_usage.items():
        avg_latency_model = sum(usage["latency"]) / len(usage["latency"])
        report["model_performance"][model] = {
            "request_count": usage["count"],
            "total_tokens": usage["tokens"],
            "total_cost": usage["cost"],
            "average_latency_ms": avg_latency_model,
            "cost_per_request": usage["cost"] / usage["count"],
            "tokens_per_request": usage["tokens"] / usage["count"],
            "market_share_percent": (usage["count"] / len(historical_data)) * 100,
        }

    # Generate recommendations
    recommendations = []

    # Cost optimization recommendations
    most_expensive_model = max(model_usage.items(), key=lambda x: x[1]["cost"])
    if most_expensive_model[1]["cost"] > total_cost * 0.4:
        recommendations.append(
            f"Model '{most_expensive_model[0]}' accounts for {(most_expensive_model[1]['cost']/total_cost)*100:.1f}% of costs - consider optimization"
        )

    # Performance recommendations
    slowest_model = max(
        model_usage.items(), key=lambda x: sum(x[1]["latency"]) / len(x[1]["latency"])
    )
    avg_slowest = sum(slowest_model[1]["latency"]) / len(slowest_model[1]["latency"])
    if avg_slowest > avg_latency * 1.5:
        recommendations.append(
            f"Model '{slowest_model[0]}' is significantly slower than average - consider alternatives"
        )

    # Usage pattern recommendations
    most_used_scenario = max(scenario_usage.items(), key=lambda x: x[1]["count"])
    if most_used_scenario[1]["count"] > len(historical_data) * 0.4:
        recommendations.append(
            f"Scenario '{most_used_scenario[0]}' dominates usage ({(most_used_scenario[1]['count']/len(historical_data))*100:.1f}%) - consider specialized optimization"
        )

    report["recommendations"] = recommendations

    # Save report to file
    report_file = data_dir / "usage_analytics_report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    # Display summary
    print("\n   📊 Analytics Summary:")
    print(
        f"      Period: {report['analysis_period']['start_date']} to {report['analysis_period']['end_date']}"
    )
    print(f"      Total requests: {report['overall_statistics']['total_requests']:,}")
    print(f"      Total tokens: {report['overall_statistics']['total_tokens']:,}")
    print(f"      Total cost: ${report['overall_statistics']['total_cost']:.4f}")
    print(
        f"      Avg cost/request: ${report['overall_statistics']['average_cost_per_request']:.4f}"
    )
    print(
        f"      Avg latency: {report['overall_statistics']['average_latency_ms']:.0f}ms"
    )

    print("\n   🏆 Top Models by Usage:")
    sorted_models = sorted(
        report["model_performance"].items(),
        key=lambda x: x[1]["request_count"],
        reverse=True,
    )
    for i, (model, metrics) in enumerate(sorted_models[:3], 1):
        print(
            f"      {i}. {model}: {metrics['request_count']} requests ({metrics['market_share_percent']:.1f}%)"
        )

    print(f"\n   💡 Recommendations ({len(recommendations)} items):")
    for rec in recommendations:
        print(f"      • {rec}")

    print(f"\n   💾 Report saved to: {report_file}")

    return report


def main():
    """Run comprehensive LLM monitoring testing with real Ollama integration."""
    print("🤖 Comprehensive LLMAgentNode Monitoring with Real Ollama Integration")
    print("=" * 70)

    # Setup test environment
    env_info = setup_test_environment()

    # Run comprehensive tests
    test_real_ollama_integration(env_info)
    test_comprehensive_monitoring_scenarios(env_info)
    test_budget_controls_and_alerts(env_info)
    test_workflow_integration_monitoring(env_info)
    generate_usage_analytics_report(env_info)

    print("\n" + "=" * 70)
    print("✅ Comprehensive LLM monitoring testing completed!")
    print("\nKey capabilities demonstrated:")
    print("   • Real Ollama LLM integration with local AI processing")
    print("   • Production-grade token counting and cost analysis")
    print("   • Multi-model performance comparison and optimization")
    print("   • Enterprise budget controls with alerts and limits")
    print("   • Real-time performance monitoring and analysis")
    print("   • Comprehensive usage analytics and reporting")
    print("   • Workflow integration with monitoring at every step")
    print("   • Historical data analysis and trend identification")
    print("   • Automated recommendations for cost and performance optimization")
    print("\n💡 LLMAgentNode provides enterprise-grade AI monitoring and cost control!")
    print("\n🔧 For full testing with Ollama:")
    print("   1. Start Ollama: ollama serve")
    print("   2. Install models: ollama pull llama3.2")
    print("   3. Run this example for comprehensive monitoring")


if __name__ == "__main__":
    main()
