"""
Semantic Routing with A2A Capability Matching.

Demonstrates:
- A2A protocol for automatic agent selection
- Semantic capability-based routing
- Best-fit agent matching for different task types
- Score-based agent selection

Use case: Intelligent task routing based on agent capabilities.
Cost: $0 (uses Ollama)
"""

import asyncio

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.orchestration import (
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
    RoutingStrategy,
)
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Define Signatures
# ============================================================================


class TaskSignature(Signature):
    """Generic task processing signature."""

    task: str = InputField(description="Task description")
    result: str = OutputField(description="Task result")


# ============================================================================
# Create Specialized Agents
# ============================================================================


def create_python_expert():
    """Create Python code generation expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # A2A capability card: Python-specific
    agent._a2a_card = {
        "name": "PythonExpert",
        "capability": "Python code generation and debugging",
        "description": "Expert in Python programming, data structures, and algorithms",
    }

    return agent


def create_javascript_expert():
    """Create JavaScript code generation expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # A2A capability card: JavaScript-specific
    agent._a2a_card = {
        "name": "JavaScriptExpert",
        "capability": "JavaScript and frontend development",
        "description": "Expert in JavaScript, React, Node.js, and web development",
    }

    return agent


def create_data_scientist():
    """Create data science and ML expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # A2A capability card: Data science-specific
    agent._a2a_card = {
        "name": "DataScientist",
        "capability": "Data analysis and machine learning",
        "description": "Expert in statistics, data visualization, and ML algorithms",
    }

    return agent


def create_technical_writer():
    """Create technical documentation expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # A2A capability card: Technical writing-specific
    agent._a2a_card = {
        "name": "TechnicalWriter",
        "capability": "Technical documentation and API docs",
        "description": "Expert in writing clear technical documentation and tutorials",
    }

    return agent


# ============================================================================
# Main Orchestration
# ============================================================================


async def main():
    """Demonstrate semantic routing with A2A capability matching."""

    # Configure runtime
    config = OrchestrationRuntimeConfig(
        max_concurrent_agents=5,
        enable_health_monitoring=True,
    )

    # Create runtime
    runtime = OrchestrationRuntime(config=config)
    await runtime.start()

    try:
        # Create specialized agents
        python_expert = create_python_expert()
        js_expert = create_javascript_expert()
        data_scientist = create_data_scientist()
        tech_writer = create_technical_writer()

        # Register agents
        print("Registering specialized agents...")
        await runtime.register_agent(python_expert)
        await runtime.register_agent(js_expert)
        await runtime.register_agent(data_scientist)
        await runtime.register_agent(tech_writer)

        print(f"✓ Registered {len(runtime.agents)} agents:")
        for agent in [python_expert, js_expert, data_scientist, tech_writer]:
            print(f"  - {agent._a2a_card['name']}: {agent._a2a_card['capability']}")

        # Define diverse tasks for semantic routing
        tasks = [
            ("Write a Python function to sort a list", "Python task"),
            ("Create React component for user profile", "JavaScript task"),
            ("Analyze sales data and create visualization", "Data science task"),
            ("Write API documentation for REST endpoint", "Technical writing task"),
            ("Implement NumPy matrix operations", "Python task"),
            ("Build Express.js middleware", "JavaScript task"),
            ("Train logistic regression model", "Data science task"),
            ("Document database schema", "Technical writing task"),
        ]

        # Route tasks using semantic strategy (A2A capability matching)
        print("\n" + "=" * 70)
        print("Routing tasks with SEMANTIC strategy (A2A capability matching)")
        print("=" * 70)

        for task_description, task_type in tasks:
            # Route task - runtime automatically selects best agent via A2A
            selected_agent = await runtime.route_task(
                task_description, strategy=RoutingStrategy.SEMANTIC
            )

            if selected_agent:
                agent_name = selected_agent._a2a_card["name"]
                agent_capability = selected_agent._a2a_card["capability"]

                print(f"\nTask: '{task_description}'")
                print(f"  Expected type: {task_type}")
                print(f"  Selected agent: {agent_name}")
                print(f"  Agent capability: {agent_capability}")
            else:
                print(f"\nTask: '{task_description}'")
                print("  ⚠ No agent selected (empty pool)")

        # Demonstrate concurrent semantic routing
        print("\n" + "=" * 70)
        print("Concurrent Semantic Routing (10 tasks)")
        print("=" * 70)

        concurrent_tasks = [
            "Write Python decorator",
            "Create JavaScript closure",
            "Analyze time series data",
            "Document authentication flow",
            "Implement binary search in Python",
            "Build Vue.js component",
            "Calculate correlation matrix",
            "Write migration guide",
            "Python context manager",
            "React hooks implementation",
        ]

        # Route all tasks concurrently
        routing_coroutines = [
            runtime.route_task(task, strategy=RoutingStrategy.SEMANTIC)
            for task in concurrent_tasks
        ]

        selected_agents = await asyncio.gather(*routing_coroutines)

        # Display results
        print("\nRouting Results:")
        for i, (task, agent) in enumerate(zip(concurrent_tasks, selected_agents), 1):
            if agent:
                agent_name = agent._a2a_card["name"]
                print(f"{i:2d}. {task:35s} → {agent_name}")
            else:
                print(f"{i:2d}. {task:35s} → No agent")

        # Distribution summary
        print("\nAgent Selection Summary:")
        from collections import Counter

        distribution = Counter(
            agent._a2a_card["name"] for agent in selected_agents if agent
        )
        for agent_name, count in sorted(distribution.items()):
            percentage = (count / len(concurrent_tasks)) * 100
            print(f"  {agent_name:20s}: {count:2d} tasks ({percentage:5.1f}%)")

    finally:
        # Shutdown runtime
        await runtime.shutdown()
        print("\n✓ Runtime shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
