#!/usr/bin/env python3
"""
Self-Organizing Agent Swarm Example: Product Review Analysis
===========================================================

This example demonstrates how agents dynamically self-organize into teams
based on problem requirements, without central coordination. The solution
emerges from decentralized agent collaboration.

Key Concepts Demonstrated:
1. Agents register their capabilities with a pool manager
2. Problem analyzer breaks down the task into required capabilities
3. Teams form automatically based on capability matching
4. Multiple specialist agents work in parallel
5. Solutions emerge through decentralized collaboration
6. No explicit coordinator - consensus through interaction

The Task:
Same as A2A example - analyze MacBook Air M3 reviews, but using
a swarm of specialized agents that self-organize based on the problem.

Prerequisites:
- Ollama running with mistral model
- Exa API key in .env file
- Perplexity API key in .env file
"""

import os
import time
from pathlib import Path

from kailash import Workflow
from kailash.nodes.ai.self_organizing import (
    AgentPoolManagerNode,
    ProblemAnalyzerNode,
    SelfOrganizingAgentNode,
    SolutionEvaluatorNode,
    TeamFormationNode,
)
from kailash.nodes.mcp import MCPClient
from kailash.runtime.local import LocalRuntime


def create_specialist_agents() -> list[dict]:
    """Define the pool of specialist agents with diverse capabilities."""
    return [
        # Research specialists
        {
            "id": "tech_researcher_001",
            "capabilities": [
                "technical_research",
                "benchmark_analysis",
                "performance_testing",
            ],
            "role": "technical_researcher",
            "expertise": "hardware performance and benchmarks",
        },
        {
            "id": "market_researcher_001",
            "capabilities": [
                "market_research",
                "competitor_analysis",
                "pricing_strategy",
            ],
            "role": "market_analyst",
            "expertise": "market trends and competitive positioning",
        },
        {
            "id": "ux_researcher_001",
            "capabilities": ["user_research", "sentiment_analysis", "review_mining"],
            "role": "ux_researcher",
            "expertise": "user experience and satisfaction",
        },
        # Domain experts
        {
            "id": "hardware_expert_001",
            "capabilities": [
                "hardware_analysis",
                "chip_architecture",
                "thermal_design",
            ],
            "role": "hardware_specialist",
            "expertise": "Apple Silicon and laptop hardware",
        },
        {
            "id": "battery_expert_001",
            "capabilities": ["battery_analysis", "power_efficiency", "usage_patterns"],
            "role": "battery_specialist",
            "expertise": "battery technology and power management",
        },
        {
            "id": "display_expert_001",
            "capabilities": ["display_technology", "color_accuracy", "visual_quality"],
            "role": "display_specialist",
            "expertise": "display panels and visual technology",
        },
        # Synthesis specialists
        {
            "id": "data_synthesizer_001",
            "capabilities": [
                "data_synthesis",
                "pattern_recognition",
                "insight_extraction",
            ],
            "role": "synthesizer",
            "expertise": "combining diverse data sources",
        },
        {
            "id": "comparative_analyst_001",
            "capabilities": ["comparative_analysis", "benchmarking", "trend_analysis"],
            "role": "analyst",
            "expertise": "product comparisons and trends",
        },
        # Quality and validation
        {
            "id": "fact_checker_001",
            "capabilities": [
                "fact_checking",
                "source_verification",
                "accuracy_validation",
            ],
            "role": "validator",
            "expertise": "information verification",
        },
        {
            "id": "quality_auditor_001",
            "capabilities": [
                "quality_assurance",
                "completeness_check",
                "standard_compliance",
            ],
            "role": "auditor",
            "expertise": "review quality standards",
        },
        # Communication specialists
        {
            "id": "tech_writer_001",
            "capabilities": [
                "technical_writing",
                "documentation",
                "clarity_enhancement",
            ],
            "role": "writer",
            "expertise": "clear technical communication",
        },
        {
            "id": "summary_expert_001",
            "capabilities": [
                "summarization",
                "key_point_extraction",
                "executive_summary",
            ],
            "role": "summarizer",
            "expertise": "distilling complex information",
        },
    ]


def create_swarm_review_workflow():
    """Create a self-organizing swarm workflow for review analysis."""
    workflow = Workflow("swarm-review-001", name="swarm_review_analysis")

    # === Core Swarm Infrastructure ===

    # Agent Pool Manager - tracks all available agents
    workflow.add_node(
        "agent_pool",
        AgentPoolManagerNode(),
        max_active_agents=20,
        agent_timeout=300,  # 5 minute timeout
        performance_window=10,  # Track last 10 tasks
    )

    # Problem Analyzer - understands what capabilities are needed
    workflow.add_node(
        "problem_analyzer",
        ProblemAnalyzerNode(),
        analysis_strategy="capability_decomposition",
        granularity="fine",  # Detailed capability requirements
        include_dependencies=True,  # Consider capability dependencies
    )

    # Team Formation - creates optimal teams from available agents
    workflow.add_node(
        "team_formation",
        TeamFormationNode(),
        formation_strategy="capability_matching",  # Match capabilities to requirements
        optimization_criteria=[
            "capability_coverage",
            "performance_history",
            "team_size",
        ],
        max_team_size=8,
        allow_redundancy=True,  # Multiple agents can have same capability
    )

    # Solution Evaluator - aggregates and evaluates team outputs
    workflow.add_node(
        "solution_evaluator",
        SolutionEvaluatorNode(),
        evaluation_criteria=["completeness", "accuracy", "depth", "coherence"],
        aggregation_strategy="weighted_consensus",
        quality_threshold=0.85,
    )

    # === Search Infrastructure ===
    workflow.add_node("exa_search", MCPClient())
    workflow.add_node("perplexity_search", MCPClient())

    # === Specialist Agents ===
    # Create all specialist agents
    for agent_spec in create_specialist_agents():
        workflow.add_node(
            agent_spec["id"],
            SelfOrganizingAgentNode(),
            agent_id=agent_spec["id"],
            agent_role=agent_spec["role"],
            capabilities=agent_spec["capabilities"],
            provider="ollama",
            model="mistral",
            temperature=0.6,
            system_prompt=f"""You are a {agent_spec['expertise']} specialist.

Capabilities: {', '.join(agent_spec['capabilities'])}

When activated:
1. Focus on your area of expertise
2. Collaborate with other agents through shared context
3. Provide specific, detailed insights
4. Build upon others' findings
5. Signal completion when your contribution is ready

Output structured findings relevant to your expertise.""",
        )

    # === Workflow Connections ===
    # Problem flows to analyzer
    workflow.connect("problem_analyzer", "agent_pool")
    workflow.connect("problem_analyzer", "team_formation")

    # Team formation connects to agent pool
    workflow.connect("agent_pool", "team_formation")

    # Team formation activates selected agents
    for agent_spec in create_specialist_agents():
        workflow.connect("team_formation", agent_spec["id"])

        # Agents can access search tools
        workflow.connect(agent_spec["id"], "exa_search")
        workflow.connect(agent_spec["id"], "perplexity_search")

        # Agents output to evaluator
        workflow.connect(agent_spec["id"], "solution_evaluator")

    # Search results flow back to agents
    for agent_spec in create_specialist_agents():
        workflow.connect("exa_search", agent_spec["id"])
        workflow.connect("perplexity_search", agent_spec["id"])

    return workflow


def main():
    """Execute the swarm review analysis workflow."""
    print("=" * 80)
    print("SELF-ORGANIZING SWARM EXAMPLE: Product Review Analysis")
    print("=" * 80)
    print()
    print("This example shows how agents self-organize into teams based on")
    print("problem requirements, without central coordination.")
    print()

    # Load environment variables
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

    # Verify prerequisites
    import requests

    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code != 200:
            print("ERROR: Ollama is not running. Please start with: ollama serve")
            return

        models = response.json().get("models", [])
        if not any(m.get("name", "").startswith("mistral") for m in models):
            print("ERROR: mistral model not found. Install with: ollama pull mistral")
            return
    except Exception as e:
        print(f"ERROR: Cannot connect to Ollama: {e}")
        return

    print("✓ Prerequisites verified")
    print()

    # Create workflow
    workflow = create_swarm_review_workflow()

    # Problem definition
    problem = {
        "title": "Comprehensive MacBook Air M3 2024 Review Analysis",
        "description": """Analyze all aspects of the Apple MacBook Air M3 2024 model by:
        1. Gathering reviews from multiple sources
        2. Analyzing performance benchmarks and real-world usage
        3. Evaluating battery life in various scenarios
        4. Assessing display quality and color accuracy
        5. Examining build quality and portability
        6. Comparing value against competitors
        7. Synthesizing user feedback and professional opinions
        8. Comparing improvements over the M2 model""",
        "constraints": {
            "time_limit": 300,  # 5 minutes
            "quality_threshold": 0.85,
            "require_sources": True,
        },
        "output_format": "structured_report",
    }

    # Register all agents with the pool
    agent_pool = workflow._node_instances["agent_pool"]
    print("Registering specialist agents...")

    for agent_spec in create_specialist_agents():
        agent_pool.execute(
            action="register",
            agent_id=agent_spec["id"],
            capabilities=agent_spec["capabilities"],
            metadata={
                "role": agent_spec["role"],
                "expertise": agent_spec["expertise"],
                "performance_score": 0.8 + len(agent_spec["capabilities"]) * 0.02,
            },
        )
        print(f"  ✓ {agent_spec['id']}: {agent_spec['expertise']}")

    print(f"\nTotal agents in pool: {len(create_specialist_agents())}")
    print()

    # Configure execution parameters
    parameters = {
        "problem_analyzer": {"problem": problem},
        "agent_pool": {"action": "get_metrics"},  # Will be overridden during execution
        "team_formation": {"formation_mode": "dynamic", "prefer_diverse_teams": True},
        "solution_evaluator": {
            "evaluation_mode": "comprehensive",
            "require_consensus": False,  # Allow diverse perspectives
            "minimum_contributions": 5,  # Need at least 5 agents
        },
        "exa_search": {
            "server_config": {
                "name": "exa-server",
                "transport": "stdio",
                "command": "npx",
                "args": [
                    "-y",
                    "mcp-remote",
                    f"https://mcp.exa.ai/mcp?exaApiKey={os.environ.get('EXA_API_KEY', '')}",
                ],
            },
            "operation": "call_tool",
            "tool_name": "search",
            "timeout": 30,
        },
        "perplexity_search": {
            "server_config": {
                "name": "perplexity-server",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "server-perplexity-ask"],
                "env": {"PERPLEXITY_API_KEY": os.environ.get("PERPLEXITY_API_KEY", "")},
            },
            "operation": "call_tool",
            "tool_name": "ask",
            "timeout": 30,
        },
    }

    # Create runtime
    runtime = LocalRuntime(debug=True)

    print("Starting swarm workflow execution...")
    print("Agents will self-organize based on problem requirements")
    print("-" * 80)
    print()

    start_time = time.time()

    try:
        # Execute workflow
        results, run_id = runtime.execute(workflow, parameters=parameters)

        elapsed = time.time() - start_time

        print("\n" + "=" * 80)
        print("EXECUTION COMPLETE")
        print("=" * 80)
        print(f"Run ID: {run_id}")
        print(f"Elapsed time: {elapsed:.2f} seconds")
        print()

        # Analyze results
        if "problem_analyzer" in results:
            analysis = results["problem_analyzer"].get("analysis", {})
            print("Problem Analysis:")
            print(
                f"  Required capabilities: {len(analysis.get('required_capabilities', []))}"
            )
            if "required_capabilities" in analysis:
                print(
                    f"  Capabilities: {', '.join(analysis['required_capabilities'][:5])}..."
                )
            print()

        if "team_formation" in results:
            team = results["team_formation"].get("team", {})
            print("Team Formation:")
            print(f"  Team size: {team.get('size', 0)}")
            print(f"  Capability coverage: {team.get('capability_coverage', 0):.1%}")
            if "selected_agents" in team:
                print(f"  Selected agents: {len(team['selected_agents'])}")
                for agent in team["selected_agents"][:3]:
                    print(
                        f"    - {agent['agent_id']}: {', '.join(agent['capabilities'])}"
                    )
                if len(team["selected_agents"]) > 3:
                    print(f"    ... and {len(team['selected_agents']) - 3} more")
            print()

        if "solution_evaluator" in results:
            evaluation = results["solution_evaluator"]
            print("Solution Evaluation:")

            if "quality_score" in evaluation:
                print(f"  Overall quality: {evaluation['quality_score']:.2f}/1.0")

            if "aggregated_solution" in evaluation:
                solution = evaluation["aggregated_solution"]
                print(f"  Contributing agents: {solution.get('num_contributors', 0)}")

                if "sections" in solution:
                    print(f"  Report sections: {len(solution['sections'])}")
                    for section in solution["sections"][:3]:
                        print(f"    - {section.get('title', 'Untitled')}")

            if "consensus_reached" in evaluation:
                print(f"  Consensus reached: {evaluation['consensus_reached']}")

            # Print solution preview
            if "final_report" in evaluation:
                print("\nFinal Report Preview:")
                print("-" * 40)
                report = evaluation["final_report"]
                print(report[:500] + "..." if len(report) > 500 else report)

        # Agent participation metrics
        active_agents = [k for k in results.keys() if k.endswith("_001")]
        print(f"\nAgent Participation: {len(active_agents)} agents contributed")

    except Exception as e:
        print(f"\nError during execution: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()


"""
Expected Behavior:
=================

1. Problem Analyzer examines the review analysis task
   - Identifies required capabilities (research, analysis, synthesis, etc.)
   - Breaks down into subtasks

2. Team Formation queries the agent pool
   - Matches required capabilities to available agents
   - Forms optimal team based on expertise and performance

3. Selected agents activate simultaneously
   - Each focuses on their specialty
   - Agents work in parallel, not sequentially
   - May request searches based on their needs

4. Agents produce specialized outputs
   - Tech researchers focus on benchmarks
   - Market analysts examine competition
   - UX researchers mine user feedback
   - Each contributes their perspective

5. Solution Evaluator aggregates contributions
   - Combines diverse perspectives
   - Weights by expertise and confidence
   - Produces unified analysis

6. Quality emerges from swarm intelligence
   - No central coordinator needed
   - Agents self-organize around the problem
   - Solution quality from collective intelligence

Key Advantages:
- Truly decentralized - no coordinator
- Agents selected based on problem needs
- Parallel processing by specialists
- Emergent quality from diverse perspectives
- Scalable - easy to add more specialist agents
- Robust - handles agent failures gracefully
"""
